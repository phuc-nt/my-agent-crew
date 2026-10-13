"""Which addresses a crew browser may reach. Decided on the address a name resolves to, never
on the name, and stricter than the page fetcher's rule: anything that is not a public address
is refused, the shared range a private overlay network hands out included. A hard refusal:
no setting, approval or agent file reaches it."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from my_agent_crew import texts_browser as t
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.web import Resolver, is_private

# A test's own server, by address and port. The product never passes one.
Allow = Callable[[str, int], bool]
PORTS = {"http": 80, "https": 443}
# IPv6 written around an IPv4 address in its last four bytes: mapped, the old compatible
# form, and the prefix a NAT64 gateway translates.
CARRIES_IPV4 = tuple(ipaddress.ip_network(n) for n in ("::ffff:0:0/96", "::/96", "64:ff9b::/96"))


def _carried(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    """The IPv4 address an IPv6 one stands for, in the forms a host or a gateway turns back
    into it; any other address is itself."""
    if ip.version == 6 and any(ip in net for net in CARRIES_IPV4):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def is_local(address: str) -> bool:
    """Whether an address is anything but a public one. An IPv4 address written inside an
    IPv6 one is judged as the IPv4 address it reaches."""
    try:
        ip = _carried(ipaddress.ip_address(address.split("%", 1)[0]))
    except ValueError:
        return True  # what cannot be read is not let through
    return is_private(str(ip)) or not ip.is_global


def reachable(addresses: Sequence[str], port: int, allow: Allow | None = None) -> bool:
    """A name is reached only when every address it resolves to may be: one private address
    among public ones is how a name is made to point inwards."""
    if not addresses:
        return False
    return all(not is_local(a) or (allow is not None and allow(a, port)) for a in addresses)


async def check_url(url: str, resolver: Resolver, allow: Allow | None = None) -> str:
    """The host of a page a tab is about to be sent to, or the words that refuse it. The
    proxy decides again for every connection the page makes; this says so before a tab is
    opened, in words the model can act on."""
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port or PORTS.get(parts.scheme, 0)
    except ValueError as exc:
        raise ToolError(t.URL_SCHEME) from exc
    if parts.scheme not in PORTS or not host:
        raise ToolError(t.URL_SCHEME)
    try:
        addresses = await asyncio.to_thread(resolver, host)
    except OSError as exc:
        raise ToolError(t.URL_UNREACHABLE.format(host=host, error=exc)) from exc
    if not reachable(addresses, port, allow):
        raise ToolError(t.URL_PRIVATE.format(host=host))
    return host
