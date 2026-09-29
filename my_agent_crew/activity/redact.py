"""Covering secrets in text that is about to leave the process.

Two nets: the values of environment variables named like secrets, and the shapes common
keys take. A secret this process never held in its environment, in no recognisable shape
(read from a file, printed by a web page), passes through; callers say so to the reader
instead of promising more.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from my_agent_crew import texts

SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
# Shorter values are words like "true" or a port number: covering those everywhere would
# blank out ordinary text and hide nothing.
MIN_SECRET_CHARS = 8
_BEARER = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_KEY_SHAPES = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"
)


def env_secrets(environ: Mapping[str, str]) -> list[str]:
    """Values of the variables whose name says they are secret, longest first, so a secret
    that contains another is covered whole rather than leaving its tail."""
    found = {
        value
        for name, value in environ.items()
        if SECRET_NAME.search(name) and len(value) >= MIN_SECRET_CHARS
    }
    return sorted(found, key=lambda value: (-len(value), value))


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, texts.TRAJECTORY_REDACTED)
    text = _BEARER.sub(lambda match: match.group(1) + texts.TRAJECTORY_REDACTED, text)
    return _KEY_SHAPES.sub(texts.TRAJECTORY_REDACTED, text)


def redact_tree(value: Any, secrets: list[str]) -> Any:
    """Every string in a JSON-shaped value, covered; keys are the exporter's own and stay."""
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {key: redact_tree(item, secrets) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_tree(item, secrets) for item in value]
    return value
