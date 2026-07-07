"""Settlement + tool-layer tests against a fake Kalshi client."""

from datetime import datetime, timedelta, timezone

from arena.config import RiskLimits, Settings
from arena.fees import trading_fee_cents
from arena.ledger import Ledger
from arena.settle import build_leaderboard, settle_open_orders
from arena.tools import ToolContext, execute_tool

WEEK = "2026-07-06"


class FakeKalshi:
    """In-memory stand-in for KalshiClient."""

    def __init__(self):
        self.markets = {}
        self.fills = []
        self.positions = []
        self.created_orders = []

    def get_market(self, ticker):
        return self.markets.get(ticker, {})

    def get_fills(self, ticker=None, limit=200):
        return [f for f in self.fills if ticker is None or f["ticker"] == ticker]

    def get_positions(self, ticker=None):
        return [
            p
            for p in self.positions
            if ticker is None or p.get("ticker") == ticker or p.get("market_ticker") == ticker
        ]

    def get_series_list(self, category=None):
        return [{"ticker": "KXMLBGAME", "title": "MLB game winners", "category": category}]

    def get_events(self, **kwargs):
        return {
            "events": [
                {
                    "event_ticker": "KXMLBGAME-26JUL06",
                    "title": "Yankees @ Red Sox",
                    "markets": [self.markets.get("MLB-1", {})],
                }
            ]
        }

    def get_orderbook(self, ticker, depth=5):
        return {"yes": [[55, 100]], "no": [[44, 80]]}

    def create_order(self, **kwargs):
        self.created_orders.append(kwargs)
        return {"order_id": f"kalshi-{len(self.created_orders)}", "client_order_id": "c-1"}


def make_settings(dry_run=True, kill_switch=False):
    return Settings(
        bankroll_cents=10000,
        max_turns=10,
        risk=RiskLimits(),
        sports_categories=["Sports"],
        series_allowlist=[],
        agents=[],
        dry_run=dry_run,
        kill_switch=kill_switch,
    )


def make_world():
    ledger = Ledger()
    ledger.ensure_agent("claude", 10000)
    kalshi = FakeKalshi()
    kalshi.markets["MLB-1"] = {
        "ticker": "MLB-1",
        "title": "Will the Yankees beat the Red Sox?",
        "status": "open",
        "yes_bid": 54,
        "yes_ask": 56,
        "no_bid": 44,
        "no_ask": 46,
        "volume": 1000,
    }
    return ledger, kalshi


def ctx_for(ledger, kalshi, settings):
    return ToolContext(kalshi=kalshi, ledger=ledger, settings=settings, agent="claude", week=WEEK)


class TestTools:
    def test_dry_run_never_hits_exchange(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings(dry_run=True))
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 20,
                "limit_price_cents": 55,
                "forecast_prob": 0.62,
                "reasoning": "Ace pitching matchup edge.",
            },
        )
        assert '"placed": true' in result and '"dry_run"' in result
        assert kalshi.created_orders == []
        # 1100c stake + Kalshi fee on 20 contracts @ 55c
        fee = trading_fee_cents(20, 55)
        assert ledger.cash("claude") == 10000 - 1100 - fee
        assert f'"fee_cents": {fee}' in result

    def test_live_mode_places_real_order(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings(dry_run=False))
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 20,
                "limit_price_cents": 55,
                "forecast_prob": 0.62,
                "reasoning": "Edge.",
            },
        )
        assert '"live"' in result
        assert len(kalshi.created_orders) == 1
        assert kalshi.created_orders[0]["side"] == "yes"
        order = ledger.open_orders("claude")[0]
        assert order["kalshi_order_id"] == "kalshi-1"

    def test_kill_switch_blocks_live_and_dry(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings(dry_run=False, kill_switch=True))
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 1,
                "limit_price_cents": 55,
                "forecast_prob": 0.6,
                "reasoning": "x",
            },
        )
        assert '"rejected": true' in result
        assert kalshi.created_orders == []
        assert ledger.cash("claude") == 10000

    def test_risk_rejection_reaches_model(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings())
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 100,  # 5500c > $20 per-market cap
                "limit_price_cents": 55,
                "forecast_prob": 0.6,
                "reasoning": "too big",
            },
        )
        assert '"rejected": true' in result and "per-market cap" in result

    def test_below_minimum_stake_rejected(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings())
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 5,  # 275c < $10 minimum
                "limit_price_cents": 55,
                "forecast_prob": 0.6,
                "reasoning": "too small",
            },
        )
        assert '"rejected": true' in result and "minimum" in result
        assert ledger.cash("claude") == 10000

    def test_fair_value_bet_rejected_by_edge_gate(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings())
        result = execute_tool(
            ctx,
            "place_bet",
            {
                "ticker": "MLB-1",
                "side": "yes",
                "contracts": 20,  # clears the $10 floor
                "limit_price_cents": 55,
                "forecast_prob": 0.55,  # equal to price -> no edge after fee
                "reasoning": "no real edge here",
            },
        )
        assert '"rejected": true' in result and "net edge" in result
        assert ledger.cash("claude") == 10000

    def test_bankroll_and_note(self):
        ledger, kalshi = make_world()
        ctx = ctx_for(ledger, kalshi, make_settings())
        assert '"cash_cents": 10000' in execute_tool(ctx, "get_bankroll", {})
        assert '"recorded": true' in execute_tool(ctx, "record_note", {"text": "passing this week"})
        assert ledger.data["notes"][0]["agent"] == "claude"


class TestSettlement:
    def _paper_order(self, ledger, ticker="MLB-1", side="yes", count=10, price=55, prob=0.7):
        return ledger.record_order(
            agent="claude",
            week=WEEK,
            ticker=ticker,
            market_title=ticker,
            side=side,
            count=count,
            limit_price_cents=price,
            status="dry_run",
            forecast_prob=prob,
            reasoning="test",
        )

    def test_paper_order_settles_won(self):
        ledger, kalshi = make_world()
        self._paper_order(ledger)
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        events = settle_open_orders(ledger, kalshi, make_settings())
        assert events[0]["result"] == "won"
        assert ledger.cash("claude") == 10000 - 550 + 1000

    def test_paper_order_settles_lost(self):
        ledger, kalshi = make_world()
        self._paper_order(ledger)
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "no"
        settle_open_orders(ledger, kalshi, make_settings())
        assert ledger.cash("claude") == 10000 - 550

    def test_open_market_left_alone(self):
        ledger, kalshi = make_world()
        self._paper_order(ledger)
        events = settle_open_orders(ledger, kalshi, make_settings())
        assert events == []
        assert len(ledger.open_orders("claude")) == 1

    def test_live_partial_fill_reconciled(self):
        ledger, kalshi = make_world()
        order = ledger.record_order(
            agent="claude",
            week=WEEK,
            ticker="MLB-1",
            market_title="MLB-1",
            side="yes",
            count=10,
            limit_price_cents=55,
            status="live",
            forecast_prob=0.7,
            reasoning="test",
            kalshi_order_id="kalshi-1",
        )
        # force expiry so reconciliation kicks in
        order["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat(timespec="seconds")
        kalshi.fills = [{"ticker": "MLB-1", "order_id": "kalshi-1", "count": 4}]
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        settle_open_orders(ledger, kalshi, make_settings())
        # refunded 6*55=330, won 4 contracts -> 400
        assert ledger.cash("claude") == 10000 - 550 + 330 + 400
        assert order["result"] == "won" and order["count"] == 4

    def test_live_never_filled_fully_refunded(self):
        ledger, kalshi = make_world()
        order = ledger.record_order(
            agent="claude",
            week=WEEK,
            ticker="MLB-1",
            market_title="MLB-1",
            side="yes",
            count=10,
            limit_price_cents=55,
            status="live",
            forecast_prob=0.7,
            reasoning="test",
            kalshi_order_id="kalshi-1",
        )
        order["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat(timespec="seconds")
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        settle_open_orders(ledger, kalshi, make_settings())
        assert ledger.cash("claude") == 10000
        assert order["result"] == "unfilled"

    def test_position_safety_net_credits_missed_fill(self):
        # Regression: the V2 create response returns order_id at the top level, so
        # kalshi_order_id was briefly captured as None and fills couldn't be
        # matched -- a filled, winning order was wrongly refunded as unfilled.
        # Now the account position is a cross-check so the win is still credited.
        ledger, kalshi = make_world()
        order = ledger.record_order(
            agent="claude",
            week=WEEK,
            ticker="MLB-1",
            market_title="MLB-1",
            side="yes",
            count=10,
            limit_price_cents=55,
            status="live",
            forecast_prob=0.7,
            reasoning="test",
            kalshi_order_id=None,  # order_id capture missed it
        )
        order["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat(timespec="seconds")
        kalshi.positions = [{"ticker": "MLB-1", "position": 10}]
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        settle_open_orders(ledger, kalshi, make_settings())
        assert order["result"] == "won" and order["count"] == 10
        assert ledger.cash("claude") == 10000 - 550 + 1000

    def test_fills_counted_from_fixed_point_string(self):
        # Kalshi may report a fill count as a fixed-point string ("7.00").
        ledger, kalshi = make_world()
        order = ledger.record_order(
            agent="claude",
            week=WEEK,
            ticker="MLB-1",
            market_title="MLB-1",
            side="yes",
            count=10,
            limit_price_cents=55,
            status="live",
            forecast_prob=0.7,
            reasoning="test",
            kalshi_order_id="kalshi-1",
        )
        order["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat(timespec="seconds")
        kalshi.fills = [{"ticker": "MLB-1", "order_id": "kalshi-1", "count_fp": "7.00"}]
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        settle_open_orders(ledger, kalshi, make_settings())
        # refunded 3*55=165, won 7 -> 700
        assert order["result"] == "won" and order["count"] == 7
        assert ledger.cash("claude") == 10000 - 550 + 165 + 700

    def test_fill_rate_reported_over_live_orders(self):
        ledger, kalshi = make_world()
        # Order A: 10 ordered, 4 fill, market wins.
        a = ledger.record_order(
            agent="claude", week=WEEK, ticker="MLB-1", market_title="MLB-1",
            side="yes", count=10, limit_price_cents=55, status="live",
            forecast_prob=0.7, reasoning="t", kalshi_order_id="kalshi-1",
        )
        a["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat(timespec="seconds")
        # Order B: 10 ordered, nothing fills (fully unfilled).
        b = ledger.record_order(
            agent="claude", week=WEEK, ticker="MLB-2", market_title="MLB-2",
            side="yes", count=10, limit_price_cents=40, status="live",
            forecast_prob=0.6, reasoning="t", kalshi_order_id="kalshi-2",
        )
        b["placed_at"] = a["placed_at"]
        kalshi.markets["MLB-1"]["status"] = "settled"
        kalshi.markets["MLB-1"]["result"] = "yes"
        kalshi.markets["MLB-2"] = {"ticker": "MLB-2", "status": "settled", "result": "yes"}
        kalshi.fills = [{"ticker": "MLB-1", "order_id": "kalshi-1", "count": 4}]
        settle_open_orders(ledger, kalshi, make_settings())

        from arena.config import AgentSpec

        settings = make_settings()
        settings.agents = [AgentSpec(name="claude", provider="anthropic", model="m")]
        board = build_leaderboard(ledger, settings, generated_at="now")
        # 4 of 20 ordered contracts filled across the two live orders.
        assert board["agents"][0]["fill_rate"] == 0.2

    def test_leaderboard_metrics(self):
        ledger, kalshi = make_world()
        won = self._paper_order(ledger, prob=0.7)
        lost = self._paper_order(ledger, ticker="MLB-2", side="no", count=4, price=25, prob=0.4)
        ledger.settle_order(won, won=True)
        ledger.settle_order(lost, won=False)
        settings = make_settings()
        from arena.config import AgentSpec

        settings.agents = [AgentSpec(name="claude", provider="anthropic", model="m")]
        board = build_leaderboard(ledger, settings, generated_at="now")
        agent = board["agents"][0]
        assert agent["settled_bets"] == 2 and agent["wins"] == 1
        assert agent["win_rate"] == 0.5
        # brier: (0.7-1)^2=0.09, (0.4-0)^2=0.16 -> 0.125
        assert agent["brier"] == 0.125
        assert agent["equity_cents"] == 10000 - 550 - 100 + 1000
        assert len(board["bets"]) == 2
