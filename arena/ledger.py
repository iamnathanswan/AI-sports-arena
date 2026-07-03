"""Per-agent virtual bankroll ledger.

All agents trade through one Kalshi account; this ledger is the source of truth
for which agent owns which order, how much cash each agent has left, and each
bet's forecast/reasoning (used for Brier scoring on the dashboard).

Money is tracked in integer cents. A buy order debits its full cost when placed
(reserved); settlement credits the payout (win) or nothing (loss), and refunds
any unfilled portion of live orders.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OPEN_STATUSES = ("dry_run", "live")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, data: dict[str, Any] | None = None):
        self.data: dict[str, Any] = data or {
            "created_at": _now(),
            "agents": {},
            "orders": [],
            "notes": [],
            "history": [],
        }

    # ----- persistence -----

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        if path.exists():
            return cls(json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2) + "\n")

    # ----- agents -----

    def ensure_agent(self, name: str, initial_cents: int) -> None:
        if name not in self.data["agents"]:
            self.data["agents"][name] = {
                "initial_cents": initial_cents,
                "cash_cents": initial_cents,
            }

    def record_usage(self, agent: str, usage: dict, cost_cents: int) -> None:
        """Accumulate a session's token usage and API cost for `agent`. This is
        tracked separately from the betting bankroll -- token cost is never
        deducted from cash_cents."""
        totals = self.data["agents"][agent].setdefault(
            "usage",
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
                "cost_cents": 0,
                "sessions": 0,
            },
        )
        for key in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
            totals[key] += int(usage.get(key, 0) or 0)
        totals["cost_cents"] += cost_cents
        totals["sessions"] += 1

    def usage_totals(self, agent: str) -> dict:
        return self.data["agents"][agent].get(
            "usage",
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
                "cost_cents": 0,
                "sessions": 0,
            },
        )

    def cash(self, agent: str) -> int:
        return self.data["agents"][agent]["cash_cents"]

    def initial(self, agent: str) -> int:
        return self.data["agents"][agent]["initial_cents"]

    def open_orders(self, agent: str | None = None) -> list[dict]:
        return [
            o
            for o in self.data["orders"]
            if o["status"] in OPEN_STATUSES
            and o.get("result") is None
            and (agent is None or o["agent"] == agent)
        ]

    def open_cost(self, agent: str) -> int:
        return sum(o["cost_cents"] for o in self.open_orders(agent))

    def equity(self, agent: str) -> int:
        """Cash plus capital tied up in open positions (valued at cost)."""
        return self.cash(agent) + self.open_cost(agent)

    def open_tickers(self, agent: str) -> set[str]:
        return {o["ticker"] for o in self.open_orders(agent)}

    def new_positions_in_week(self, agent: str, week: str) -> int:
        tickers = {
            o["ticker"]
            for o in self.data["orders"]
            if o["agent"] == agent and o["week"] == week and o["status"] in OPEN_STATUSES
        }
        return len(tickers)

    # ----- orders -----

    def record_order(
        self,
        agent: str,
        week: str,
        ticker: str,
        market_title: str,
        side: str,
        count: int,
        limit_price_cents: int,
        status: str,  # "dry_run" | "live"
        forecast_prob: float,
        reasoning: str,
        kalshi_order_id: str | None = None,
        client_order_id: str | None = None,
        fee_cents: int = 0,
    ) -> dict:
        cost = count * limit_price_cents
        total = cost + fee_cents
        if total > self.cash(agent):
            raise ValueError(
                f"{agent} has {self.cash(agent)}c cash, order costs {cost}c + {fee_cents}c fee"
            )
        order = {
            "id": str(uuid.uuid4()),
            "agent": agent,
            "week": week,
            "ticker": ticker,
            "market_title": market_title,
            "side": side,
            "count": count,
            "limit_price_cents": limit_price_cents,
            "cost_cents": cost,
            "fee_cents": fee_cents,
            "status": status,
            "kalshi_order_id": kalshi_order_id,
            "client_order_id": client_order_id,
            "forecast_prob": forecast_prob,
            "reasoning": reasoning,
            "placed_at": _now(),
            "result": None,
            "payout_cents": 0,
            "settled_at": None,
        }
        self.data["agents"][agent]["cash_cents"] -= total
        self.data["orders"].append(order)
        return order

    def get_order(self, order_id: str) -> dict | None:
        return next((o for o in self.data["orders"] if o["id"] == order_id), None)

    def refund_unfilled(self, order: dict, filled_count: int) -> int:
        """Live order partially/never filled: shrink the position to what filled
        and return the reserved cash (and the estimated fee) for the rest.
        Fees are only charged on contracts that actually fill. Returns total
        cents refunded (stake + fee)."""
        original_count = order["count"]
        unfilled = max(original_count - filled_count, 0)
        stake_refund = unfilled * order["limit_price_cents"]

        original_fee = order.get("fee_cents", 0)
        if original_count > 0:
            kept_fee = round(original_fee * filled_count / original_count)
        else:
            kept_fee = 0
        fee_refund = original_fee - kept_fee

        refund = stake_refund + fee_refund
        if refund > 0:
            self.data["agents"][order["agent"]]["cash_cents"] += refund
        if unfilled > 0:
            order["count"] = filled_count
            order["cost_cents"] = filled_count * order["limit_price_cents"]
            order["fee_cents"] = kept_fee
        if filled_count == 0:
            order["result"] = "unfilled"
            order["settled_at"] = _now()
        return refund

    def settle_order(self, order: dict, won: bool) -> int:
        """Market settled: pay out 100c per contract on a win. Returns payout cents."""
        payout = order["count"] * 100 if won else 0
        order["result"] = "won" if won else "lost"
        order["payout_cents"] = payout
        order["settled_at"] = _now()
        if payout:
            self.data["agents"][order["agent"]]["cash_cents"] += payout
        return payout

    # ----- notes & history -----

    def record_note(self, agent: str, week: str, text: str) -> None:
        self.data["notes"].append({"agent": agent, "week": week, "text": text, "at": _now()})

    def snapshot(self, date: str) -> None:
        balances = {name: self.equity(name) for name in self.data["agents"]}
        # Replace an existing snapshot for the same date (re-runs shouldn't duplicate).
        self.data["history"] = [h for h in self.data["history"] if h["date"] != date]
        self.data["history"].append({"date": date, "balances": balances})
        self.data["history"].sort(key=lambda h: h["date"])
