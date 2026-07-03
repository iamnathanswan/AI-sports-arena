"""Kalshi trading-fee formula and its effect on the ledger."""

from arena.config import RiskLimits
from arena.fees import trading_fee_cents
from arena.ledger import Ledger
from arena.risk import check_order

WEEK = "2026-07-06"


class TestFeeFormula:
    def test_peaks_near_fifty_cents(self):
        # 0.07 * 1 * 0.5 * 0.5 = 0.0175 dollars = 1.75c -> rounds up to 2c
        assert trading_fee_cents(1, 50) == 2

    def test_ten_contracts_at_fifty(self):
        # 0.07 * 10 * 0.5 * 0.5 = 0.175 -> 17.5c -> 18c
        assert trading_fee_cents(10, 50) == 18

    def test_cheap_at_extremes(self):
        # 0.07 * 1 * 0.9 * 0.1 = 0.0063 -> 0.63c -> 1c
        assert trading_fee_cents(1, 90) == 1
        assert trading_fee_cents(1, 10) == 1

    def test_maker_is_quarter_of_taker(self):
        # maker on 10 @ 50: 0.25 * 17.5 = 4.375 -> 5c
        assert trading_fee_cents(10, 50, maker=True) == 5

    def test_zero_for_degenerate_inputs(self):
        assert trading_fee_cents(0, 50) == 0
        assert trading_fee_cents(10, 0) == 0
        assert trading_fee_cents(10, 100) == 0


class TestFeeInLedger:
    def _ledger(self, cash=10000):
        ledger = Ledger()
        ledger.ensure_agent("claude", cash)
        return ledger

    def test_fee_deducted_from_cash_on_place(self):
        ledger = self._ledger()
        fee = trading_fee_cents(10, 55)
        ledger.record_order(
            agent="claude", week=WEEK, ticker="T1", market_title="T1", side="yes",
            count=10, limit_price_cents=55, status="dry_run", forecast_prob=0.6,
            reasoning="x", fee_cents=fee,
        )
        assert ledger.cash("claude") == 10000 - 550 - fee

    def test_cannot_place_when_fee_would_overdraw(self):
        # cash exactly covers stake but not the fee
        ledger = self._ledger(cash=550)
        import pytest

        with pytest.raises(ValueError):
            ledger.record_order(
                agent="claude", week=WEEK, ticker="T1", market_title="T1", side="yes",
                count=10, limit_price_cents=55, status="dry_run", forecast_prob=0.6,
                reasoning="x", fee_cents=trading_fee_cents(10, 55),
            )

    def test_risk_check_rejects_when_fee_exceeds_cash(self):
        ledger = self._ledger(cash=550)
        limits = RiskLimits()
        fee = trading_fee_cents(10, 55)
        decision = check_order(ledger, limits, "claude", WEEK, "T1", 10, 55, fee_cents=fee)
        assert not decision and "fee" in decision.reason

    def test_refund_unfilled_returns_proportional_fee(self):
        ledger = self._ledger()
        fee = trading_fee_cents(10, 50)  # 18c on 10 contracts
        order = ledger.record_order(
            agent="claude", week=WEEK, ticker="T1", market_title="T1", side="yes",
            count=10, limit_price_cents=50, status="live", forecast_prob=0.6,
            reasoning="x", fee_cents=fee,
        )
        cash_after_place = ledger.cash("claude")  # 10000 - 500 - 18
        # only 4 of 10 filled -> refund 6*50 stake + 6/10 of the fee
        ledger.refund_unfilled(order, filled_count=4)
        expected_fee_refund = fee - round(fee * 4 / 10)
        assert ledger.cash("claude") == cash_after_place + 6 * 50 + expected_fee_refund
        assert order["fee_cents"] == round(fee * 4 / 10)

    def test_fully_unfilled_refunds_entire_fee(self):
        ledger = self._ledger()
        fee = trading_fee_cents(10, 50)
        order = ledger.record_order(
            agent="claude", week=WEEK, ticker="T1", market_title="T1", side="yes",
            count=10, limit_price_cents=50, status="live", forecast_prob=0.6,
            reasoning="x", fee_cents=fee,
        )
        ledger.refund_unfilled(order, filled_count=0)
        assert ledger.cash("claude") == 10000  # stake + fee fully returned
        assert order["result"] == "unfilled"
