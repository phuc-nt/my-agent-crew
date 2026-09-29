"""What the crew says about how long an approval waits for a person."""

from __future__ import annotations

APPROVAL_TTL_INVALID = (
    "{where}: approval_ttl_seconds phải là số giây nguyên, từ {low} đến {high} (không đặt "
    "trong ngoặc kép), không phải {value!r}."
)
