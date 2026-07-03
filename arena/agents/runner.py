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
from ..pricing import add_usage, compute_cost_cents, empty_usage
from ..tools import TOOL_SCHEMAS, ToolContext, execute_tool

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
USER_KICKOFF = "Begin your weekly betting session now."

# Fairness-preserving backstop: every agent's system prompt already mandates at
# least one bet per session. If a model still ends without placing one (despite
# the prompt), every agent gets exactly one identical, forced second attempt
# before the session is allowed to end with zero bets. Same nudge, same wording,
# same turn budget for every model — no agent gets an advantage from complying
# on the first try vs. the second.
FORCE_BET_KICKOFF = (
    "Your last session ended without placing any bet, which violates your mandate "
    "to place at least one bet every session. Re-check the board and place your "
    "single most defensible bet now, sized conservatively if your edge is thin — "
    "even one contract is fine. Only end without betting if you can confirm there "
    "are truly zero open sports markets anywhere on the exchange right now; if so, "
    "say that plainly via record_note."
)
FORCE_BET_MAX_TURNS = 20

REQUIRED_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
}


def build_system_prompt(settings: Settings, week: str, today: date) -> str:
    text = PROMPT_PATH.read_text()
    replacements = {
        "{{TODAY}}": today.isoformat(),
        "{{WEEK}}": week,
        "{{MAX_STAKE_PCT}}": f"{settings.risk.max_stake_pct_per_market:.0f}",
        "{{MAX_POSITIONS}}": str(settings.risk.max_new_positions_per_week),
        "{{MAX_DEPLOYED_PCT}}": f"{settings.risk.max_deployed_pct:.0f}",
        "{{MIN_PRICE}}": str(settings.risk.min_price_cents),
        "{{MAX_PRICE}}": str(settings.risk.max_price_cents),
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
        "forced_bet_nudge": False,
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

        result = adapter.run(
            model=spec.model,
            system_prompt=system_prompt,
            user_prompt=USER_KICKOFF,
            schemas=TOOL_SCHEMAS,
            execute=execute,
            max_turns=max_turns,
        )
        summary.update(result)

        if not ctx.bets_placed:
            forced = adapter.run(
                model=spec.model,
                system_prompt=system_prompt,
                user_prompt=FORCE_BET_KICKOFF,
                schemas=TOOL_SCHEMAS,
                execute=execute,
                max_turns=min(max_turns, FORCE_BET_MAX_TURNS),
            )
            summary["turns"] += forced.get("turns", 0)
            summary["final_text"] = forced.get("final_text", summary["final_text"])
            summary["forced_bet_nudge"] = True
            add_usage(summary["usage"], forced.get("usage"))

        summary["cost_cents"] = compute_cost_cents(spec, summary["usage"])
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return summary
