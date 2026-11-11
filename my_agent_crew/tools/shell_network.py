"""Where a shell command would send something, read from the command before it runs.

An autonomous agent's commands run unasked, and a command that talks to a server can carry
anything the agent has read to it. So a command that runs a network program stops for a
person unless every host it names is one of the agent's `outbound_hosts`; one that names no
host that can be read (`curl "$URL"`) stops too. A program that runs code (`python`, `node`)
counts when the command also spells an address.

A soft guard, like the ask list: it reads the words of one command. A script written in one
call and run in the next names no address here; what holds for that is the sandbox
(`shell_network: false`), which is why an agent kept offline is not read at all."""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence

from my_agent_crew.browser.policy import host_allowed

# Programs whose whole job is to reach another machine.
FETCHERS = frozenset({"curl", "wget", "http", "https", "xh", "aria2c"})
# The same, naming the machine as a bare word or as `user@host`.
REMOTES = frozenset({"ssh", "scp", "sftp", "telnet", "ftp", "nc", "ncat", "netcat"})
# Programs that run code or speak a protocol when told to: read only beside an address.
RUNNERS = frozenset(
    {"node", "ruby", "perl", "php", "deno", "bun", "bunx", "npx", "uv", "uvx", "pipx"}
    | {"git", "openssl", "socat", "osascript", "pwsh"}
)
# Words that stand before the program they run.
WRAPPERS = frozenset({"sudo", "env", "time", "nohup", "exec", "command", "xargs", "nice"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
IMPLICIT = {"gh": "github.com"}
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})
BREAKS = "();<>|&`\n"

URL = re.compile(r"(?<![a-z0-9+.-])(?!file:)[a-z][a-z0-9+.-]*://([^\s/'\"?#\\)>]*)", re.IGNORECASE)
DEV_TCP = re.compile(r"/dev/(?:tcp|udp)/([^/\s]+)/")
AT_HOST = re.compile(r"^[^@\s/]*@([^:/\s]+)")
HOST_PATH = re.compile(r"^([A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}):")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PYTHON = re.compile(r"^python[0-9.]*$")
# Nothing is told apart from an address that could not be read.
UNREAD = ""


def _segments(command: str) -> list[list[str]]:
    """The simple commands of a line, each as its words. A line the shell's own rules cannot
    split (a quote left open) is split on blanks, which reads more as a program, not less."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=BREAKS)
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    try:
        words = list(lexer)
    except ValueError:
        words = re.split(r"[ \t\r]+|([();<>|&`\n]+)", command)
    segments: list[list[str]] = [[]]
    for word in words:
        if not word:
            continue
        if word[0] in BREAKS:
            segments.append([])
        elif bare := word.removeprefix("$"):
            segments[-1].append(bare)
    return [segment for segment in segments if segment]


def _program(words: Sequence[str]) -> tuple[str, Sequence[str]]:
    """The program a simple command runs and the words after it, past what is set for it and
    the words that only run another program."""
    at = 0
    while at < len(words):
        word = words[at]
        name = word.rsplit("/", 1)[-1].lower()
        if ASSIGNMENT.match(word) or name in WRAPPERS or (at and word.startswith("-")):
            at += 1
            continue
        return name, words[at + 1 :]
    return "", ()


def _host(spelled: str) -> str:
    """A host without its port, its name before `@` or its brackets, in lower case."""
    host = spelled.rsplit("@", 1)[-1].lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.split(":", 1)[0].rstrip(".")


def _url_hosts(text: str) -> list[str]:
    return [_host(found) or UNREAD for found in URL.findall(text)] + [
        _host(found) for found in DEV_TCP.findall(text)
    ]


def _named(args: Sequence[str]) -> list[str]:
    """Every machine written as `user@host` or `host:path`."""
    found = (m for a in args for m in (AT_HOST.match(a), HOST_PATH.match(a)) if m)
    return [_host(m.group(1)) for m in found]


def _remote_hosts(args: Sequence[str]) -> list[str]:
    """The machines a remote program is pointed at: every `user@host` and `host:path`, else
    the first word that is no option. An option's own value may be read as the machine; the
    call then asks, which is the safe way to be wrong."""
    if named := _named(args):
        return named
    bare = [a for a in args if not a.startswith("-")]
    return [_host(bare[0])] if bare else [UNREAD]


def _destinations(command: str) -> list[str] | None:
    """The hosts a command would reach, `UNREAD` for one it names in no way to be read, or
    None for a command that runs no network program."""
    hosts: list[str] = []
    networked = runner = False
    for segment in _segments(command):
        name, args = _program(segment)
        if name in SHELLS and "-c" in args:
            inner = _destinations(" ".join(args[args.index("-c") + 1 :]))
            if inner is not None:
                networked, hosts = True, hosts + inner
            continue
        text = " ".join(args)
        if name in FETCHERS:
            networked, hosts = True, hosts + (_url_hosts(text) or [UNREAD])
        elif name in REMOTES:
            networked, hosts = True, hosts + _remote_hosts(args)
        elif name in IMPLICIT:
            networked, hosts = True, [*hosts, IMPLICIT[name]]
        elif name == "rsync":
            found = _named(args) + _url_hosts(text)
            networked, hosts = networked or bool(found), hosts + found
        elif name == "git" and "push" in args:
            networked, hosts = True, hosts + (_url_hosts(text) or _named(args) or [UNREAD])
        elif name in RUNNERS or PYTHON.match(name):
            runner = True
    if DEV_TCP.search(command):
        networked = True
    if runner or DEV_TCP.search(command):
        found = _url_hosts(command)
        networked, hosts = networked or bool(found), hosts + found
    return hosts if networked else None


def unlisted_host(command: str, allowed: Sequence[str]) -> str | None:
    """None for a command that reaches no machine but this one and the agent's own hosts.
    Else the first host it names outside them, or "" when it runs a network program and
    names no host that can be read."""
    hosts = _destinations(command)
    if hosts is None:
        return None
    listed = [pattern.lower() for pattern in allowed]
    for host in hosts:
        if host in LOOPBACK or host.startswith("127."):
            continue
        if host == UNREAD or not host_allowed(host, listed):
            return host
    return None
