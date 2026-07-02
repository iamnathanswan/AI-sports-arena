"""Verify the runner's mandatory-bet backstop: any agent that ends its first
session without placing a bet gets exactly one forced retry, applied
identically regardless of which model it is."""

from arena.agents import runner
from arena.config import AgentSpec, RiskLimits, Settings
from arena.ledger import Ledger
from arena.tools import ToolContext

WEEK = "2026-06-29"


def make_settings():
    return Settings(
        bankroll_cents=10000,
        max_turns=10,
        risk=RiskLimits(),
        sports_categories=["Sports"],
        series_allowlist=[],
        agents=[AgentSpec(name="claude", provider="anthropic", model="m")],
    )


class FakeKalshi:
    def get_market(self, ticker):
        return {"ticker": ticker, "title": "Test market", "status": "open"}


def make_ctx():
    ledger = Ledger()
    ledger.ensure_agent("claude", 10000)
    settings = make_settings()
    return ToolContext(kalshi=FakeKalshi(), ledger=ledger, settings=settings, agent="claude", week=WEEK)


class RecordingAdapter:
    """Stands in for anthropic_agent/openai_agent/gemini_agent — records every
    call's user_prompt and optionally places a bet via the real execute()."""

    def __init__(self, bet_on_call: int | None):
        self.calls: list[dict] = []
        self.bet_on_call = bet_on_call

    def run(self, model, system_prompt, user_prompt, schemas, execute, max_turns):
        call_index = len(self.calls) + 1
        self.calls.append(
            {"user_prompt": user_prompt, "max_turns": max_turns, "system_prompt": system_prompt}
        )
        if self.bet_on_call == call_index:
            execute(
                "place_bet",
                {
                    "ticker": "T1",
                    "side": "yes",
                    "contracts": 1,
                    "limit_price_cents": 50,
                    "forecast_prob": 0.55,
                    "reasoning": "forced-bet test",
                },
            )
        return {"turns": 3, "final_text": f"done call {call_index}"}


def run_with_fake_adapter(monkeypatch, adapter):
    # `from . import anthropic_agent as adapter` inside run_agent resolves via
    # the already-imported package attribute, not sys.modules -- so patch the
    # real module's `run` function directly (same technique as test_adapters.py).
    monkeypatch.setattr(runner, "has_api_key", lambda spec: True)
    monkeypatch.setattr("arena.agents.anthropic_agent.run", adapter.run)
    ctx = make_ctx()
    spec = AgentSpec(name="claude", provider="anthropic", model="m")
    result = runner.run_agent(spec, ctx, system_prompt="SYSTEM", max_turns=10)
    return result, ctx, adapter


class TestForcedBetBackstop:
    def test_bets_on_first_try_no_nudge(self, monkeypatch):
        adapter = RecordingAdapter(bet_on_call=1)
        result, ctx, adapter = run_with_fake_adapter(monkeypatch, adapter)
        assert len(adapter.calls) == 1
        assert adapter.calls[0]["user_prompt"] == runner.USER_KICKOFF
        assert result["forced_bet_nudge"] is False
        assert result["turns"] == 3
        assert len(ctx.bets_placed) == 1

    def test_passes_then_forced_to_bet(self, monkeypatch):
        adapter = RecordingAdapter(bet_on_call=2)
        result, ctx, adapter = run_with_fake_adapter(monkeypatch, adapter)
        assert len(adapter.calls) == 2
        assert adapter.calls[0]["user_prompt"] == runner.USER_KICKOFF
        assert adapter.calls[1]["user_prompt"] == runner.FORCE_BET_KICKOFF
        # same system prompt both times -- fairness: no extra/different info
        assert adapter.calls[0]["system_prompt"] == adapter.calls[1]["system_prompt"] == "SYSTEM"
        # run_agent is called with max_turns=10 in this test, which is below
        # FORCE_BET_MAX_TURNS (20) -- the retry respects the smaller cap.
        assert adapter.calls[1]["max_turns"] == 10
        assert result["forced_bet_nudge"] is True
        assert result["turns"] == 6  # 3 + 3
        assert result["final_text"] == "done call 2"
        assert len(ctx.bets_placed) == 1

    def test_passes_both_times_still_reports_zero_bets_honestly(self, monkeypatch):
        adapter = RecordingAdapter(bet_on_call=None)
        result, ctx, adapter = run_with_fake_adapter(monkeypatch, adapter)
        assert len(adapter.calls) == 2
        assert result["forced_bet_nudge"] is True
        assert ctx.bets_placed == []  # never fabricates a bet on the model's behalf

    def test_forced_retry_turn_budget_never_exceeds_configured_max(self, monkeypatch):
        adapter = RecordingAdapter(bet_on_call=None)
        monkeypatch.setattr(runner, "has_api_key", lambda spec: True)
        monkeypatch.setattr("arena.agents.anthropic_agent.run", adapter.run)
        ctx = make_ctx()
        spec = AgentSpec(name="claude", provider="anthropic", model="m")
        # max_turns smaller than FORCE_BET_MAX_TURNS -- retry must respect the cap
        runner.run_agent(spec, ctx, system_prompt="SYSTEM", max_turns=5)
        assert adapter.calls[1]["max_turns"] == 5
