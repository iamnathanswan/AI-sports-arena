"""Weekly settlement: resolve finished markets, reconcile live fills,
and compute the leaderboard consumed by the dashboard.

Runs before agents bet each week. For every open order:
  - live orders: reconcile against actual Kalshi fills (refund what never filled)
  - settled markets: pay out winners at 100c/contract via the ledger
  - dry-run (paper) orders: assume a full fill at the limit price, settle against
    the market's real public result — a faithful paper-trading simulation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .kalshi.client import KalshiClient, KalshiError
from .ledger import Ledger

SETTLED_STATUSES = ("settled", "finalized")


def _order_expired(order: dict, expiration_minutes: int) -> bool:
    placed = datetime.fromisoformat(order["placed_at"])
    return datetime.now(timezone.utc) > placed + timedelta(minutes=expiration_minutes)


def _filled_count(kalshi: KalshiClient, order: dict) -> int:
    """How many contracts of a live order actually filled, per Kalshi fills."""
    kalshi_order_id = order.get("kalshi_order_id")
    if not kalshi_order_id:
        return 0
    try:
        fills = kalshi.get_fills(ticker=order["ticker"])
    except KalshiError:
        return order["count"]  # can't verify — assume filled rather than refund wrongly
    return sum(f.get("count", 0) for f in fills if f.get("order_id") == kalshi_order_id)


def settle_open_orders(ledger: Ledger, kalshi: KalshiClient, settings: Settings) -> list[dict]:
    """Returns a list of settlement events (for logging)."""
    events: list[dict] = []
    market_cache: dict[str, dict[str, Any]] = {}

    for order in list(ledger.open_orders()):
        ticker = order["ticker"]
        if ticker not in market_cache:
            try:
                market_cache[ticker] = kalshi.get_market(ticker)
            except KalshiError as exc:
                events.append({"order": order["id"], "action": "skipped", "why": str(exc)})
                market_cache[ticker] = {}
                continue
        market = market_cache[ticker]
        if not market:
            continue

        status = (market.get("status") or "").lower()
        result = (market.get("result") or "").lower()
        is_settled = status in SETTLED_STATUSES or result in ("yes", "no")

        # Live orders: reconcile actual fills once the order can no longer fill
        # (market settled, or the limit order has expired).
        if order["status"] == "live" and (
            is_settled or _order_expired(order, settings.risk.order_expiration_minutes)
        ):
            filled = _filled_count(kalshi, order)
            if filled < order["count"]:
                refund = ledger.refund_unfilled(order, filled)
                events.append(
                    {
                        "order": order["id"],
                        "agent": order["agent"],
                        "ticker": ticker,
                        "action": "refund_unfilled",
                        "refund_cents": refund,
                        "filled": filled,
                    }
                )
            if order.get("result") == "unfilled":
                continue  # nothing filled; order is closed

        if not is_settled:
            continue

        won = result == order["side"]
        payout = ledger.settle_order(order, won=won)
        events.append(
            {
                "order": order["id"],
                "agent": order["agent"],
                "ticker": ticker,
                "action": "settled",
                "result": "won" if won else "lost",
                "payout_cents": payout,
            }
        )
    return events


def build_leaderboard(ledger: Ledger, settings: Settings, generated_at: str) -> dict:
    agents = []
    for spec in settings.agents:
        name = spec.name
        if name not in ledger.data["agents"]:
            continue
        settled = [
            o
            for o in ledger.data["orders"]
            if o["agent"] == name and o.get("result") in ("won", "lost")
        ]
        wins = [o for o in settled if o["result"] == "won"]
        staked = sum(o["cost_cents"] for o in settled)
        returned = sum(o["payout_cents"] for o in settled)
        briers = [
            (o["forecast_prob"] - (1.0 if o["result"] == "won" else 0.0)) ** 2
            for o in settled
            if o.get("forecast_prob") is not None
        ]
        equity = ledger.equity(name)
        initial = ledger.initial(name)
        agents.append(
            {
                "name": name,
                "provider": spec.provider,
                "model": spec.model,
                "equity_cents": equity,
                "cash_cents": ledger.cash(name),
                "initial_cents": initial,
                "pnl_cents": equity - initial,
                "roi_pct": round((equity - initial) / initial * 100, 2) if initial else 0,
                "settled_bets": len(settled),
                "wins": len(wins),
                "win_rate": round(len(wins) / len(settled), 3) if settled else None,
                "staked_cents": staked,
                "returned_cents": returned,
                "brier": round(sum(briers) / len(briers), 4) if briers else None,
                "open_positions": [
                    {
                        "ticker": o["ticker"],
                        "title": o["market_title"],
                        "side": o["side"],
                        "contracts": o["count"],
                        "cost_cents": o["cost_cents"],
                        "forecast_prob": o["forecast_prob"],
                    }
                    for o in ledger.open_orders(name)
                ],
            }
        )
    agents.sort(key=lambda a: a["equity_cents"], reverse=True)

    bets = [
        {
            "agent": o["agent"],
            "week": o["week"],
            "ticker": o["ticker"],
            "title": o["market_title"],
            "side": o["side"],
            "contracts": o["count"],
            "price_cents": o["limit_price_cents"],
            "cost_cents": o["cost_cents"],
            "forecast_prob": o["forecast_prob"],
            "reasoning": o["reasoning"],
            "status": o["status"],
            "result": o["result"],
            "payout_cents": o["payout_cents"],
            "placed_at": o["placed_at"],
        }
        for o in sorted(ledger.data["orders"], key=lambda o: o["placed_at"], reverse=True)
    ]

    return {
        "generated_at": generated_at,
        "dry_run": settings.dry_run,
        "kalshi_env": settings.kalshi_env,
        "agents": agents,
        "history": ledger.data["history"],
        "bets": bets,
        "notes": sorted(ledger.data["notes"], key=lambda n: n["at"], reverse=True),
    }
