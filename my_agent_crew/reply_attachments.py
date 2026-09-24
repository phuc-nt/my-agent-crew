"""How a reply names a file to send: the two line prefixes and the size a chat will take.

Shared by the channels that deliver a reply and the delegate tool that carries a child's
attachments over to its parent, so it lives outside both packages."""

from __future__ import annotations

MEDIA_PREFIX = "MEDIA:"
FILE_PREFIX = "FILE:"

# Telegram refuses a document over 50 MB, but the cap here is lower on purpose: it is a
# chat, and a file this size is one a person would rather fetch from the workspace page
# than receive twice on a phone.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
