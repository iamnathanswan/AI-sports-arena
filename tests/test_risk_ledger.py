"""Unit tests for the virtual ledger and the hard risk limits."""

import pytest

from arena.config import RiskLimits
from arena.ledger import Ledger
from arena.risk import check_order

LIMITS = RiskLimits(
    min_stake_cents_per_market=1000,
    max_stake_cents_per_market=2000,
    max_new_positions_per_week=0,  # unlimited by default
    max_deployed_pct=50,
    min_price_cents=5,
    max_price_cents=95,
)
WEEK = "2026-07-06"


def limits_with_weekly_cap(cap=5):
    return RiskLimits(
        min_stake_cents_per_market=1000,
        max_stake_cents_per_market=2000,
        max_new_positions_per_week=cap,
        max_deployed_pct=50,
        min_price_cents=5,
        max_price_cents=95,
    )


def make_ledger(cash=10000):
    ledger = Ledger()
    ledger.ensure_agent("claude", cash)
    return ledger


def place(ledger, ticker="MLB-GAME-1", count=10, price=50, agent="claude", status="dry_run"):
    return ledger.record_order(
        agent=agent,
        week=WEEK,
        ticker=ticker,
        market_title=ticker,
        side="yes",
        count=count,
        limit_price_cents=price,
        status=status,
        forecast_prob=0.6,
        reasoning="test",
    )


class TestRisk:
    def test_allows_reasonable_order(self):
        ledger = make_ledger()
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 30, 50)  # 1500c

    def test_kill_switch_blocks_everything(self):
        ledger = make_ledger()
        decision = check_order(ledger, LIMITS, "claude", WEEK, "T1", 1, 50, kill_switch=True)
        assert not decision and "KILL_SWITCH" in decision.reason

    def test_price_bounds(self):
        ledger = make_ledger()
        assert not check_order(ledger, LIMITS, "claude", WEEK, "T1", 1, 3)
        assert not check_order(ledger, LIMITS, "claude", WEEK, "T1", 1, 97)
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 250, 5)  # 1250c
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 15, 95)  # 1425c

    def test_below_minimum_stake_rejected(self):
        ledger = make_ledger()
        # 10 contracts @ 50c = 500c, under the $10 (1000c) per-bet minimum.
        decision = check_order(ledger, LIMITS, "claude", WEEK, "T1", 10, 50)
        assert not decision and "minimum" in decision.reason
        # One more contract clears the minimum.
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 20, 50)  # 1000c exactly

    def test_edge_gate_rejects_fair_value_bet(self):
        ledger = make_ledger()
        # 30 @ 50c clears the stake floor, but a 50% fair value on a 50c price is
        # zero edge -> rejected by the net-EV gate.
        decision = check_order(
            ledger, LIMITS, "claude", WEEK, "T1", 30, 50, forecast_prob=0.50
        )
        assert not decision and "net edge" in decision.reason

    def test_edge_gate_rejects_thin_edge(self):
        ledger = make_ledger()
        # 52c fair value vs 50c price = 2c edge, under the 3c minimum.
        decision = check_order(
            ledger, LIMITS, "claude", WEEK, "T1", 30, 50, forecast_prob=0.52
        )
        assert not decision and "net edge" in decision.reason

    def test_edge_gate_allows_real_edge(self):
        ledger = make_ledger()
        # 60c fair value vs 50c price = 10c edge, well over the minimum.
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 30, 50, forecast_prob=0.60)

    def test_edge_gate_skipped_without_forecast(self):
        # When no forecast is supplied the gate is inert (back-compat path).
        ledger = make_ledger()
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 30, 50)

    def test_insufficient_cash(self):
        ledger = make_ledger(cash=900)
        # 1000c stake clears the minimum but exceeds available cash.
        decision = check_order(ledger, LIMITS, "claude", WEEK, "T1", 20, 50)
        assert not decision and "cash" in decision.reason

    def test_per_market_cap(self):
        ledger = make_ledger()  # cap 2000c per market
        assert check_order(ledger, LIMITS, "claude", WEEK, "T1", 40, 50)  # 2000c ok
        decision = check_order(ledger, LIMITS, "claude", WEEK, "T1", 41, 50)  # 2050c
        assert not decision and "per-market cap" in decision.reason

    def test_per_market_cap_counts_existing_stake(self):
        ledger = make_ledger()
        place(ledger, ticker="T1", count=30, price=50)  # 1500c on T1 already
        decision = check_order(ledger, LIMITS, "claude", WEEK, "T1", 20, 50)  # +1000c = 2500c
        assert not decision and "per-market cap" in decision.reason

    def test_weekly_cap_disabled_by_default(self):
        # With max_new_positions_per_week = 0 the weekly cap never blocks.
        ledger = make_ledger(cash=1000000)
        for i in range(10):
            place(ledger, ticker=f"T{i}", count=20, price=50)  # 1000c each
        assert check_order(ledger, LIMITS, "claude", WEEK, "T-new", 20, 50)

    def test_weekly_position_cap(self):
        limits = limits_with_weekly_cap(5)
        ledger = make_ledger(cash=1000000)
        for i in range(5):
            place(ledger, ticker=f"T{i}", count=5, price=50)
        decision = check_order(ledger, limits, "claude", WEEK, "T-new", 30, 50)  # 1500c
        assert not decision and "new positions" in decision.reason
        # Adding to an existing position is still allowed by this rule.
        assert check_order(ledger, limits, "claude", WEEK, "T0", 30, 50)

    def test_unfilled_orders_do_not_consume_weekly_slots(self):
        # An agent whose 5 resting orders never filled (all refunded) must not
        # stay locked out -- those never became positions.
        limits = limits_with_weekly_cap(5)
        ledger = make_ledger(cash=100000)
        for i in range(5):
            order = place(ledger, ticker=f"T{i}", count=5, price=50, status="live")
            ledger.refund_unfilled(order, filled_count=0)  # nothing filled
        assert ledger.new_positions_in_week("claude", WEEK) == 0
        # ...so the agent can enter a new market again.
        assert check_order(ledger, limits, "claude", WEEK, "T-fresh", 30, 50)  # 1500c

    def test_deployment_cap(self):
        limits = RiskLimits(
            min_stake_cents_per_market=1000,
            max_stake_cents_per_market=2000,
            max_new_positions_per_week=0,
            max_deployed_pct=50,
        )
        ledger = make_ledger()
        place(ledger, ticker="T1", count=40, price=50)  # 2000c deployed
        place(ledger, ticker="T2", count=40, price=50)  # 4000c deployed
        # equity still 10000, cap 5000c -> another 2000c order would exceed at 6000c
        decision = check_order(ledger, limits, "claude", WEEK, "T3", 40, 50)
        assert not decision and "deployed" in decision.reason
        assert check_order(ledger, limits, "claude", WEEK, "T3", 20, 50)  # 1000c -> 5000c ok


class TestLedger:
    def test_debit_on_place_and_credit_on_win(self):
        ledger = make_ledger()
        order = place(ledger, count=10, price=50)  # 500c
        assert ledger.cash("claude") == 9500
        assert ledger.equity("claude") == 10000
        payout = ledger.settle_order(order, won=True)
        assert payout == 1000
        assert ledger.cash("claude") == 10500
        assert ledger.equity("claude") == 10500

    def test_loss_pays_nothing(self):
        ledger = make_ledger()
        order = place(ledger, count=10, price=50)
        ledger.settle_order(order, won=False)
        assert ledger.cash("claude") == 9500
        assert ledger.equity("claude") == 9500
        assert order["result"] == "lost"

    def test_refund_unfilled(self):
        ledger = make_ledger()
        order = place(ledger, count=10, price=50, status="live")
        refund = ledger.refund_unfilled(order, filled_count=4)
        assert refund == 300
        assert ledger.cash("claude") == 9800
        assert order["count"] == 4 and order["cost_cents"] == 200

    def test_fully_unfilled_closes_order(self):
        ledger = make_ledger()
        order = place(ledger, count=10, price=50, status="live")
        ledger.refund_unfilled(order, filled_count=0)
        assert ledger.cash("claude") == 10000
        assert order["result"] == "unfilled"
        assert ledger.open_orders("claude") == []

    def test_cannot_overspend(self):
        ledger = make_ledger(cash=100)
        with pytest.raises(ValueError):
            place(ledger, count=10, price=50)

    def test_attribution_and_snapshot(self):
        ledger = make_ledger()
        ledger.ensure_agent("gpt", 10000)
        place(ledger, ticker="T1", agent="claude")
        place(ledger, ticker="T2", agent="gpt", count=4, price=25)
        assert {o["agent"] for o in ledger.open_orders()} == {"claude", "gpt"}
        assert ledger.open_cost("gpt") == 100
        ledger.snapshot("2026-07-06")
        ledger.snapshot("2026-07-06")  # re-run same day must not duplicate
        assert len(ledger.data["history"]) == 1
        assert ledger.data["history"][0]["balances"]["claude"] == 10000

    def test_roundtrip_persistence(self, tmp_path):
        ledger = make_ledger()
        place(ledger)
        path = tmp_path / "ledger.json"
        ledger.save(path)
        loaded = Ledger.load(path)
        assert loaded.cash("claude") == 9500
        assert len(loaded.open_orders("claude")) == 1
