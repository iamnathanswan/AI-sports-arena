"""Weekly orchestrator: settle last week, run each agent, write results.

Usage:  python -m arena.run_week

Safety: DRY_RUN defaults to true (paper trading). A live run requires
DRY_RUN=false AND Kalshi credentials AND KILL_SWITCH unset/false.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone

from .config import load_settings
from .kalshi.client import KalshiClient
from .ledger import Ledger
from .agents.runner import build_system_prompt, run_agent
from .settle import build_leaderboard, settle_open_orders
from .tools import ToolContext


def main() -> int:
    settings = load_settings()
    today = date.today()
    # "week" is the Monday of the current ISO week, not today's exact date —
    # so a scheduled Monday run and a manual re-run on, say, Wednesday of the
    # same week share one weekly position cap (as intended), while a run in a
    # genuinely new week gets a fresh cap.
    week = (today - timedelta(days=today.weekday())).isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    mode = "DRY RUN (paper trading)" if settings.dry_run else f"LIVE on Kalshi {settings.kalshi_env}"
    print(f"=== AI Sports Arena — week of {week} — {mode} ===")

    if not settings.dry_run and not (settings.kalshi_api_key_id and settings.kalshi_private_key_pem):
        print("ERROR: DRY_RUN=false but Kalshi credentials are missing. Aborting.", file=sys.stderr)
        return 1
    if settings.kill_switch:
        print("KILL_SWITCH is active: settlement will run, but no orders will be placed.")

    kalshi = KalshiClient(
        env=settings.kalshi_env,
        api_key_id=settings.kalshi_api_key_id,
        private_key_pem=settings.kalshi_private_key_pem,
    )

    ledger_path = settings.data_dir / "ledger.json"
    ledger = Ledger.load(ledger_path)
    for spec in settings.agents:
        ledger.ensure_agent(spec.name, settings.bankroll_cents)

    # 1. Settle last week's positions.
    print("\n--- Settling open positions ---")
    events = settle_open_orders(ledger, kalshi, settings)
    for e in events:
        print(f"  {e}")
    if not events:
        print("  nothing to settle")
    ledger.save(ledger_path)

    # 2. Run the agents, rotating run order weekly so no model always sees
    #    prices first.
    system_prompt = build_system_prompt(settings, week, today)
    rotation = today.isocalendar().week % len(settings.agents) if settings.agents else 0
    lineup = settings.agents[rotation:] + settings.agents[:rotation]

    results = []
    for spec in lineup:
        print(f"\n--- {spec.name} ({spec.provider}/{spec.model}) ---")
        ctx = ToolContext(
            kalshi=kalshi, ledger=ledger, settings=settings, agent=spec.name, week=week
        )
        result = run_agent(spec, ctx, system_prompt, settings.max_turns)
        result["bets_placed"] = len(ctx.bets_placed)
        results.append(result)
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            nudge = " (forced-bet nudge triggered)" if result.get("forced_bet_nudge") else ""
            print(f"  turns={result['turns']} bets={result['bets_placed']}{nudge}")
            if result.get("final_text"):
                print(f"  final: {result['final_text'][:300]}")
        ledger.save(ledger_path)  # crash safety: persist after each agent

    # 3. Snapshot + outputs.
    ledger.snapshot(week)
    ledger.save(ledger_path)

    leaderboard = build_leaderboard(ledger, settings, generated_at=now)
    (settings.data_dir / "leaderboard.json").write_text(
        json.dumps(leaderboard, indent=2) + "\n"
    )

    weekly_dir = settings.data_dir / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / f"{week}.json").write_text(
        json.dumps(
            {
                "week": week,
                "generated_at": now,
                "dry_run": settings.dry_run,
                "settlement_events": events,
                "agent_runs": results,
            },
            indent=2,
        )
        + "\n"
    )

    print("\n=== Standings ===")
    for a in leaderboard["agents"]:
        print(
            f"  {a['name']:<8} ${a['equity_cents'] / 100:>8.2f}  "
            f"P&L ${a['pnl_cents'] / 100:>+7.2f}  ROI {a['roi_pct']:>+6.2f}%"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
