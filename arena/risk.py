"""Hard risk limits, enforced in code on every order.

The models are *told* these limits in the system prompt, but nothing here
trusts a model: every place_bet call is validated against the agent's ledger
and these rules, and rejected orders never reach Kalshi.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RiskLimits
from .ledger import Ledger


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def check_order(
    ledger: Ledger,
    limits: RiskLimits,
    agent: str,
    week: str,
    ticker: str,
    count: int,
    limit_price_cents: int,
    kill_switch: bool = False,
    fee_cents: int = 0,
) -> RiskDecision:
    if kill_switch:
        return RiskDecision(False, "KILL_SWITCH is active — all order placement is halted.")

    if count < 1:
        return RiskDecision(False, "count must be at least 1 contract.")

    if not (limits.min_price_cents <= limit_price_cents <= limits.max_price_cents):
        return RiskDecision(
            False,
            f"limit price {limit_price_cents}c is outside the allowed range "
            f"{limits.min_price_cents}-{limits.max_price_cents}c.",
        )

    cost = count * limit_price_cents
    cash = ledger.cash(agent)
    # Cash must cover stake plus the trading fee. The position-size caps below
    # are measured on stake only -- the fee is an expense, not capital at risk.
    if cost + fee_cents > cash:
        return RiskDecision(
            False,
            f"order costs {cost}c + {fee_cents}c fee but you only have {cash}c cash available.",
        )

    equity = ledger.equity(agent)

    # Per-market cap counts what's already staked on this ticker plus the new order.
    existing_on_ticker = sum(
        o["cost_cents"] for o in ledger.open_orders(agent) if o["ticker"] == ticker
    )
    market_cap = int(equity * limits.max_stake_pct_per_market / 100)
    if existing_on_ticker + cost > market_cap:
        return RiskDecision(
            False,
            f"stake on {ticker} would be {existing_on_ticker + cost}c, exceeding the "
            f"per-market cap of {market_cap}c ({limits.max_stake_pct_per_market:.0f}% of equity).",
        )

    # Weekly new-position cap (entering a market you already hold doesn't count).
    if ticker not in ledger.open_tickers(agent):
        if ledger.new_positions_in_week(agent, week) >= limits.max_new_positions_per_week:
            return RiskDecision(
                False,
                f"you already opened {limits.max_new_positions_per_week} new positions "
                "this week (the weekly maximum).",
            )

    # Total deployment cap.
    deploy_cap = int(equity * limits.max_deployed_pct / 100)
    if ledger.open_cost(agent) + cost > deploy_cap:
        return RiskDecision(
            False,
            f"total deployed capital would be {ledger.open_cost(agent) + cost}c, exceeding "
            f"the cap of {deploy_cap}c ({limits.max_deployed_pct:.0f}% of equity).",
        )

    return RiskDecision(True)
