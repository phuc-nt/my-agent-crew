"""Signing in to a server with OAuth: where the sign-in is found, what goes with the person
and what comes back with them, where the tokens are kept, and what renews or ends them
(`mcp/oauth_discovery.py`, `mcp/oauth.py`, `mcp/sign_in.py`, `mcp/renewal.py`,
`mcp/tokens.py`)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from my_agent_crew import texts_mcp as t
from my_agent_crew.env_file import env_path, load_env_file, read_env
from my_agent_crew.mcp import oauth_discovery, sign_in
from my_agent_crew.mcp.hub import CONNECTED, FAILED, SIGNED_OUT, McpHub
from my_agent_crew.mcp.oauth_discovery import discover
from my_agent_crew.mcp.wire import McpError, Unauthorized
from tests.mcp_fakes import (
    AUTH,
    AUTH_DOC,
    MCP_URL,
    PUBLIC_ADDRESS,
    REDIRECT,
    RESOURCE_DOC,
    FakeMcp,
    make_hub,
    s256,
    server,
)

ACCESS, REFRESH, CLIENT, ISSUER = (
    "MCP_NOTION_ACCESS_TOKEN",
    "MCP_NOTION_REFRESH_TOKEN",
    "MCP_NOTION_CLIENT_ID",
    "MCP_NOTION_ISSUER",
)
ELSEWHERE = "https://login.elsewhere.test"
HOST_DOC = "https://mcp.example.test/.well-known/oauth-protected-resource"
OWN_AUTH_DOC = "https://mcp.example.test/.well-known/oauth-authorization-server"
OWN_OPENID_DOC = "https://mcp.example.test/.well-known/openid-configuration"


async def asked(fake: FakeMcp, **kwargs) -> McpHub:
    """A hub whose server has just refused it for want of a sign-in."""
    hub = make_hub(fake, **kwargs)
    await hub.connect()
    assert hub.links["notion"].status == SIGNED_OUT
    return hub


async def signed_in(fake: FakeMcp, **kwargs) -> McpHub:
    hub = await asked(fake, **kwargs)
    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))
    assert await sign_in.finish(hub, state, code) == "notion"
    assert hub.links["notion"].status == CONNECTED
    return hub


def intercepting(hub: McpHub, fake: FakeMcp, intercept) -> None:
    """Lets `intercept` answer a request before the fake does; None leaves it to the fake."""

    async def handle(request: httpx.Request) -> httpx.Response:
        early = intercept(request)
        return early if early is not None else await fake.handle(request)

    hub.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))


def gets(fake: FakeMcp) -> list[str]:
    return [url for method, url in fake.fetched if method == "GET"]


async def test_a_sign_in_goes_out_with_the_person_and_comes_back_as_a_connected_server(
    tmp_path: Path,
):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    assert "oauth-protected-resource" in link.challenge and link.tools == ()

    url = await sign_in.begin(hub, link, REDIRECT)

    assert url.startswith(f"{AUTH}/authorize?")
    sent = dict(parse_qsl(urlsplit(url).query))
    assert sent == {
        "response_type": "code",
        "client_id": "client-1",
        "redirect_uri": REDIRECT,
        "state": sent["state"],
        "code_challenge": sent["code_challenge"],
        "code_challenge_method": "S256",
        # The token is asked for this server and no other (RFC 8707).
        "resource": "https://mcp.example.test",
        "scope": "default",
    }
    assert len(sent["state"]) >= 32 and len(sent["code_challenge"]) == 43
    assert fake.registered == [
        {
            "client_name": "my-agent-crew",
            "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    ]
    # What the server said of where to sign in is read first, before any guess.
    assert gets(fake) == [RESOURCE_DOC, AUTH_DOC]

    code, state = fake.approve(url)
    assert await sign_in.finish(hub, state, code) == "notion"

    [traded] = fake.token_requests
    assert traded == {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": "client-1",
        "code_verifier": traded["code_verifier"],
        "resource": "https://mcp.example.test",
    }
    # The verifier never left with the person: only its digest did.
    assert s256(traded["code_verifier"]) == sent["code_challenge"]
    assert traded["code_verifier"] not in url
    assert link.status == CONNECTED and link.error == "" and link.challenge == ""
    assert [tool.remote for tool in link.tools] == ["search", "create-page"]
    assert fake.seen[-1].headers["authorization"] == "Bearer access-1"
    # Where it was granted is kept beside it: the one place it is ever renewed.
    kept = {ACCESS: "access-1", REFRESH: "refresh-1", CLIENT: "client-1", ISSUER: AUTH}
    assert environ == kept and read_env(env_path(tmp_path)) == kept
    assert env_path(tmp_path).stat().st_mode & 0o777 == 0o600
    [row] = hub.describe({})
    assert row["signed_in"] is True and row["uses_key"] is False
    assert "access-1" not in repr(row) and "refresh-1" not in repr(row)


async def test_the_next_start_reads_the_sign_in_back_and_connects_without_asking(tmp_path: Path):
    fake = FakeMcp(oauth=True)
    await signed_in(fake, environ={}, home=tmp_path)
    started: dict[str, str] = {}
    load_env_file(tmp_path, started)

    hub = make_hub(fake, environ=started, home=tmp_path)
    await hub.connect()

    assert hub.links["notion"].status == CONNECTED and len(fake.token_requests) == 1


@pytest.mark.parametrize(
    ("published", "read"),
    [
        ({RESOURCE_DOC: "resource", AUTH_DOC: "auth"}, [RESOURCE_DOC, AUTH_DOC]),
        ({HOST_DOC: "resource", AUTH_DOC: "auth"}, [RESOURCE_DOC, HOST_DOC, AUTH_DOC]),
        # A server that publishes nothing of what protects it is its own sign-in.
        ({OWN_AUTH_DOC: "own"}, [RESOURCE_DOC, HOST_DOC, OWN_AUTH_DOC]),
        ({OWN_OPENID_DOC: "own"}, [RESOURCE_DOC, HOST_DOC, OWN_AUTH_DOC, OWN_OPENID_DOC]),
    ],
    ids=["for its own path", "for its host", "its own sign-in", "an OpenID document"],
)
async def test_with_no_word_from_the_server_the_sign_in_is_looked_for_where_it_is_published(
    published, read
):
    fake = FakeMcp(oauth=True)
    documents = {
        "resource": fake.documents[RESOURCE_DOC],
        "auth": fake.documents[AUTH_DOC],
        "own": {**fake.documents[AUTH_DOC], "issuer": "https://mcp.example.test"},
    }
    fake.documents = {url: documents[kind] for url, kind in published.items()}
    hub = await asked(fake)
    hub.links["notion"].challenge = ""  # the refusal named no place

    url = await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert gets(fake) == read and url.startswith(f"{AUTH}/authorize?")


def publish(fake: FakeMcp, doc: str, **changes) -> None:
    fake.documents[doc] = {**fake.documents[doc], **changes}


def inside_for_some(host: str) -> list[str]:
    """`lan.` names resolve inside the network, and `both.` names to both sides of it: one
    address inside is enough for a request to end up there."""
    if host.startswith("lan."):
        return ["10.0.0.5"]
    return [PUBLIC_ADDRESS, "10.0.0.5"] if host.startswith("both.") else [PUBLIC_ADDRESS]


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (lambda f: publish(f, AUTH_DOC, issuer="https://evil.example.test"), "tự nhận là"),
        (lambda f: publish(f, AUTH_DOC, code_challenge_methods_supported=["plain"]), "PKCE S256"),
        (lambda f: publish(f, AUTH_DOC, code_challenge_methods_supported=None), "PKCE S256"),
        (
            lambda f: publish(f, RESOURCE_DOC, resource="https://other.example.test"),
            "không cùng nguồn",
        ),
        (
            lambda f: publish(f, AUTH_DOC, authorization_endpoint=f"http://{AUTH[8:]}/authorize"),
            "phải là https",
        ),
        (lambda f: publish(f, AUTH_DOC, token_endpoint="https://lan.example.test/t"), "nội bộ"),
        (lambda f: publish(f, AUTH_DOC, token_endpoint="https://both.example.test/t"), "nội bộ"),
        (
            lambda f: publish(f, AUTH_DOC, token_endpoint=f"https://someone@{AUTH[8:]}/token"),
            "phải là https",
        ),
        (lambda f: publish(f, AUTH_DOC, token_endpoint=None), "phải là https"),
        (
            lambda f: publish(f, AUTH_DOC, registration_endpoint="https://lan.example.test/r"),
            "nội bộ",
        ),
        (
            lambda f: publish(f, RESOURCE_DOC, authorization_servers=["https://lan.example.test"]),
            "nội bộ",
        ),
        (lambda f: publish(f, RESOURCE_DOC, authorization_servers=[7]), "phải là https"),
        (lambda f: f.documents.pop(AUTH_DOC), "Không đọc được thông tin đăng nhập"),
        (
            lambda f: publish(f, AUTH_DOC, padding="x" * 250_000),
            "Không đọc được thông tin đăng nhập",
        ),
        (lambda f: publish(f, AUTH_DOC, registration_endpoint=f"{AUTH}/nowhere"), "HTTP 404"),
    ],
    ids=[
        "a document that names another issuer",
        "no S256",
        "no word on PKCE at all",
        "a resource of another origin",
        "an authorize address without TLS",
        "a token address inside the network",
        "a token address that is also inside the network",
        "a token address with someone's name in it",
        "no token address",
        "a registration address inside the network",
        "an issuer inside the network",
        "an issuer that is not an address",
        "nothing published by the issuer",
        "a document too large to be one",
        "a registration that is refused",
    ],
)
async def test_a_sign_in_that_cannot_be_trusted_is_not_started(change, said):
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    hub.resolver = inside_for_some
    change(fake)

    with pytest.raises(McpError) as failure:
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert said in str(failure.value)
    # Nothing was sent to an address inside the network to find that out.
    inside = ("lan.example.test", "both.example.test")
    assert not [url for _, url in fake.fetched if any(host in url for host in inside)]
    assert fake.token_requests == [] and hub.sign_ins.take("") is None


async def test_where_to_register_is_checked_when_it_is_learnt():
    """Not only when something is sent there: what is kept as where to sign in holds no
    address this crew would refuse to use."""
    fake = FakeMcp(oauth=True)
    publish(fake, AUTH_DOC, registration_endpoint="https://lan.example.test/r")

    with pytest.raises(McpError, match="nội bộ"):
        await discover(fake.client(), MCP_URL, "", inside_for_some)


async def test_a_registration_the_sign_in_server_refuses_is_not_a_client_id():
    """Whatever the refusal carries, even something that reads like a client id."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ)
    refusal = {"client_id": "not-for-you", "error": "access_denied"}
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(403, json=refusal) if str(request.url) == f"{AUTH}/register" else None
        ),
    )

    with pytest.raises(McpError, match="HTTP 403 access_denied"):
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert environ == {}


async def test_a_place_the_server_points_at_inside_the_network_is_never_fetched():
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    hub.resolver = lambda host: ["127.0.0.1"] if host == "internal.example.test" else ["8.8.8.8"]
    hub.links["notion"].challenge = 'Bearer resource_metadata="https://internal.example.test/x"'

    with pytest.raises(McpError, match="nội bộ"):
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert gets(fake) == []


async def test_a_discovery_document_that_redirects_is_not_followed():
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    elsewhere = "https://elsewhere.example.test/doc"
    fake.documents[HOST_DOC] = fake.documents[RESOURCE_DOC]
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(302, headers={"Location": elsewhere})
            if str(request.url) == RESOURCE_DOC
            else None
        ),
    )

    await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert elsewhere not in gets(fake) and HOST_DOC in gets(fake)


@pytest.mark.parametrize("url", ["http://localhost:3000/mcp", "http://127.0.0.1:3000/mcp"])
async def test_a_server_on_this_machine_is_not_signed_in_to_with_oauth(url):
    """It may be reached without TLS, which is fine for a key in a header and not for a
    token traded over the same wire."""
    fake = FakeMcp(oauth=True)
    hub = make_hub(fake, server(url=url))

    with pytest.raises(McpError, match="phải là https"):
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert gets(fake) == []


async def test_a_server_authorised_by_a_key_in_the_file_has_no_sign_in():
    fake = FakeMcp(oauth=True)
    hub = make_hub(fake, server(headers={"Authorization": "Bearer ${K}"}), environ={"K": "k"})

    with pytest.raises(McpError) as failure:
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert str(failure.value) == t.MCP_LOGIN_HEADER_KEY and fake.fetched == []


async def test_a_key_refused_in_the_middle_of_a_call_is_a_key_to_mend_not_a_sign_in():
    """The row must not offer a sign-in that cannot start."""
    fake, environ = FakeMcp(oauth=True), {"K": "first"}
    fake.required = "first"
    hub = make_hub(fake, server(headers={"Authorization": "Bearer ${K}"}), environ=environ)
    await hub.connect()
    link = hub.links["notion"]
    assert link.status == CONNECTED
    fake.required = "second"  # the key was changed at the server

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert (link.status, link.error) == (FAILED, t.MCP_KEY_REFUSED)
    assert fake.token_requests == [] and gets(fake) == []
    assert fake.methods().count("tools/call") == 1
    # A failed server is tried again without being asked, so a mended key is picked up.
    assert hub.waiting() == ["notion"]
    environ["K"] = "second"
    await hub.connect(hub.waiting())
    assert link.status == CONNECTED and link.error == ""


async def test_where_no_client_may_register_itself_the_owners_client_id_is_used(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    del fake.documents[AUTH_DOC]["registration_endpoint"]
    hub = await asked(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]

    with pytest.raises(McpError) as failure:
        await sign_in.begin(hub, link, REDIRECT)
    assert str(failure.value) == t.MCP_OAUTH_NO_REGISTRATION.format(name=CLIENT)

    environ[CLIENT] = "registered-by-hand"
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    await sign_in.finish(hub, state, code)

    assert link.status == CONNECTED and fake.registered == []
    assert fake.token_requests[0]["client_id"] == "registered-by-hand"


async def test_a_state_is_good_once_and_only_for_the_newest_click():
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    link = hub.links["notion"]
    first_code, first = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    assert first != state

    # The earlier click's state stopped being worth anything when the second was made.
    assert await sign_in.finish(hub, first, first_code) is None
    assert await sign_in.finish(hub, "", code) is None
    assert await sign_in.finish(hub, "made-up", code) is None
    assert fake.token_requests == [] and link.status == SIGNED_OUT

    assert await sign_in.finish(hub, state, code) == "notion"
    assert await sign_in.finish(hub, state, code) is None
    assert len(fake.token_requests) == 1 and link.status == CONNECTED


async def test_a_person_who_comes_back_too_late_is_told_to_start_again():
    fake, now = FakeMcp(oauth=True), [1000.0]
    hub = await asked(fake)
    link = hub.links["notion"]
    hub.sign_ins = sign_in.SignIns(clock=lambda: now[0])
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))

    now[0] += sign_in.STATE_SECONDS

    assert await sign_in.finish(hub, state, code) == "notion"
    assert link.error == t.MCP_OAUTH_LATE and link.status == SIGNED_OUT
    # The code is not traded, and the state is spent like any other.
    assert fake.token_requests == []
    now[0] -= sign_in.STATE_SECONDS
    assert await sign_in.finish(hub, state, code) is None


async def test_a_state_is_still_good_just_before_its_time_is_up():
    fake, now = FakeMcp(oauth=True), [1000.0]
    hub = await asked(fake)
    hub.sign_ins = sign_in.SignIns(clock=lambda: now[0])
    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))

    now[0] += sign_in.STATE_SECONDS - 0.001
    await sign_in.finish(hub, state, code)

    assert hub.links["notion"].status == CONNECTED


async def test_a_server_that_asks_for_no_sign_in_is_not_signed_in_to():
    fake = FakeMcp()
    hub = make_hub(fake)
    await hub.connect()

    with pytest.raises(McpError) as failure:
        await sign_in.begin(hub, hub.links["notion"], REDIRECT)

    assert str(failure.value) == t.MCP_LOGIN_NOT_ASKED
    assert [url for _, url in fake.fetched if url != MCP_URL] == []


async def test_a_server_already_signed_in_to_may_be_signed_in_to_again(tmp_path: Path):
    """Another account, or a workspace the first sign-in did not include."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)

    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))
    await sign_in.finish(hub, state, code)

    assert hub.links["notion"].status == CONNECTED
    assert (environ[ACCESS], environ[CLIENT]) == ("access-2", "client-2")


async def test_a_sign_in_that_ran_out_while_the_crew_was_down_is_renewed_as_it_starts(
    tmp_path: Path,
):
    fake = FakeMcp(oauth=True)
    await signed_in(fake, environ={}, home=tmp_path)
    started: dict[str, str] = {}
    load_env_file(tmp_path, started)
    fake.required, fetched = "ran-out", len(fake.fetched)

    hub = make_hub(fake, environ=started, home=tmp_path)
    await hub.connect()

    # Nothing remembered where to renew: it is looked up again, then asked once.
    assert hub.links["notion"].status == CONNECTED and started[ACCESS] == "access-2"
    assert gets(fake)[-2:] == [RESOURCE_DOC, AUTH_DOC]
    assert fake.token_requests[-1]["grant_type"] == "refresh_token"
    assert len(fake.fetched) > fetched

    # What was looked up then is remembered: the next renewal asks nowhere.
    fake.required, looked = "ran-out-again", len(gets(fake))
    await hub.links["notion"].session.call_tool("create-page", {"title": "Báo cáo"})
    assert started[ACCESS] == "access-3" and len(gets(fake)) == looked


@pytest.mark.parametrize(
    ("code", "error", "said"),
    [
        ("", "access_denied", t.MCP_OAUTH_DENIED.format(error="access_denied")),
        ("", "", t.MCP_OAUTH_NO_CODE),
        ("not-the-code", "", t.MCP_OAUTH_TOKEN.format(error="HTTP 400 invalid_grant")),
    ],
    ids=["the person said no", "no code came back", "a code the server does not know"],
)
async def test_a_sign_in_that_does_not_end_well_says_so_on_the_servers_row(code, error, said):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ)
    link = hub.links["notion"]
    _, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))

    assert await sign_in.finish(hub, state, code, error) == "notion"

    assert link.error == said and link.status == SIGNED_OUT
    assert ACCESS not in environ and REFRESH not in environ


async def test_a_no_that_comes_back_with_a_code_is_still_a_no():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))

    assert await sign_in.finish(hub, state, code, "access_denied") == "notion"

    assert link.error == t.MCP_OAUTH_DENIED.format(error="access_denied")
    assert fake.token_requests == [] and link.status == SIGNED_OUT
    assert ACCESS not in environ


async def test_a_token_sent_with_a_failure_is_not_kept():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    broken = {"access_token": "a", "token_type": "Bearer"}
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(500, json=broken) if str(request.url) == f"{AUTH}/token" else None
        ),
    )

    await sign_in.finish(hub, state, code)

    assert link.error == t.MCP_OAUTH_TOKEN.format(error="HTTP 500") and link.status == SIGNED_OUT
    assert environ == {}


@pytest.mark.parametrize(
    ("granted", "said"),
    [
        ({"access_token": "a", "token_type": "mac"}, "chỉ hỗ trợ Bearer"),
        ({"access_token": "line\nbreak", "token_type": "Bearer"}, "Không lưu được token"),
        ({"token_type": "Bearer"}, "Đổi mã lấy token thất bại"),
    ],
    ids=["a token of another kind", "a token the env file cannot hold", "no token at all"],
)
async def test_a_grant_that_cannot_be_kept_is_not_half_kept(granted, said):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await asked(fake, environ=environ)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(200, json=granted) if str(request.url) == f"{AUTH}/token" else None
        ),
    )

    await sign_in.finish(hub, state, code)

    assert said in link.error and link.status == SIGNED_OUT
    assert environ == {} and link.auth is None


async def test_an_access_token_that_ran_out_is_renewed_and_the_call_made_once(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    session = hub.links["notion"].session
    fake.required = "the-old-one-ran-out"
    looked = len(gets(fake))

    result = await session.call_tool("create-page", {"title": "Báo cáo"})

    assert result["content"][0]["text"] == "ran create-page"
    assert fake.calls == [("create-page", {"title": "Báo cáo"})]
    # Where to renew was learnt at the sign-in; it is not looked up again for each one.
    assert len(gets(fake)) == looked
    assert fake.token_requests[-1] == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "client_id": "client-1",
        "resource": "https://mcp.example.test",
    }
    kept = {ACCESS: "access-2", REFRESH: "refresh-2", CLIENT: "client-1", ISSUER: AUTH}
    assert environ == kept and read_env(env_path(tmp_path)) == kept
    assert fake.seen[-1].headers["authorization"] == "Bearer access-2"


async def test_calls_refused_together_renew_once_between_them():
    """The refresh token is good once. A second call renewing with the one the first
    already spent would be told no, and sign the whole server out."""
    fake = FakeMcp(oauth=True)
    hub = await signed_in(fake)
    session = hub.links["notion"].session
    fake.required, fake.delay = "the-old-one-ran-out", 0.01

    results = await asyncio.gather(
        session.call_tool("search", {"query": "a"}),
        session.call_tool("search", {"query": "b"}),
        session.call_tool("search", {"query": "c"}),
    )

    assert [r["content"][0]["text"] for r in results] == ["ran search"] * 3
    renewals = [r for r in fake.token_requests if r["grant_type"] == "refresh_token"]
    assert len(renewals) == 1 and hub.links["notion"].status == CONNECTED
    assert sorted(arguments["query"] for _, arguments in fake.calls) == ["a", "b", "c"]


async def test_a_call_told_no_after_another_has_renewed_is_sent_again_with_what_that_one_got():
    """What it was refused for is the sign-in it was sent with. Renewing the one held now
    would spend a refresh token for nothing, and take the new access token away from the
    call that had just been given it."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    session = hub.links["notion"].session
    fake.required = "the-old-one-ran-out"
    late: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        response = await fake.handle(request)
        if response.status_code == 401 and not late:
            late.append(request)
            # This refusal is on its way for as long as the other call's renewal takes.
            while environ[ACCESS] == "access-1":
                await asyncio.sleep(0)
        return response

    hub.client = session.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))

    results = await asyncio.gather(
        session.call_tool("search", {"query": "a"}),
        session.call_tool("search", {"query": "b"}),
    )

    assert [r["content"][0]["text"] for r in results] == ["ran search"] * 2
    renewals = [r for r in fake.token_requests if r["grant_type"] == "refresh_token"]
    assert len(renewals) == 1 and hub.links["notion"].status == CONNECTED
    assert environ[ACCESS] == "access-2" and environ[REFRESH] == "refresh-2"
    assert late[0].headers["authorization"] == "Bearer access-1"


async def test_a_server_that_keeps_the_refresh_token_as_it_was_leaves_it_kept():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    fake.required = "ran-out"

    def renew_without_a_new_refresh_token(request: httpx.Request):
        if str(request.url) != f"{AUTH}/token":
            return None
        fake.required = "access-next"
        return httpx.Response(200, json={"access_token": "access-next", "token_type": "bearer"})

    intercepting(hub, fake, renew_without_a_new_refresh_token)

    await hub.links["notion"].session.call_tool("search", {})

    assert environ[ACCESS] == "access-next" and environ[REFRESH] == "refresh-1"


async def test_a_refresh_the_server_refuses_signs_the_server_out(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    fake.required = "ran-out"
    fake.refresh_tokens.clear()  # revoked at the server

    with pytest.raises(Unauthorized) as failure:
        await link.session.call_tool("create-page", {})

    assert str(failure.value) == t.MCP_UNAUTHORIZED.format(server="notion")
    assert fake.calls == [] and link.status == SIGNED_OUT
    assert fake.methods().count("tools/call") == 1  # not sent again with nothing to show
    # What can no longer sign in is not kept; the crew's name at that server is.
    assert environ == {CLIENT: "client-1"} and read_env(env_path(tmp_path)) == environ
    assert hub.waiting() == []  # only the owner can sign in again


async def test_calls_refused_together_are_none_of_them_sent_again_once_one_is_told_no():
    fake = FakeMcp(oauth=True)
    hub = await signed_in(fake)
    link = hub.links["notion"]
    fake.required, fake.delay = "ran-out", 0.01
    fake.refresh_tokens.clear()  # revoked at the server
    sent = len(fake.seen)

    results = await asyncio.gather(
        link.session.call_tool("search", {"query": "a"}),
        link.session.call_tool("search", {"query": "b"}),
        return_exceptions=True,
    )

    assert [type(result) for result in results] == [Unauthorized, Unauthorized]
    renewals = [r for r in fake.token_requests if r["grant_type"] == "refresh_token"]
    assert len(renewals) == 1 and link.status == SIGNED_OUT
    assert len(fake.seen) - sent == 2  # each was sent the once


async def test_a_sign_in_server_that_is_down_fails_the_call_and_keeps_the_sign_in():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    link = hub.links["notion"]
    fake.required = "ran-out"
    down = [True]
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(503, text="try later")
            if down[0] and str(request.url) == f"{AUTH}/token"
            else None
        ),
    )
    link.session.client = hub.client
    sent = len(fake.seen)

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert environ[REFRESH] == "refresh-1" and link.status == CONNECTED
    assert len(fake.seen) - sent == 1  # with no new token, sending it again is the same no
    down[0] = False
    result = await link.session.call_tool("search", {})
    assert result["content"][0]["text"] == "ran search" and environ[ACCESS] == "access-2"


async def test_a_sign_in_server_that_cannot_be_reached_is_not_a_refusal():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    fake.required = "ran-out"

    def unreachable(request: httpx.Request):
        if str(request.url) == f"{AUTH}/token":
            raise httpx.ConnectError("connection refused")
        return None

    intercepting(hub, fake, unreachable)
    hub.links["notion"].session.client = hub.client
    sent = len(fake.seen)

    with pytest.raises(Unauthorized):
        await hub.links["notion"].session.call_tool("search", {})

    assert environ[REFRESH] == "refresh-1" and hub.links["notion"].status == CONNECTED
    assert len(fake.seen) - sent == 1


def token_endpoint_says(hub: McpHub, fake: FakeMcp, status: int, **answer) -> list[bool]:
    """Makes the token endpoint answer with `status` for as long as the flag given back
    holds true."""
    saying = [True]
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(status, **answer)
            if saying[0] and str(request.url) == f"{AUTH}/token"
            else None
        ),
    )
    if hub.links["notion"].session is not None:
        hub.links["notion"].session.client = hub.client
    return saying


@pytest.mark.parametrize(
    ("status", "answer"),
    [
        (429, {"json": {"error": "slow_down"}}),
        (403, {"text": "<html>blocked on the way in</html>"}),
        (400, {"json": {"error": "temporarily_unavailable"}}),
        (400, {"json": {"error": "invalid_request", "error_description": "invalid_grant"}}),
        (400, {"text": "invalid_grant"}),
        (400, {"json": {"error": ["invalid_grant"]}}),
        (500, {"json": {"error": "invalid_grant"}}),
        (503, {"json": {"error": "invalid_grant"}}),
    ],
    ids=["too-many", "blocked", "busy", "unreadable", "no-json", "not-a-word", "broken", "down"],
)
async def test_only_a_no_to_the_grant_itself_ends_a_sign_in(status, answer, tmp_path: Path):
    """A token endpoint says no for many reasons that leave the refresh token as good as
    it was: too many requests, a wall in front of it, a request it could not read."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    fake.required = "ran-out"
    saying_no = token_endpoint_says(hub, fake, status, **answer)
    kept = dict(environ)

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert environ == kept and read_env(env_path(tmp_path)) == kept
    assert link.status == CONNECTED
    # The row says why, since the calls themselves only say the sign-in ran out.
    assert link.error.startswith(t.MCP_OAUTH_TOKEN.format(error=f"HTTP {status}"))
    saying_no[0] = False
    result = await link.session.call_tool("search", {})
    assert result["content"][0]["text"] == "ran search"
    assert environ[REFRESH] == "refresh-2" and link.error == ""


async def test_a_renewed_token_that_cannot_be_kept_leaves_the_sign_in_and_says_why(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    fake.required = "ran-out"
    granted = {"access_token": "line\nbreak", "refresh_token": "next", "token_type": "Bearer"}
    answering = token_endpoint_says(hub, fake, 200, json=granted)
    kept = dict(environ)

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert environ == kept and read_env(env_path(tmp_path)) == kept
    assert link.status == CONNECTED
    assert link.error.startswith(t.MCP_OAUTH_STORE.format(error=""))
    answering[0] = False
    await link.session.call_tool("search", {})
    assert environ[REFRESH] == "refresh-2" and link.error == ""


@pytest.mark.parametrize(
    ("status", "error"), [(400, "invalid_grant"), (401, "invalid_client"), (400, "invalid_client")]
)
async def test_a_no_to_the_grant_or_to_this_client_ends_the_sign_in(status, error):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    link = hub.links["notion"]
    fake.required = "ran-out"
    token_endpoint_says(hub, fake, status, json={"error": error})

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert link.status == SIGNED_OUT and ACCESS not in environ and REFRESH not in environ


def named_elsewhere(hub: McpHub, fake: FakeMcp, **granted: str) -> list[dict[str, str]]:
    """The server now says its sign-in is at another place, which this plays. What that
    place's token endpoint was sent."""
    publish(fake, RESOURCE_DOC, authorization_servers=[ELSEWHERE])
    fake.documents[f"{ELSEWHERE}/.well-known/oauth-authorization-server"] = {
        "issuer": ELSEWHERE,
        "authorization_endpoint": f"{ELSEWHERE}/authorize",
        "token_endpoint": f"{ELSEWHERE}/token",
        "registration_endpoint": f"{ELSEWHERE}/register",
        "code_challenge_methods_supported": ["S256"],
    }
    sent: list[dict[str, str]] = []

    def elsewhere(request: httpx.Request) -> httpx.Response | None:
        if str(request.url) == f"{ELSEWHERE}/register":
            return httpx.Response(201, json={"client_id": "client-elsewhere"})
        if str(request.url) == f"{ELSEWHERE}/token":
            sent.append(dict(parse_qsl(request.content.decode("utf-8"))))
            answer = {"access_token": "from-elsewhere", "token_type": "Bearer", **granted}
            return httpx.Response(200, json=answer)
        return None

    intercepting(hub, fake, elsewhere)
    if hub.links["notion"].session is not None:
        hub.links["notion"].session.client = hub.client
    return sent


def came_back(url: str) -> str:
    """The state a person sent to `url` comes back with."""
    return dict(parse_qsl(urlsplit(url).query))["state"]


def replacing(monkeypatch, fail: str = "") -> list[tuple[str, str]]:
    """Watches the env file being replaced, which with `fail` it cannot be. Each time it
    was tried."""
    tried, replace = [], os.replace

    def watched(src, dst):
        tried.append((str(src), str(dst)))
        if fail:
            raise OSError(fail)
        replace(src, dst)

    monkeypatch.setattr("my_agent_crew.env_file.os.replace", watched)
    return tried


def holding_renewals(hub: McpHub, fake: FakeMcp) -> tuple[asyncio.Event, asyncio.Event]:
    """Keeps a renewal at the door of the token endpoint until the second event is set;
    the first says one has got there."""
    arrived, go = asyncio.Event(), asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{AUTH}/token" and b"grant_type=refresh_token" in request.content:
            arrived.set()
            await go.wait()
        return await fake.handle(request)

    hub.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    hub.links["notion"].session.client = hub.client
    return arrived, go


async def test_a_refresh_token_is_said_only_where_it_was_granted(tmp_path: Path):
    """A server that was taken over can name any place as its sign-in. What the owner's
    own sign-in left here is never said there."""
    fake = FakeMcp(oauth=True)
    await signed_in(fake, environ={}, home=tmp_path)
    started: dict[str, str] = {}
    load_env_file(tmp_path, started)
    fake.required, asked_before = "ran-out", len(fake.token_requests)
    hub = make_hub(fake, environ=started, home=tmp_path)
    sent = named_elsewhere(hub, fake)

    await hub.connect()

    link = hub.links["notion"]
    assert sent == [] and len(fake.token_requests) == asked_before
    assert ("POST", f"{ELSEWHERE}/token") not in fake.fetched
    assert link.status == SIGNED_OUT and hub.waiting() == []
    assert link.error == t.MCP_OAUTH_MOVED.format(got=ELSEWHERE, expected=AUTH)
    assert started == {CLIENT: "client-1"} and read_env(env_path(tmp_path)) == started


async def test_a_refresh_token_is_not_said_elsewhere_in_the_middle_of_a_call():
    fake, environ = FakeMcp(oauth=True), {}
    await signed_in(fake, environ=environ)
    # Started again with a token that still opened the server, which then ran out.
    hub = make_hub(fake, environ=environ)
    await hub.connect()
    link = hub.links["notion"]
    assert link.status == CONNECTED and link.auth is None
    sent = named_elsewhere(hub, fake)
    fake.required = "ran-out"

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert sent == [] and len(fake.token_requests) == 1
    assert link.status == SIGNED_OUT and environ == {CLIENT: "client-1"}
    assert link.error == t.MCP_OAUTH_MOVED.format(got=ELSEWHERE, expected=AUTH)
    # Nothing learnt of the other place is kept either: the next look starts afresh.
    assert link.auth is None


async def test_a_refresh_token_with_no_word_of_where_it_was_granted_is_said_nowhere():
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    link = hub.links["notion"]
    del environ[ISSUER]
    fake.required, asked_before = "ran-out", len(fake.token_requests)

    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})

    assert len(fake.token_requests) == asked_before
    assert link.status == SIGNED_OUT and link.error == "" and environ == {CLIENT: "client-1"}


async def test_a_sign_in_begun_and_left_changes_nothing_of_the_one_in_use(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    kept, auth = dict(environ), link.auth
    sent = named_elsewhere(hub, fake)

    await sign_in.begin(hub, link, REDIRECT)  # and the owner never comes back

    assert environ == kept and read_env(env_path(tmp_path)) == kept and link.auth is auth
    fake.required = "ran-out"
    result = await link.session.call_tool("search", {})
    assert result["content"][0]["text"] == "ran search" and sent == []
    assert fake.token_requests[-1]["client_id"] == "client-1"
    assert fake.token_requests[-1]["refresh_token"] == "refresh-1"


async def test_a_sign_in_made_elsewhere_takes_the_place_of_the_one_kept_whole(
    tmp_path: Path, monkeypatch
):
    """The new place gave no refresh token. The one the old place gave is not left beside
    the new place's name, to be said there the first time its access token runs out."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    sent = named_elsewhere(hub, fake)
    state = came_back(await sign_in.begin(hub, link, REDIRECT))
    fake.required = "from-elsewhere"
    tried = replacing(monkeypatch)

    assert await sign_in.finish(hub, state, "a-code") == "notion"

    kept = {ACCESS: "from-elsewhere", CLIENT: "client-elsewhere", ISSUER: ELSEWHERE}
    assert environ == kept and read_env(env_path(tmp_path)) == kept
    # Written in one go: a crash between two writes would leave half of each sign-in.
    assert len(tried) == 1
    assert link.status == CONNECTED and link.auth.issuer == ELSEWHERE
    assert [form["grant_type"] for form in sent] == ["authorization_code"]
    fake.required = "ran-out"
    hub.links["notion"].session.client = hub.client
    with pytest.raises(Unauthorized):
        await link.session.call_tool("search", {})
    assert [form["grant_type"] for form in sent] == ["authorization_code"]
    assert link.status == SIGNED_OUT and len(fake.token_requests) == 1


async def test_a_new_sign_in_that_cannot_be_written_down_leaves_the_one_in_use_whole(
    tmp_path: Path, monkeypatch
):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    kept, auth = dict(environ), link.auth
    sent = named_elsewhere(hub, fake, refresh_token="refresh-elsewhere")
    state = came_back(await sign_in.begin(hub, link, REDIRECT))
    tried = replacing(monkeypatch, fail="no room left")

    await sign_in.finish(hub, state, "a-code")

    monkeypatch.undo()
    assert len(tried) == 1 and link.error == t.MCP_OAUTH_STORE.format(error="no room left")
    assert environ == kept and read_env(env_path(tmp_path)) == kept and link.auth is auth
    # What was in use still is, and is renewed where it was granted and nowhere else.
    fake.required = "ran-out"
    result = await link.session.call_tool("search", {})
    assert result["content"][0]["text"] == "ran search"
    assert fake.token_requests[-1]["refresh_token"] == "refresh-1"
    assert [form["grant_type"] for form in sent] == ["authorization_code"]


async def test_a_new_sign_in_that_cannot_be_kept_leaves_the_one_in_use_whole(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    kept, auth = dict(environ), link.auth
    named_elsewhere(hub, fake, refresh_token="line\nbreak")
    state = came_back(await sign_in.begin(hub, link, REDIRECT))

    await sign_in.finish(hub, state, "a-code")

    assert environ == kept and read_env(env_path(tmp_path)) == kept and link.auth is auth
    assert link.error.startswith(t.MCP_OAUTH_STORE.format(error=""))
    assert link.status == CONNECTED


async def test_the_owners_own_client_id_is_left_as_they_wrote_it(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {CLIENT: "registered-by-hand"}
    del fake.documents[AUTH_DOC]["registration_endpoint"]
    hub = await asked(fake, environ=environ, home=tmp_path)
    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))

    await sign_in.finish(hub, state, code)

    assert hub.links["notion"].status == CONNECTED
    assert environ[CLIENT] == "registered-by-hand" and environ[ISSUER] == AUTH
    # It was set for this run, not saved from the web: the file is not made to hold it.
    assert CLIENT not in read_env(env_path(tmp_path))


async def test_a_sign_in_that_cannot_be_renewed_as_the_crew_starts_is_kept_and_tried_again(
    tmp_path: Path,
):
    fake = FakeMcp(oauth=True)
    await signed_in(fake, environ={}, home=tmp_path)
    started: dict[str, str] = {}
    load_env_file(tmp_path, started)
    fake.required, kept = "ran-out", dict(started)
    hub = make_hub(fake, environ=started, home=tmp_path)
    saying_no = token_endpoint_says(hub, fake, 503)

    await hub.connect()

    link = hub.links["notion"]
    assert link.status == FAILED and hub.waiting() == ["notion"]
    assert link.error == t.MCP_OAUTH_TOKEN.format(error="HTTP 503")
    assert started == kept and read_env(env_path(tmp_path)) == kept
    saying_no[0] = False
    await hub.connect(hub.waiting())
    assert link.status == CONNECTED and link.error == "" and started[ACCESS] == "access-2"


async def test_a_server_that_refuses_a_token_just_renewed_wants_a_sign_in():
    fake, environ = FakeMcp(oauth=True), {}
    await signed_in(fake, environ=environ)
    hub = make_hub(fake, environ=environ)
    fake.required = "ran-out"
    answer = {"access_token": "not-what-it-wants", "token_type": "Bearer"}
    token_endpoint_says(hub, fake, 200, json=answer)

    await hub.connect()

    link = hub.links["notion"]
    assert link.status == SIGNED_OUT and link.error == "" and hub.waiting() == []


async def test_a_code_that_comes_back_from_another_place_is_not_traded():
    """A server can send the owner to another service's consent page and wait for the
    code. A place that says who it is when it sends them back is believed (RFC 9207)."""
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))

    assert await sign_in.finish(hub, state, code, iss=ELSEWHERE) == "notion"

    assert fake.token_requests == [] and link.status == SIGNED_OUT
    assert link.error == t.MCP_OAUTH_ISSUER.format(got=ELSEWHERE, expected=AUTH)
    # The state went with it: the code is not tried again under the right name.
    assert await sign_in.finish(hub, state, code, iss=AUTH) is None


async def test_a_code_that_comes_back_from_the_place_asked_is_traded():
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))

    await sign_in.finish(hub, state, code, iss=AUTH)

    assert hub.links["notion"].status == CONNECTED


@pytest.mark.parametrize(
    ("promised", "iss", "status", "said"),
    [
        (True, "", SIGNED_OUT, t.MCP_OAUTH_NO_ISS),
        (True, AUTH, CONNECTED, ""),
        ("false", "", CONNECTED, ""),
        (False, "", CONNECTED, ""),
    ],
    ids=["promised and missing", "promised and given", "a word that is not a yes", "not promised"],
)
async def test_a_place_that_says_it_will_name_itself_must(promised, iss, status, said):
    fake = FakeMcp(oauth=True)
    publish(fake, AUTH_DOC, authorization_response_iss_parameter_supported=promised)
    hub = await asked(fake)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))

    await sign_in.finish(hub, state, code, iss=iss)

    assert (link.status, link.error) == (status, said)
    assert len(fake.token_requests) == (1 if status == CONNECTED else 0)


async def test_a_sign_in_place_is_known_by_the_name_it_gives_itself(tmp_path: Path):
    """A server may spell its sign-in place with a slash the place itself does not use.
    What is kept, and what comes back with a code is held against, is the place's word."""
    fake = FakeMcp(oauth=True)
    publish(fake, RESOURCE_DOC, authorization_servers=[f"{AUTH}/"])
    hub = await asked(fake, environ={}, home=tmp_path)
    code, state = fake.approve(await sign_in.begin(hub, hub.links["notion"], REDIRECT))

    await sign_in.finish(hub, state, code, iss=AUTH)

    assert hub.links["notion"].status == CONNECTED
    started: dict[str, str] = {}
    load_env_file(tmp_path, started)
    assert started[ISSUER] == AUTH
    # Spelt the other way at the next start, it is still the place that granted it.
    publish(fake, RESOURCE_DOC, authorization_servers=[AUTH])
    fake.required = "ran-out"
    again = make_hub(fake, environ=started, home=tmp_path)
    await again.connect()
    assert again.links["notion"].status == CONNECTED and started[ACCESS] == "access-2"


async def test_the_names_of_a_place_and_of_who_came_back_are_cut_before_they_are_shown():
    fake = FakeMcp(oauth=True)
    place = f"{AUTH}/{'p' * 300}"
    publish(fake, RESOURCE_DOC, authorization_servers=[place])
    there = f"{AUTH}/.well-known/oauth-authorization-server/{'p' * 300}"
    fake.documents[there] = {**fake.documents[AUTH_DOC], "issuer": place}
    hub = await asked(fake)
    link = hub.links["notion"]
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    long = "https://" + "a" * 5000

    await sign_in.finish(hub, state, code, iss=long)

    assert link.error == t.MCP_OAUTH_ISSUER.format(got=long[:200], expected=place[:200])
    assert fake.token_requests == []


async def test_the_places_named_when_a_sign_in_has_moved_are_cut_before_they_are_shown():
    fake, environ = FakeMcp(oauth=True), {}
    await signed_in(fake, environ=environ)
    kept_under = environ[ISSUER] = "https://" + "k" * 300
    moved_to = f"{ELSEWHERE}/{'m' * 300}"
    publish(fake, RESOURCE_DOC, authorization_servers=[moved_to])
    there = f"{ELSEWHERE}/.well-known/oauth-authorization-server/{'m' * 300}"
    fake.documents[there] = {**fake.documents[AUTH_DOC], "issuer": moved_to}
    fake.required = "ran-out"
    hub = make_hub(fake, environ=environ)

    await hub.connect()

    link = hub.links["notion"]
    said = t.MCP_OAUTH_MOVED.format(got=moved_to[:200], expected=kept_under[:200])
    assert (link.status, link.error) == (SIGNED_OUT, said)
    assert len(fake.token_requests) == 1


async def test_a_renewal_on_its_way_does_not_write_over_the_sign_in_the_owner_comes_back_with(
    tmp_path: Path,
):
    """Whichever of the two ends last, what is kept is one sign-in: a refresh token is
    never left beside a client id it was not granted to."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    arrived, go = holding_renewals(hub, fake)
    fake.required = "ran-out"
    calling = asyncio.create_task(link.session.call_tool("search", {}))
    await arrived.wait()
    code, state = fake.approve(await sign_in.begin(hub, link, REDIRECT))
    finishing = asyncio.create_task(sign_in.finish(hub, state, code))
    async with asyncio.timeout(5):
        while len(fake.token_requests) < 2:  # the code is traded while the renewal waits
            await asyncio.sleep(0)

    go.set()
    _, finished = await asyncio.gather(calling, finishing, return_exceptions=True)

    assert finished == "notion" and link.status == CONNECTED
    assert environ[ISSUER] == AUTH and read_env(env_path(tmp_path)) == environ
    granted = fake.token_requests[int(environ[REFRESH].removeprefix("refresh-")) - 1]
    assert granted["client_id"] == environ[CLIENT] == "client-2"


async def test_a_renewal_on_its_way_does_not_sign_the_owner_back_in_after_they_sign_out(
    tmp_path: Path,
):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    link = hub.links["notion"]
    arrived, go = holding_renewals(hub, fake)
    fake.required = "ran-out"
    calling = asyncio.create_task(link.session.call_tool("search", {}))
    await arrived.wait()
    leaving = asyncio.create_task(hub.sign_out("notion"))
    await asyncio.sleep(0)

    go.set()
    _, left = await asyncio.gather(calling, leaving, return_exceptions=True)

    assert left is None and len(fake.token_requests) == 2
    assert environ == {CLIENT: "client-1"} and read_env(env_path(tmp_path)) == environ
    assert link.status == SIGNED_OUT and link.auth is None


async def test_a_server_that_was_down_and_now_wants_a_sign_in_no_longer_says_it_was_down():
    fake = FakeMcp(oauth=True)
    fake.before = lambda request, message: httpx.Response(503)
    hub = make_hub(fake)
    await hub.connect()
    link = hub.links["notion"]
    assert link.status == FAILED and link.error

    fake.before = None
    await hub.connect(hub.waiting())

    assert (link.status, link.error) == (SIGNED_OUT, "")


async def dripping():
    """A body that comes a byte at a time and never ends. Every byte is in time for a
    limit that is counted from the byte before it."""
    while True:
        yield b" "
        await asyncio.sleep(0.005)


async def test_a_token_endpoint_that_drips_its_answer_is_given_up_on(monkeypatch):
    """A renewal holds the server's lock. Left waiting, it would keep every call to that
    server, and the owner's sign-out, waiting behind it."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ)
    link = hub.links["notion"]
    fake.required = "ran-out"
    token_endpoint_says(hub, fake, 200, content=dripping())
    monkeypatch.setattr(oauth_discovery, "TIMEOUT_SECONDS", 0.05)
    kept = dict(environ)

    with pytest.raises(Unauthorized):
        await asyncio.wait_for(link.session.call_tool("search", {}), 3)

    assert environ == kept and link.status == CONNECTED and not link.renewing.locked()
    slow = t.MCP_OAUTH_SLOW.format(seconds=0.05)
    assert link.error == t.MCP_OAUTH_TOKEN.format(error=slow)


async def test_a_registration_that_drips_its_answer_is_given_up_on(monkeypatch):
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(201, content=dripping())
            if str(request.url) == f"{AUTH}/register"
            else None
        ),
    )
    monkeypatch.setattr(oauth_discovery, "TIMEOUT_SECONDS", 0.05)

    with pytest.raises(McpError) as failure:
        await asyncio.wait_for(sign_in.begin(hub, hub.links["notion"], REDIRECT), 3)

    slow = t.MCP_OAUTH_SLOW.format(seconds=0.05)
    assert str(failure.value) == t.MCP_OAUTH_REGISTER.format(error=slow)


async def test_a_document_that_drips_is_given_up_on_and_the_next_place_asked(monkeypatch):
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    intercepting(
        hub,
        fake,
        lambda request: (
            httpx.Response(200, content=dripping()) if str(request.url) == RESOURCE_DOC else None
        ),
    )
    fake.documents[HOST_DOC] = fake.documents[RESOURCE_DOC]
    monkeypatch.setattr(oauth_discovery, "TIMEOUT_SECONDS", 0.05)
    link = hub.links["notion"]

    found = await asyncio.wait_for(discover(hub.client, MCP_URL, link.challenge, hub.resolver), 3)

    # What the server publishes for its own path never came whole; what its host
    # publishes did.
    assert found.issuer == AUTH and gets(fake)[-2:] == [HOST_DOC, AUTH_DOC]


async def test_looking_for_a_sign_in_has_an_end_however_many_places_answer_late(monkeypatch):
    """Each place may take its time, and there are several: together they get one limit."""
    fake = FakeMcp(oauth=True)
    hub = await asked(fake)
    places: list[str] = []

    async def late_and_empty(request: httpx.Request) -> httpx.Response:
        places.append(str(request.url))
        await asyncio.sleep(0.05)
        return httpx.Response(404)

    hub.client = httpx.AsyncClient(transport=httpx.MockTransport(late_and_empty))
    monkeypatch.setattr(oauth_discovery, "DISCOVERY_SECONDS", 0.12)

    with pytest.raises(McpError) as failure:
        await asyncio.wait_for(sign_in.begin(hub, hub.links["notion"], REDIRECT), 3)

    slow = t.MCP_OAUTH_SLOW.format(seconds=0.12)
    assert str(failure.value) == t.MCP_OAUTH_DISCOVERY.format(error=slow)
    assert 0 < len(places) < 5  # five places would have been asked, a twentieth of a second each


async def test_signing_out_forgets_the_tokens_and_keeps_the_crews_name(tmp_path: Path):
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)

    await hub.sign_out("notion")

    link = hub.links["notion"]
    assert link.status == SIGNED_OUT and link.tools == () and link.auth is None
    assert environ == {CLIENT: "client-1"} and read_env(env_path(tmp_path)) == environ
    assert hub.describe({})[0]["signed_in"] is False
    assert MCP_URL in [url for _, url in fake.fetched[-1:]]  # it asked, and was refused


async def test_a_sign_out_that_cannot_be_written_down_leaves_the_sign_in_as_the_file_has_it(
    tmp_path: Path, monkeypatch
):
    """Forgotten here and read back at the next start, it would be a sign-out that lasts
    until the crew restarts."""
    fake, environ = FakeMcp(oauth=True), {}
    hub = await signed_in(fake, environ=environ, home=tmp_path)
    kept = dict(environ)
    tried = replacing(monkeypatch, fail="a home that cannot be written")

    await hub.sign_out("notion")

    assert len(tried) == 1 and environ == kept and read_env(env_path(tmp_path)) == kept
    assert hub.links["notion"].status == CONNECTED


async def test_a_sign_in_with_no_home_lasts_as_long_as_the_process():
    fake, environ = FakeMcp(oauth=True), {}

    await signed_in(fake, environ=environ)

    assert environ[ACCESS] == "access-1"
