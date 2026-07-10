"""run_agent wiring: it calls the adapter exactly once, passes the cost-control
options, and wires the per-run minimum-deployment backstop (followup_prompt +
should_continue) when min_deploy_cents_per_run > 0."""

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
        effort="medium",
        max_searches_per_session=5,
        max_cost_cents_per_session=100,
        min_deploy_cents_per_run=2000,
    )


class FakeKalshi:
    def get_market(self, ticker):
        return {"ticker": ticker, "title": "Test market", "status": "open"}


def make_ctx():
    ledger = Ledger()
    ledger.ensure_agent("claude", 10000)
    return ToolContext(
        kalshi=FakeKalshi(), ledger=ledger, settings=make_settings(), agent="claude", week=WEEK
    )


class RecordingAdapter:
    """Captures the options run_agent passes, and returns a canned result."""

    def __init__(self, usage=None):
        self.captured_options = None
        self.call_count = 0
        self.usage = usage or {
            "input_tokens": 1000, "output_tokens": 200,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }

    def run(self, model, system_prompt, user_prompt, schemas, execute, max_turns, options=None):
        self.call_count += 1
        self.captured_options = options
        return {"turns": 3, "final_text": "done", "usage": self.usage}


def run_with(monkeypatch, adapter):
    monkeypatch.setattr(runner, "has_api_key", lambda spec: True)
    monkeypatch.setattr("arena.agents.anthropic_agent.run", adapter.run)
    ctx = make_ctx()
    spec = AgentSpec(name="claude", provider="anthropic", model="m")
    return runner.run_agent(spec, ctx, system_prompt="SYSTEM", max_turns=10), ctx


class TestRunnerWiring:
    def test_calls_adapter_exactly_once(self, monkeypatch):
        adapter = RecordingAdapter()
        run_with(monkeypatch, adapter)
        assert adapter.call_count == 1

    def test_passes_cost_control_options(self, monkeypatch):
        adapter = RecordingAdapter()
        run_with(monkeypatch, adapter)
        opts = adapter.captured_options
        assert opts is not None
        assert opts.effort == "medium"
        assert opts.max_searches == 5
        assert opts.budget_cents == 100
        assert callable(opts.cost_of)

    def test_topup_backstop_wired_when_floor_set(self, monkeypatch):
        # With a per-run floor configured, the runner wires the top-up nudge.
        adapter = RecordingAdapter()
        _, ctx = run_with(monkeypatch, adapter)
        opts = adapter.captured_options
        assert opts.followup_prompt is not None
        assert "20" in opts.followup_prompt  # $20 floor mentioned
        # Under the floor -> keep going; at/over it -> stop.
        assert opts.should_continue() is True
        ctx.bets_placed.append({"cost_cents": 2000})
        assert opts.should_continue() is False

    def test_no_backstop_when_floor_zero(self, monkeypatch):
        adapter = RecordingAdapter()
        monkeypatch.setattr(runner, "has_api_key", lambda spec: True)
        monkeypatch.setattr("arena.agents.anthropic_agent.run", adapter.run)
        ctx = make_ctx()
        ctx.settings.min_deploy_cents_per_run = 0
        spec = AgentSpec(name="claude", provider="anthropic", model="m")
        runner.run_agent(spec, ctx, system_prompt="SYSTEM", max_turns=10)
        opts = adapter.captured_options
        assert opts.followup_prompt is None
        assert opts.should_continue is None
        assert opts.wants_followup() is False

    def test_cost_of_computes_from_spec_prices(self, monkeypatch):
        adapter = RecordingAdapter()
        run_with(monkeypatch, adapter)
        # spec has no prices set in this test -> cost is 0, but callable works.
        assert adapter.captured_options.cost_of({"input_tokens": 1_000_000}) == 0

    def test_budget_disabled_when_zero(self, monkeypatch):
        adapter = RecordingAdapter()
        monkeypatch.setattr(runner, "has_api_key", lambda spec: True)
        monkeypatch.setattr("arena.agents.anthropic_agent.run", adapter.run)
        ctx = make_ctx()
        ctx.settings.max_cost_cents_per_session = 0
        spec = AgentSpec(name="claude", provider="anthropic", model="m")
        runner.run_agent(spec, ctx, system_prompt="SYSTEM", max_turns=10)
        assert adapter.captured_options.budget_cents is None
