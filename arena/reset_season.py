"""Reset the arena to a fresh season (e.g. when flipping from paper to live).

Usage:  python -m arena.reset_season

Wipes the ledger (all agents back to their starting bankroll, no orders,
no history) and rewrites a season-zero leaderboard. Weekly logs are removed.
This does NOT touch anything on Kalshi — close real positions yourself first.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone

from .config import load_settings
from .ledger import Ledger
from .settle import build_leaderboard


def main() -> int:
    settings = load_settings()
    ledger = Ledger()
    for spec in settings.agents:
        ledger.ensure_agent(spec.name, settings.bankroll_cents)
    ledger.save(settings.data_dir / "ledger.json")

    board = build_leaderboard(
        ledger, settings, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    (settings.data_dir / "leaderboard.json").write_text(json.dumps(board, indent=2) + "\n")

    weekly = settings.data_dir / "weekly"
    if weekly.exists():
        shutil.rmtree(weekly)

    names = ", ".join(spec.name for spec in settings.agents)
    print(f"Season reset: {names} each at {settings.bankroll_cents / 100:.2f} USD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
