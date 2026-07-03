"""Token cost calculation. Prices come from config/settings.yaml per agent
(dollars per 1M tokens) -- edit those if a provider changes prices.

This is a separate ledger from the betting bankroll: token cost is a real
expense of running the arena, but it is never deducted from an agent's
$100 stake -- the two are tracked and displayed independently.
"""

from __future__ import annotations

from .config import AgentSpec

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens")


def empty_usage() -> dict[str, int]:
    return {key: 0 for key in USAGE_KEYS}


def add_usage(total: dict[str, int], delta: dict[str, int] | None) -> None:
    """Accumulate `delta` into `total` in place. Missing keys default to 0."""
    if not delta:
        return
    for key in USAGE_KEYS:
        total[key] = total.get(key, 0) + int(delta.get(key, 0) or 0)


def compute_cost_cents(spec: AgentSpec, usage: dict[str, int]) -> int:
    """Cost in integer cents for the given token usage, at `spec`'s prices."""
    dollars = (
        usage.get("input_tokens", 0) * spec.price_per_million_input
        + usage.get("output_tokens", 0) * spec.price_per_million_output
        + usage.get("cache_write_tokens", 0) * spec.price_per_million_cache_write
        + usage.get("cache_read_tokens", 0) * spec.price_per_million_cache_read
    ) / 1_000_000
    return round(dollars * 100)
