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
    forecast_prob: float | None = None,
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

    # Minimum stake per bet.
    if cost < limits.min_stake_cents_per_market:
        return RiskDecision(
            False,
            f"stake {cost}c is below the {limits.min_stake_cents_per_market}c minimum per bet "
            f"(${limits.min_stake_cents_per_market / 100:.0f}) — increase the number of contracts.",
        )

    # Net-EV gate. forecast_prob is the model's stated probability that the side
    # it is buying wins, so gross value per contract is forecast_prob*100c while
    # the market charges limit_price_cents + fee for it. We require the edge to
    # clear price AND fee by a margin -- this is what makes the bot pass on
    # fairly-priced markets instead of bleeding fees on coin-flips. (The stated
    # probability is Brier-scored after settlement, so inflating it to clear the
    # gate is punished on the public leaderboard.)
    if forecast_prob is not None:
        fee_per_contract = fee_cents / count if count else 0
        net_edge = forecast_prob * 100 - limit_price_cents - fee_per_contract
        if net_edge < limits.min_edge_cents_per_contract:
            return RiskDecision(
                False,
                f"net edge is {net_edge:.1f}c/contract (your {forecast_prob * 100:.0f}c fair value "
                f"minus the {limit_price_cents}c price and {fee_per_contract:.1f}c fee), under the "
                f"{limits.min_edge_cents_per_contract}c minimum — too close to fairly priced to beat "
                "the fee. Pass, or find a bigger mispricing.",
            )

    cash = ledger.cash(agent)
    # Cash must cover stake plus the trading fee. The position-size caps below
    # are measured on stake only -- the fee is an expense, not capital at risk.
    if cost + fee_cents > cash:
        return RiskDecision(
            False,
            f"order costs {cost}c + {fee_cents}c fee but you only have {cash}c cash available.",
        )

    equity = ledger.equity(agent)

    # Per-market maximum: what's already staked on this ticker plus the new order.
    existing_on_ticker = sum(
        o["cost_cents"] for o in ledger.open_orders(agent) if o["ticker"] == ticker
    )
    if existing_on_ticker + cost > limits.max_stake_cents_per_market:
        return RiskDecision(
            False,
            f"stake on {ticker} would be {existing_on_ticker + cost}c, exceeding the "
            f"per-market cap of {limits.max_stake_cents_per_market}c "
            f"(${limits.max_stake_cents_per_market / 100:.0f}).",
        )

    # Weekly new-position cap (0 = unlimited). Entering a market you already hold
    # doesn't count as a new position.
    if limits.max_new_positions_per_week > 0 and ticker not in ledger.open_tickers(agent):
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
