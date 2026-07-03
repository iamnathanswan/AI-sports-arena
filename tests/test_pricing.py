"""Token cost calculation and per-agent usage accumulation in the ledger."""

from arena.config import AgentSpec
from arena.ledger import Ledger
from arena.pricing import add_usage, compute_cost_cents, empty_usage


def test_empty_usage_is_all_zero():
    u = empty_usage()
    assert u == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
    }


def test_add_usage_accumulates():
    total = empty_usage()
    add_usage(total, {"input_tokens": 100, "output_tokens": 20})
    add_usage(total, {"input_tokens": 50, "cache_read_tokens": 10})
    assert total == {
        "input_tokens": 150,
        "output_tokens": 20,
        "cache_write_tokens": 0,
        "cache_read_tokens": 10,
    }


def test_add_usage_tolerates_none():
    total = empty_usage()
    add_usage(total, None)
    assert total == empty_usage()


def test_compute_cost_cents():
    spec = AgentSpec(
        name="claude",
        provider="anthropic",
        model="m",
        price_per_million_input=5.00,
        price_per_million_output=25.00,
        price_per_million_cache_write=6.25,
        price_per_million_cache_read=0.50,
    )
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_write_tokens": 40_000,
        "cache_read_tokens": 200_000,
    }
    # 5.00 + 2.50 + 0.25 + 0.10 = 7.85 dollars -> 785 cents
    assert compute_cost_cents(spec, usage) == 785


def test_compute_cost_cents_zero_priced_model_is_free():
    spec = AgentSpec(name="x", provider="anthropic", model="m")  # all prices default 0
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert compute_cost_cents(spec, usage) == 0


class TestLedgerUsageTracking:
    def test_first_session_initializes_totals(self):
        ledger = Ledger()
        ledger.ensure_agent("claude", 10000)
        ledger.record_usage("claude", {"input_tokens": 1000, "output_tokens": 200}, cost_cents=15)
        totals = ledger.usage_totals("claude")
        assert totals["input_tokens"] == 1000
        assert totals["output_tokens"] == 200
        assert totals["cost_cents"] == 15
        assert totals["sessions"] == 1

    def test_accumulates_across_sessions(self):
        ledger = Ledger()
        ledger.ensure_agent("claude", 10000)
        ledger.record_usage("claude", {"input_tokens": 1000, "output_tokens": 200}, cost_cents=15)
        ledger.record_usage("claude", {"input_tokens": 500, "output_tokens": 100}, cost_cents=8)
        totals = ledger.usage_totals("claude")
        assert totals["input_tokens"] == 1500
        assert totals["output_tokens"] == 300
        assert totals["cost_cents"] == 23
        assert totals["sessions"] == 2

    def test_usage_never_touches_cash(self):
        ledger = Ledger()
        ledger.ensure_agent("claude", 10000)
        ledger.record_usage("claude", {"input_tokens": 1000}, cost_cents=500)
        assert ledger.cash("claude") == 10000
        assert ledger.equity("claude") == 10000

    def test_usage_totals_defaults_to_zero_for_untracked_agent(self):
        ledger = Ledger()
        ledger.ensure_agent("claude", 10000)
        totals = ledger.usage_totals("claude")
        assert totals["sessions"] == 0
        assert totals["cost_cents"] == 0

    def test_roundtrip_persistence(self, tmp_path):
        ledger = Ledger()
        ledger.ensure_agent("claude", 10000)
        ledger.record_usage("claude", {"input_tokens": 1000, "output_tokens": 200}, cost_cents=15)
        path = tmp_path / "ledger.json"
        ledger.save(path)
        loaded = Ledger.load(path)
        assert loaded.usage_totals("claude")["cost_cents"] == 15
