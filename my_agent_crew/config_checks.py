"""What a whole `Settings` must satisfy before a server starts on it. Checked once it is read,
so a bad number or an unknown zone stops the start, not the first turn or the first job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent_crew.clock import zone_for

if TYPE_CHECKING:
    from my_agent_crew.config import Settings


def checked(settings: Settings) -> Settings:
    positive = (settings.max_steps, settings.approval_ttl_seconds, settings.tool_output_chars)
    if min(positive) < 1 or settings.cost_cap_usd < 0:
        raise ValueError(
            "max_steps, approval_ttl_seconds and tool_output_chars must be >= 1, cost_cap_usd >= 0"
        )
    zone_for(settings.timezone)  # an unknown zone fails here, not in the first job
    return settings
