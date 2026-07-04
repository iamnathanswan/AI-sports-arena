"""Shared options passed into every provider adapter.

Bundling these into one object keeps the adapter signatures stable and makes
the cost-control levers (effort, search cap, cost ceiling, in-session retry)
uniform across providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class RunOptions:
    # Reasoning effort applied identically to every model: "low" | "medium" |
    # "high". Lower effort = fewer thinking tokens (billed at the output rate),
    # the biggest cost lever that still preserves the model's ability to research.
    effort: str | None = None

    # Soft cap on native web searches per session (told to the model in the
    # prompt; also a hard cap on Anthropic via max_uses).
    max_searches: int | None = None

    # Hard per-session spend ceiling in cents. After each turn the adapter
    # computes running cost via cost_of(usage); if it reaches budget_cents the
    # session stops. A backstop against runaway loops, not a tight leash.
    budget_cents: int | None = None
    cost_of: Callable[[dict], int] | None = None

    # In-session mandatory-bet retry: if, when the model naturally ends its
    # turn, should_continue() is True, the adapter appends followup_prompt as a
    # new user turn and keeps going in the SAME conversation (reusing the
    # research it already paid for and cached) instead of a fresh second run.
    followup_prompt: str | None = None
    should_continue: Callable[[], bool] | None = None

    def over_budget(self, usage: dict) -> bool:
        if not self.budget_cents or not self.cost_of:
            return False
        return self.cost_of(usage) >= self.budget_cents

    def wants_followup(self) -> bool:
        return bool(self.followup_prompt and self.should_continue and self.should_continue())
