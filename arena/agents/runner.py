"""Provider-agnostic agent runner.

Fairness contract: every agent receives the same system prompt (rendered from
arena/prompts/system.md), the same user kickoff message, the same tool schemas,
and the same turn budget. Adapters translate wire formats only.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from ..config import AgentSpec, Settings
from ..pricing import compute_cost_cents, empty_usage
from ..tools import TOOL_SCHEMAS, ToolContext, execute_tool
from .base import RunOptions

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
USER_KICKOFF = "Begin your weekly betting session now."

REQUIRED_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
}

# Minimum-deployment backstop: if a session would end having staked less than
# the configured per-run floor, the adapter injects this once and continues the
# SAME conversation (reusing the research it already paid for) so the agent tops
# up from its best remaining opportunities. Same wording for every model.
TOP_UP_KICKOFF = (
    "You are about to end this run having deployed less than the ${min_deploy:.0f} "
    "minimum for this session. From the markets you already reviewed, place your "
    "best remaining positive-edge bets to reach at least ${min_deploy:.0f} of total "
    "stake (each bet ${min_stake:.0f}-${max_stake:.0f} on one market). Only stop short "
    "if you genuinely cannot find any bet you expect to win after fees; if so, say "
    "that plainly via record_note."
)


def build_system_prompt(settings: Settings, today: date) -> str:
    text = PROMPT_PATH.read_text()
    replacements = {
        "{{TODAY}}": today.isoformat(),
        "{{MIN_STAKE}}": f"{settings.risk.min_stake_cents_per_market / 100:.0f}",
        "{{MAX_STAKE}}": f"{settings.risk.max_stake_cents_per_market / 100:.0f}",
        "{{MIN_DEPLOY}}": f"{settings.min_deploy_cents_per_run / 100:.0f}",
        "{{MIN_EDGE}}": str(settings.risk.min_edge_cents_per_contract),
        "{{MAX_DEPLOYED_PCT}}": f"{settings.risk.max_deployed_pct:.0f}",
        "{{MIN_PRICE}}": str(settings.risk.min_price_cents),
        "{{MAX_PRICE}}": str(settings.risk.max_price_cents),
        "{{MAX_SEARCHES}}": str(settings.max_searches_per_session),
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def has_api_key(spec: AgentSpec) -> bool:
    env = REQUIRED_ENV.get(spec.provider)
    return bool(env and os.environ.get(env, "").strip())


def run_agent(spec: AgentSpec, ctx: ToolContext, system_prompt: str, max_turns: int) -> dict:
    """Run one agent's weekly session. Returns a summary dict (never raises)."""

    def execute(name: str, args: dict) -> str:
        return execute_tool(ctx, name, args)

    summary: dict = {
        "agent": spec.name,
        "provider": spec.provider,
        "model": spec.model,
        "turns": 0,
        "final_text": "",
        "error": None,
        "usage": empty_usage(),
        "cost_cents": 0,
    }

    if not has_api_key(spec):
        summary["error"] = f"skipped: {REQUIRED_ENV.get(spec.provider)} is not set"
        return summary

    try:
        if spec.provider == "anthropic":
            from . import anthropic_agent as adapter
        elif spec.provider == "openai":
            from . import openai_agent as adapter
        elif spec.provider == "google":
            from . import gemini_agent as adapter
        else:
            summary["error"] = f"unknown provider {spec.provider!r}"
            return summary

        settings = ctx.settings
        # Minimum-deployment backstop: if the session would end below the per-run
        # floor, nudge the model once to top up from its best remaining
        # opportunities. Disabled (no followup) when the floor is 0.
        min_deploy = settings.min_deploy_cents_per_run
        followup_prompt = None
        should_continue = None
        if min_deploy > 0:
            risk = settings.risk
            followup_prompt = TOP_UP_KICKOFF.format(
                min_deploy=min_deploy / 100,
                min_stake=risk.min_stake_cents_per_market / 100,
                max_stake=risk.max_stake_cents_per_market / 100,
            )
            should_continue = (
                lambda: sum(b["cost_cents"] for b in ctx.bets_placed) < min_deploy
            )

        options = RunOptions(
            effort=settings.effort,
            max_searches=settings.max_searches_per_session,
            budget_cents=settings.max_cost_cents_per_session or None,
            cost_of=lambda u: compute_cost_cents(spec, u),
            followup_prompt=followup_prompt,
            should_continue=should_continue,
        )

        result = adapter.run(
            model=spec.model,
            system_prompt=system_prompt,
            user_prompt=USER_KICKOFF,
            schemas=TOOL_SCHEMAS,
            execute=execute,
            max_turns=max_turns,
            options=options,
        )
        summary.update(result)
        summary["cost_cents"] = compute_cost_cents(spec, summary["usage"])
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return summary
