"""What a conversation has cost so far: dollars when the provider priced the call, else a
count of calls whose cost nobody reported."""

from __future__ import annotations

from my_agent_crew.store.models import Conversation
from my_agent_crew.store.stamps import now_iso


class Spending:
    """Mixed into `Store`, whose `_update_returning` runs the UPDATE and reads the row back."""

    def add_spend(
        self, conv_id: str, cost_usd: float | None, *, touch: bool = True
    ) -> Conversation:
        column = (
            "spent_usd = spent_usd + ?"
            if cost_usd is not None
            else "unknown_cost_calls = unknown_cost_calls + ?"
        )
        amount = cost_usd if cost_usd is not None else 1
        stamp, params = (", updated_at = ?", (amount, now_iso())) if touch else ("", (amount,))
        return self._update_returning(
            f"UPDATE conversations SET {column}{stamp} WHERE id = ? RETURNING *",
            (*params, conv_id),
        )
