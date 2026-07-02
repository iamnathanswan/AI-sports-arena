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
from ..tools import TOOL_SCHEMAS, ToolContext, execute_tool

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
USER_KICKOFF = "Begin your weekly betting session now."

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
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return summary
