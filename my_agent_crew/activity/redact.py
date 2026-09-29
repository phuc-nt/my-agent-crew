"""Covering secrets in text that is about to leave the process.

Two nets: the values of environment variables named like secrets, and the shapes common
keys take. A secret this process never held in its environment, in no recognisable shape
(read from a file, printed by a web page), passes through; callers say so to the reader
instead of promising more.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from my_agent_crew import texts

SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
# Shorter values are words like "true" or a port number: covering those everywhere would
# blank out ordinary text and hide nothing. A piece of a secret is covered from this long.
MIN_SECRET_CHARS = 8
ELLIPSIS = "…"
_BEARER = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_KEY_SHAPES = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"
)


def env_secrets(environ: Mapping[str, str]) -> list[str]:
    """Values of the variables whose name says they are secret, in each form a run's record
    may hold them (whitespace collapsed by a preview, escaped inside JSON, or both), longest
    first, so a secret that contains another is covered whole rather than leaving its tail."""
    found: set[str] = set()
    for name, value in environ.items():
        if SECRET_NAME.search(name) and len(value) >= MIN_SECRET_CHARS:
            escaped = json.dumps(value, ensure_ascii=False)[1:-1]
            forms = (value, escaped, *(" ".join(form.split()) for form in (value, escaped)))
            found.update(form for form in forms if len(form) >= MIN_SECRET_CHARS)
    return sorted(found, key=lambda value: (-len(value), value))


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        text = _cover_cuts(text.replace(secret, texts.TRAJECTORY_REDACTED), secret)
    text = _BEARER.sub(lambda match: match.group(1) + texts.TRAJECTORY_REDACTED, text)
    return _KEY_SHAPES.sub(texts.TRAJECTORY_REDACTED, text)


def redact_tree(value: Any, secrets: list[str]) -> Any:
    """Every string in a JSON-shaped value, keys included: tool arguments carry the keys a
    model wrote, and those can hold a secret as well as the values can."""
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {
            redact(key, secrets) if isinstance(key, str) else key: redact_tree(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_tree(item, secrets) for item in value]
    return value


def _cover_cuts(text: str, secret: str) -> str:
    """A run's record keeps previews, not whole texts. A cut through a secret leaves its head
    at the end of the text or before the ellipsis a preview adds, and an output kept from its
    end starts with the secret's tail; neither is the whole value an exact match looks for."""
    kept = _tail_at_start(text, secret)
    if kept:
        text = texts.TRAJECTORY_REDACTED + text[kept:]
    return ELLIPSIS.join(_without_head(piece, secret) for piece in text.split(ELLIPSIS))


def _without_head(text: str, secret: str) -> str:
    probe = secret[:MIN_SECRET_CHARS]
    at = text.find(probe, max(0, len(text) - len(secret) + 1))
    while at != -1:
        if secret.startswith(text[at:]):
            return text[:at] + texts.TRAJECTORY_REDACTED
        at = text.find(probe, at + 1)
    return text


def _tail_at_start(text: str, secret: str) -> int:
    """How many of the secret's last characters open the text, or 0 when too few do."""
    probe = secret[-MIN_SECRET_CHARS:]
    at = text.rfind(probe, 0, len(secret) - 1)
    while at != -1:
        kept = at + MIN_SECRET_CHARS
        if secret.endswith(text[:kept]):
            return kept
        at = text.rfind(probe, 0, kept - 1)
    return 0
