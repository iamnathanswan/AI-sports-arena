"""Google adapter (Gemini models), via the google-genai SDK."""

from __future__ import annotations

import json
from typing import Callable

from google import genai
from google.genai import types

from ..pricing import empty_usage
from .base import RunOptions

_THINKING_LEVEL = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


def _thinking_config(effort: str | None):
    """Map the shared effort level to a Gemini ThinkingConfig, defensively --
    a bad/unknown value just leaves thinking at the model default."""
    if not effort:
        return None
    level_name = _THINKING_LEVEL.get(effort.lower())
    if not level_name or not hasattr(types, "ThinkingLevel"):
        return None
    try:
        level = getattr(types.ThinkingLevel, level_name)
        return types.ThinkingConfig(thinking_level=level)
    except Exception:
        return None


def run(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schemas: list[dict],
    execute: Callable[[str, dict], str],
    max_turns: int,
    options: RunOptions | None = None,
) -> dict:
    options = options or RunOptions()
    client = genai.Client()  # reads GEMINI_API_KEY
    declarations = [
        {"name": s["name"], "description": s["description"], "parameters": s["parameters"]}
        for s in schemas
    ]

    # Google Search grounding (native, server-side) alongside our custom
    # function tools -- supported together on Gemini 3+. This is Google's own
    # search; see the fairness note in the README. Each grounded query Gemini
    # runs is separately billed by Google.
    config_kwargs: dict = {
        "system_instruction": system_prompt,
        "tools": [
            types.Tool(function_declarations=declarations),
            types.Tool(google_search=types.GoogleSearch()),
        ],
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    thinking = _thinking_config(options.effort)
    if thinking is not None:
        config_kwargs["thinking_config"] = thinking
    config = types.GenerateContentConfig(**config_kwargs)

    contents: list = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
    turns = 0
    final_text = ""
    usage = empty_usage()
    injected_followup = False

    while turns < max_turns:
        turns += 1
        response = client.models.generate_content(model=model, contents=contents, config=config)
        um = response.usage_metadata
        if um:
            usage["input_tokens"] += um.prompt_token_count or 0
            # Thinking tokens are billed as output on Gemini's pricing model.
            usage["output_tokens"] += (um.candidates_token_count or 0) + (
                getattr(um, "thoughts_token_count", 0) or 0
            )
            usage["cache_read_tokens"] += getattr(um, "cached_content_token_count", 0) or 0
        candidate = response.candidates[0]
        contents.append(candidate.content)

        if options.over_budget(usage):
            final_text = "(stopped early: session cost ceiling reached)"
            break

        function_calls = [
            part.function_call
            for part in (candidate.content.parts or [])
            if getattr(part, "function_call", None)
        ]
        if not function_calls:
            if not injected_followup and options.wants_followup():
                injected_followup = True
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=options.followup_prompt)])
                )
                continue
            final_text = response.text or ""
            break

        response_parts = []
        for fc in function_calls:
            result = execute(fc.name, dict(fc.args or {}))
            response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response={"result": json.loads(result)}
                )
            )
        contents.append(types.Content(role="tool", parts=response_parts))
    else:
        final_text = "(turn budget exhausted)"

    return {
        "turns": turns,
        "final_text": final_text,
        "usage": usage,
        "forced_followup": injected_followup,
    }
