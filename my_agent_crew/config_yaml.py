"""What `config.yaml` may hold and how it is read. Only `config.py` uses this; a wrong key in
the file is a mistake worth stopping for, not a value silently ignored.
"""

from __future__ import annotations

from pathlib import Path

import yaml

YAML_KEYS = (
    "routes",
    "vision_routes",
    "audio_routes",
    "cost_cap_usd",
    "language",
    "timezone",
    "web_url",
    "max_steps",
    "autonomous_default",
    "shell_ask_patterns",
    "shell_allow_patterns",
    "approval_ttl_seconds",
    "tool_output_chars",
    "openrouter_providers",
    "openrouter_provider_fallbacks",
    "mcp_servers",
)


def from_yaml(home: Path) -> dict:
    path = home / "config.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = set(data) - set(YAML_KEYS)
    if unknown:
        raise ValueError(f"config.yaml: unknown keys {sorted(unknown)}")
    return data
