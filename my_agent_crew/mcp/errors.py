"""What goes wrong in a call to an MCP server, each kind told apart by who can mend it."""

from __future__ import annotations


class McpError(Exception):
    """A call to a server that did not work, in words the model and the owner can read."""


class Unauthorized(McpError):
    """The server wants a sign-in, or the one it was shown has run out. `challenge` is what
    it said of where to get one, `sent` the authorization the refused request carried."""

    def __init__(self, message: str, challenge: str = "", sent: str = ""):
        super().__init__(message)
        self.challenge = challenge
        self.sent = sent


class SessionGone(McpError):
    """The server no longer knows the session the request named. The request did not run."""
