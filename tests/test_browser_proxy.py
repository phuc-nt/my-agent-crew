"""The proxy every crew browser goes out through: it refuses private addresses by the address
a name resolves to, connects only to an address it checked, serves nobody without the
password of its launch and carries one request per plain connection. No browser here: each
test speaks to the proxy as a client would."""

from __future__ import annotations

import asyncio
import base64

import pytest

from my_agent_crew.browser.proxy import MARK, USER, FilteringProxy
from tests.browser_servers import Recorder, ask, only, sites


def auth(proxy: FilteringProxy, password: str | None = None) -> bytes:
    secret = proxy.launch_option["password"] if password is None else password
    token = base64.b64encode(f"{USER}:{secret}".encode()).decode()
    return f"Proxy-Authorization: Basic {token}\r\n".encode()


def get(proxy: FilteringProxy, url: str, extra: bytes = b"") -> bytes:
    host = url.split("/")[2]
    return f"GET {url} HTTP/1.1\r\nHost: {host}\r\n".encode() + auth(proxy) + extra + b"\r\n"


@pytest.fixture
async def started():
    """Starts proxies and stops each one when the test is over."""
    made: list[FilteringProxy] = []

    async def start(**settings) -> FilteringProxy:
        proxy = FilteringProxy(**settings)
        await proxy.start()
        made.append(proxy)
        return proxy

    yield start
    for proxy in made:
        await proxy.stop()


async def test_the_real_rule_refuses_a_local_server_and_never_connects_to_it(started):
    """No exemption is passed, as in the product: the server on this machine stands for the
    crew's own API or a router's admin page."""
    proxy = await started()
    with sites({"/secret": "bí mật"}) as [intranet]:
        plain = await ask(proxy.port, get(proxy, intranet.url("/secret")))
        target = f"127.0.0.1:{intranet.port}".encode()
        tunnel = await ask(
            proxy.port, b"CONNECT " + target + b" HTTP/1.1\r\n" + auth(proxy) + b"\r\n"
        )
        named = await ask(proxy.port, get(proxy, f"http://localhost:{intranet.port}/secret"))

        assert plain.startswith(b"HTTP/1.1 403 ") and "bí mật".encode() not in plain
        assert tunnel.startswith(b"HTTP/1.1 403 ")
        assert named.startswith(b"HTTP/1.1 403 ")
        assert intranet.seen == []
    assert list(proxy.refused) == ["127.0.0.1", "127.0.0.1", "localhost"]
    assert proxy.refused_total == 3


async def test_a_name_that_points_inwards_is_refused_by_the_address_it_resolves_to(started):
    names = {"shop.test": ["8.8.8.8", "127.0.0.1"], "nowhere.test": []}
    proxy = await started(resolver=lambda host: names[host])

    mixed = await ask(proxy.port, get(proxy, "http://shop.test/"))
    empty = await ask(proxy.port, get(proxy, "http://nowhere.test/"))

    assert mixed.startswith(b"HTTP/1.1 403 ") and empty.startswith(b"HTTP/1.1 403 ")
    assert list(proxy.refused) == ["shop.test", "nowhere.test"]


async def test_a_name_nobody_resolves_is_a_bad_gateway_and_not_a_refusal(started):
    def resolver(host: str) -> list[str]:
        raise OSError("no such host")

    proxy = await started(resolver=resolver)

    answer = await ask(proxy.port, get(proxy, "http://gone.test/"))

    assert answer.startswith(b"HTTP/1.1 502 ")
    assert proxy.refused_total == 0


async def test_the_proxy_signs_its_own_answers_and_no_answer_of_a_site(started):
    """A refusal and a site's own 403 read the same to a browser. The line the proxy adds to
    what it says itself is how the two are told apart."""
    sign = f"{MARK}: 1".encode()

    def resolver(host: str) -> list[str]:
        if host == "gone.test":
            raise OSError("no such host")
        return ["127.0.0.1"]

    with sites({"/cam": lambda site: (403, {}, "cấm")}) as [shop]:
        proxy = await started(resolver=resolver, allow=only(shop))

        own = await ask(proxy.port, get(proxy, shop.url("/cam")))
        refused = await ask(proxy.port, get(proxy, "http://127.0.0.1:9/"))
        gone = await ask(proxy.port, get(proxy, "http://gone.test/"))
        stranger = await ask(proxy.port, b"GET http://x.test/ HTTP/1.1\r\nHost: x.test\r\n\r\n")

    assert own.startswith(b"HTTP/1.1 403 ") and sign not in own.lower()
    assert refused.startswith(b"HTTP/1.1 403 ") and sign in refused.split(b"\r\n\r\n")[0]
    assert gone.startswith(b"HTTP/1.1 502 ") and sign in gone.split(b"\r\n\r\n")[0]
    assert stranger.startswith(b"HTTP/1.1 407 ") and sign in stranger.split(b"\r\n\r\n")[0]


async def test_a_request_goes_to_the_address_that_was_checked_and_not_to_the_name_again(started):
    """The name is resolved once, here, and the connection is made to what came back: a
    name that answers differently the second time gets no second answer."""
    asked: list[str] = []

    def resolver(host: str) -> list[str]:
        asked.append(host)
        return ["127.0.0.1"] if len(asked) == 1 else ["10.0.0.5"]

    with sites({"/don": "đơn hàng"}) as [shop]:
        proxy = await started(resolver=resolver, allow=only(shop))

        answer = await ask(proxy.port, get(proxy, f"http://shop.test:{shop.port}/don?x=1"))

        assert answer.startswith(b"HTTP/1.1 200 ") and "đơn hàng".encode() in answer
        assert shop.seen == ["GET /don?x=1"]
    assert asked == ["shop.test"]


async def test_the_site_is_not_told_what_was_said_to_the_proxy(started):
    with sites({"/": "ok"}) as [shop]:
        proxy = await started(allow=only(shop))
        extra = b"Proxy-Connection: keep-alive\r\nConnection: keep-alive\r\nCookie: a=1\r\n"

        await ask(proxy.port, get(proxy, shop.url("/"), extra))

        [head] = shop.heads
    assert "proxy-authorization" not in head and "proxy-connection" not in head
    assert (head["connection"], head["cookie"], head["host"]) == (
        "close",
        "a=1",
        f"127.0.0.1:{shop.port}",
    )


async def test_a_body_is_passed_on_whole(started):
    with sites({"/form": "đã nhận"}) as [shop]:
        proxy = await started(allow=only(shop))
        body = "tên=Phở".encode()
        head = f"POST {shop.url('/form')} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n"

        answer = await ask(proxy.port, head.encode() + auth(proxy) + b"\r\n" + body)

        assert answer.startswith(b"HTTP/1.1 200 ")
        assert (shop.seen, shop.bodies) == (["POST /form"], [body])


async def test_a_second_request_on_the_same_connection_is_never_passed_on(started):
    """It would reach the first host under another host's name, and carry the proxy's
    password to it."""
    with sites({"/": "một"}, {"/secret": "hai"}) as [shop, other]:
        proxy = await started(allow=only(shop, other))

        answer = await ask(
            proxy.port, get(proxy, shop.url("/")), more=get(proxy, other.url("/secret"))
        )

        assert answer.count(b"HTTP/1.1 200 ") == 1 and b"hai" not in answer
        assert (shop.seen, other.seen) == (["GET /"], [])
        assert all("proxy-authorization" not in head for head in shop.heads)


async def test_what_follows_a_request_is_dropped_even_by_a_site_that_keeps_the_line_open(started):
    """`Connection: close` asks the site to hang up; this one does not. The second request
    is still never sent to it."""
    async with Recorder() as site:
        proxy = await started(allow=only(site))
        first = get(proxy, f"http://127.0.0.1:{site.port}/one")
        second = get(proxy, f"http://127.0.0.1:{site.port}/two")

        answer = await ask(proxy.port, first, more=second)

        assert answer.startswith(b"HTTP/1.1 200 OK")
        assert site.received.startswith(b"GET /one HTTP/1.1\r\n")
        assert b"/two" not in site.received and b"Proxy-Authorization" not in site.received


async def test_a_tunnel_carries_bytes_both_ways_to_the_checked_address(started):
    with sites({"/ws": "qua đường hầm"}) as [shop]:
        proxy = await started(allow=only(shop))
        connect = f"CONNECT 127.0.0.1:{shop.port} HTTP/1.1\r\n".encode() + auth(proxy) + b"\r\n"
        inner = b"GET /ws HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"

        answer = await ask(proxy.port, connect, more=inner)

        assert answer.startswith(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        assert "qua đường hầm".encode() in answer
        assert shop.seen == ["GET /ws"]


@pytest.mark.parametrize("password", ["", "wrong", "crew"])
async def test_nobody_is_served_without_the_password_of_this_launch(started, password):
    with sites({"/": "ok"}) as [shop]:
        proxy = await started(allow=only(shop))
        url = shop.url("/").encode()
        bare = b"GET " + url + b" HTTP/1.1\r\nHost: x\r\n\r\n"
        wrong = b"GET " + url + b" HTTP/1.1\r\nHost: x\r\n" + auth(proxy, password) + b"\r\n"
        tunnel = f"CONNECT 127.0.0.1:{shop.port} HTTP/1.1\r\n".encode() + auth(proxy, password)

        answers = [await ask(proxy.port, raw) for raw in (bare, wrong, tunnel + b"\r\n")]

        assert all(a.startswith(b"HTTP/1.1 407 ") for a in answers)
        assert all(b"Proxy-Authenticate: Basic" in a for a in answers)
        assert shop.seen == []


async def test_two_launches_do_not_share_a_password(started):
    one, two = await started(), await started()

    assert one.launch_option["password"] != two.launch_option["password"]
    assert len(one.launch_option["password"]) >= 24
    assert one.launch_option["server"] == f"http://127.0.0.1:{one.port}"


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (b"GET ftp://shop.test/a HTTP/1.1\r\n", b"400"),
        (b"GET /only-a-path HTTP/1.1\r\n", b"400"),
        (b"POST http://shop.test/ HTTP/1.1\r\nTransfer-Encoding: chunked\r\n", b"411"),
        (b"POST http://shop.test/ HTTP/1.1\r\nContent-Length: many\r\n", b"411"),
    ],
)
async def test_what_is_no_request_it_can_carry_is_answered_and_not_passed_on(started, raw, status):
    proxy = await started(resolver=lambda host: ["8.8.8.8"])

    answer = await ask(proxy.port, raw + auth(proxy) + b"\r\n")

    assert answer.startswith(b"HTTP/1.1 " + status)


async def test_noise_and_a_client_that_hangs_up_leave_the_proxy_serving(started):
    with sites({"/": "vẫn chạy"}) as [shop]:
        proxy = await started(allow=only(shop))

        assert await ask(proxy.port, b"\x16\x03\x01\x02\r\n\r\n") == b""
        assert await ask(proxy.port, b"GET") == b""
        assert (await ask(proxy.port, b"\x16 not http\r\n\r\n")).startswith(b"HTTP/1.1 407 ")
        assert await ask(proxy.port, b"x" * 70_000 + b"\r\n\r\n") == b""
        answer = await ask(proxy.port, get(proxy, shop.url("/")))

        assert "vẫn chạy".encode() in answer


async def test_the_refusals_since_a_mark_are_the_recent_ones(started):
    proxy = await started(resolver=lambda host: ["10.0.0.5"])
    await ask(proxy.port, get(proxy, "http://a.test/"))
    mark = proxy.refused_total

    assert proxy.refused_since(mark) == []
    await ask(proxy.port, get(proxy, "http://b.test/"))
    await ask(proxy.port, get(proxy, "http://c.test/"))

    assert proxy.refused_since(mark) == ["b.test", "c.test"]
    assert proxy.refused_since(0) == ["a.test", "b.test", "c.test"]


async def test_stopping_closes_the_door_and_the_tunnels_that_were_open(started):
    with sites({"/": "ok"}) as [shop]:
        proxy = await started(allow=only(shop))
        port = proxy.port
        connect = f"CONNECT 127.0.0.1:{shop.port} HTTP/1.1\r\n".encode() + auth(proxy) + b"\r\n"
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(connect)
        assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200 ")

        await asyncio.wait_for(proxy.stop(), 5)
        await proxy.stop()  # twice is once

        assert await asyncio.wait_for(reader.read(), 5) == b""
        writer.close()
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)
