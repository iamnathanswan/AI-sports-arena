"""Configuration loading: config/settings.yaml + environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"
DATA_DIR = REPO_ROOT / "data"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RiskLimits:
    max_stake_pct_per_market: float = 10.0
    max_new_positions_per_week: int = 5
    max_deployed_pct: float = 50.0
    min_price_cents: int = 5
    max_price_cents: int = 95
    order_expiration_minutes: int = 60


@dataclass
class AgentSpec:
    name: str
    provider: str  # anthropic | openai | google
    model: str
    # Pricing in dollars per 1M tokens, for cost tracking -- edit these if a
    # provider changes prices. 0 disables cost tracking for that category.
    price_per_million_input: float = 0.0
    price_per_million_output: float = 0.0
    price_per_million_cache_write: float = 0.0
    price_per_million_cache_read: float = 0.0


@dataclass
class Settings:
    bankroll_cents: int
    max_turns: int
    risk: RiskLimits
    sports_categories: list[str]
    series_allowlist: list[str]
    agents: list[AgentSpec]

    # Cost controls (applied identically to every agent for fairness).
    effort: str = "medium"  # low | medium | high
    max_searches_per_session: int = 5
    max_cost_cents_per_session: int = 100  # hard per-session spend ceiling; 0 disables

    # Environment-derived
    dry_run: bool = True
    kill_switch: bool = False
    kalshi_env: str = "prod"
    kalshi_api_key_id: str = ""
    kalshi_private_key_pem: str = ""

    data_dir: Path = field(default_factory=lambda: DATA_DIR)


def _load_private_key_pem() -> str:
    pem = os.environ.get("KALSHI_PRIVATE_KEY", "").strip()
    if pem:
        # Allow escaped newlines when pasted as a single-line env var.
        return pem.replace("\\n", "\n")
    path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
    if path and Path(path).exists():
        return Path(path).read_text()
    return ""


def load_settings(settings_path: Path | None = None) -> Settings:
    path = settings_path or SETTINGS_PATH
    raw = yaml.safe_load(path.read_text())

    risk_raw = raw.get("risk", {})
    risk = RiskLimits(
        max_stake_pct_per_market=float(risk_raw.get("max_stake_pct_per_market", 10)),
        max_new_positions_per_week=int(risk_raw.get("max_new_positions_per_week", 5)),
        max_deployed_pct=float(risk_raw.get("max_deployed_pct", 50)),
        min_price_cents=int(risk_raw.get("min_price_cents", 5)),
        max_price_cents=int(risk_raw.get("max_price_cents", 95)),
        order_expiration_minutes=int(risk_raw.get("order_expiration_minutes", 60)),
    )

    sports = raw.get("sports", {})
    agents = [
        AgentSpec(
            name=a["name"],
            provider=a["provider"],
            model=a["model"],
            price_per_million_input=float(a.get("price_per_million_input", 0)),
            price_per_million_output=float(a.get("price_per_million_output", 0)),
            price_per_million_cache_write=float(a.get("price_per_million_cache_write", 0)),
            price_per_million_cache_read=float(a.get("price_per_million_cache_read", 0)),
        )
        for a in raw.get("agents", [])
    ]

    return Settings(
        bankroll_cents=int(raw.get("bankroll_cents", 10000)),
        max_turns=int(raw.get("max_turns", 25)),
        risk=risk,
        sports_categories=list(sports.get("categories", ["Sports"])),
        series_allowlist=list(sports.get("series_allowlist", []) or []),
        agents=agents,
        effort=str(raw.get("effort", "medium")).lower(),
        max_searches_per_session=int(raw.get("max_searches_per_session", 5)),
        max_cost_cents_per_session=int(raw.get("max_cost_cents_per_session", 100)),
        dry_run=_env_flag("DRY_RUN", default=True),
        kill_switch=_env_flag("KILL_SWITCH", default=False),
        kalshi_env=os.environ.get("KALSHI_ENV", "prod").strip().lower() or "prod",
        kalshi_api_key_id=os.environ.get("KALSHI_API_KEY_ID", "").strip(),
        kalshi_private_key_pem=_load_private_key_pem(),
    )
