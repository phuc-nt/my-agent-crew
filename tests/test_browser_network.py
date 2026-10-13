"""Which addresses a crew browser may reach: nothing that is not public, read from the address
and never from the name, and stricter than the page fetcher. And what `browser_navigate` says
of an address before a tab is opened."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.browser.network import always_refused, check_url, is_local, reachable
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.web import is_private

PUBLIC = {
    "shop.test": ["8.8.8.8"],
    "v6.test": ["2001:4860:4860::8888"],
    "xn--bcher-kva.test": ["8.8.4.4"],
}


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.8.9.10",
        "10.0.0.5",
        "172.16.3.1",
        "192.168.1.10",
        "169.254.169.254",  # the metadata address of a cloud machine
        "100.64.0.1",  # the shared range an overlay network hands out
        "0.0.0.0",
        "198.18.0.1",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fe80::1%lo0",
        "fd00::1",
        "ff02::1",
        "2001:db8::1",
    ],
)
def test_an_address_that_is_not_public_is_local(address):
    assert is_local(address)


@pytest.mark.parametrize(
    "address",
    [
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.5",
        "::ffff:100.64.0.1",
        "::127.0.0.1",
        "::192.168.1.10",
        "64:ff9b::7f00:1",
        "64:ff9b::c0a8:10a",
        "2002:7f00:1::",
    ],
)
def test_a_private_address_written_inside_an_ipv6_one_is_still_local(address):
    assert is_local(address)


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888", "::ffff:8.8.8.8", "64:ff9b::808:808"],
)
def test_a_public_address_is_not_local(address):
    assert not is_local(address)


@pytest.mark.parametrize("text", ["", "not an address", "8.8.8", "8.8.8.8.8", "127.1", "1e3"])
def test_what_does_not_read_as_an_address_is_not_let_through(text):
    assert is_local(text)


def test_the_browser_refuses_a_range_the_page_fetcher_lets_through():
    """Why the browser has a rule of its own: a logged-in browser on an overlay network is
    worth more to a hostile page than one anonymous fetch."""
    assert not is_private("100.64.0.1")
    assert is_local("100.64.0.1")


def test_a_name_is_reached_only_when_every_address_it_resolves_to_may_be():
    assert reachable(["8.8.8.8", "2001:4860:4860::8888"], 443)
    assert not reachable(["8.8.8.8", "10.0.0.5"], 443)
    assert not reachable(["10.0.0.5", "8.8.8.8"], 443)
    assert not reachable([], 443)


def test_an_exemption_names_a_port_and_covers_nothing_else():
    """Only tests pass one: their own server, by its port."""
    shop = lambda address, port: port == 8080  # noqa: E731

    assert reachable(["127.0.0.1"], 8080, shop)
    assert not reachable(["127.0.0.1"], 8081, shop)
    assert not reachable(["127.0.0.1", "10.0.0.5"], 8081, shop)
    assert reachable(["127.0.0.1", "8.8.8.8"], 8080, shop)


@pytest.mark.parametrize(
    ("url", "given"),
    [
        ("https://shop.test/don-hang?id=1#top", "https://shop.test/don-hang?id=1#top"),
        ("http://SHOP.test.:8080/", "http://shop.test.:8080/"),
        ("https://v6.test", "https://v6.test"),
        ("https://bücher.test/", "https://xn--bcher-kva.test/"),
    ],
)
async def test_a_public_page_is_let_through_spelled_as_the_browser_is_given_it(url, given):
    assert await check_url(url, PUBLIC.__getitem__) == given


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "chrome://settings",
        "about:blank",
        "javascript:alert(1)",
        "data:text/html,<p>x",
        "view-source:https://shop.test/",
        "ftp://shop.test/a",
        "ws://shop.test/",
        "shop.test/don-hang",
        "https://",
        "https://shop.test:port/",
        "http://[::1",
        "//shop.test/don-hang",
        "https://user:secret@shop.test/",
        "https://evil.test\\@shop.test/",
        "https://shop.test%2eevil.test/",
        "https://shop.test /",
        "",
    ],
)
async def test_only_a_full_http_address_is_opened(url):
    asked: list[str] = []

    def resolver(host: str) -> list[str]:
        asked.append(host)
        return ["8.8.8.8"]

    with pytest.raises(ToolError) as refused:
        await check_url(url, resolver)

    assert str(refused.value) == t.URL_SCHEME
    assert asked == []
    assert always_refused(url)


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://127.0.0.1:8765/api/agents", "127.0.0.1"),
        ("http://10.0.0.5/", "10.0.0.5"),
        ("https://169.254.169.254/latest/meta-data/", "169.254.169.254"),
        ("http://100.64.0.1/", "100.64.0.1"),
        ("http://[::1]:8765/", "::1"),
        ("http://[fd00::1]/", "fd00::1"),
        ("http://localhost:8765/", "localhost"),
        ("http://LOCALHOST./", "localhost"),
        ("http://shop.localhost:3000/", "shop.localhost"),
    ],
)
async def test_a_private_address_written_out_is_refused_with_no_name_resolved(url, host):
    """It is this machine or its network whatever a resolver says of it, one that lies
    included, and is known to be refused before the call is made."""
    asked: list[str] = []

    def resolver(name: str) -> list[str]:
        asked.append(name)
        return ["8.8.8.8"]

    with pytest.raises(ToolError) as refused:
        await check_url(url, resolver)

    assert str(refused.value) == t.URL_PRIVATE.format(host=host)
    assert asked == []
    assert always_refused(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://shop.test/",
        "https://router.test/admin",  # private, but only resolving its name says so
        "https://nowhere.test/",
        "http://8.8.8.8/",
        "http://[2001:4860:4860::8888]/",
        "http://notlocalhost/",
        "http://localhost.evil.test/",
    ],
)
def test_an_address_only_resolving_can_refuse_is_not_called_refused_beforehand(url):
    assert not always_refused(url)


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://127.0.0.1:8765/api/agents", "127.0.0.1"),
        ("http://localhost:8765/", "localhost"),
        ("http://[::1]:8765/", "::1"),
        ("https://router.test/admin", "router.test"),
        ("https://mixed.test/", "mixed.test"),
        ("https://nowhere.test/", "nowhere.test"),
    ],
)
async def test_a_page_at_a_private_address_is_refused_by_name(url, host):
    names = {
        "127.0.0.1": ["127.0.0.1"],
        "localhost": ["127.0.0.1", "::1"],
        "::1": ["::1"],
        "router.test": ["192.168.1.1"],
        "mixed.test": ["8.8.8.8", "10.0.0.5"],
        "nowhere.test": [],
    }

    with pytest.raises(ToolError) as refused:
        await check_url(url, names.__getitem__)

    assert str(refused.value) == t.URL_PRIVATE.format(host=host)


async def test_a_name_nobody_resolves_is_said_to_be_that_and_not_private():
    def resolver(host: str) -> list[str]:
        raise OSError("nodename nor servname provided")

    with pytest.raises(ToolError) as refused:
        await check_url("https://gone.test/", resolver)

    assert str(refused.value) == t.URL_UNREACHABLE.format(
        host="gone.test", error="nodename nor servname provided"
    )


async def test_a_test_server_is_let_through_only_on_the_port_it_was_given():
    local = lambda host: ["127.0.0.1"]  # noqa: E731
    shop = lambda address, port: port == 8080  # noqa: E731

    assert await check_url("http://shop.test:8080/", local, shop) == "http://shop.test:8080/"
    with pytest.raises(ToolError):
        await check_url("http://shop.test:8081/", local, shop)
    with pytest.raises(ToolError):
        await check_url("http://shop.test/", local, shop)  # port 80
    # Written out, it is known beforehand to be refused on any other port and on no other.
    assert not always_refused("http://127.0.0.1:8080/", shop)
    assert not always_refused("http://localhost:8080/", shop)
    assert await check_url("http://localhost:8080/", local, shop) == "http://localhost:8080/"
    assert always_refused("http://127.0.0.1:8081/", shop)
    assert always_refused("http://localhost/", shop)
    assert always_refused("http://127.0.0.1:8080/")
