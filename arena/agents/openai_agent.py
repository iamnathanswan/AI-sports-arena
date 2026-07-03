"""OpenAI adapter (GPT models), via the Responses API.

Uses the Responses API (not the legacy Chat Completions) so the model can use
OpenAI's native web_search tool alongside our custom betting functions in the
same request. Server-side conversation state is chained with
previous_response_id, so each turn only sends the new tool outputs.

web_search here is OpenAI's own search engine -- see the fairness note in the
README about comparing across different native search backends.
"""

from __future__ import annotations

import json
from typing import Callable

from openai import OpenAI

from ..pricing import empty_usage


def run(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schemas: list[dict],
    execute: Callable[[str, dict], str],
    max_turns: int,
) -> dict:
    client = OpenAI()
    # Responses-API tool shapes: built-in web_search + flattened function tools
    # (name/description/parameters at top level, not nested under "function").
    tools: list = [{"type": "web_search"}]
    tools += [
        {
            "type": "function",
            "name": s["name"],
            "description": s["description"],
            "parameters": s["parameters"],
        }
        for s in schemas
    ]

    turns = 0
    final_text = ""
    usage = empty_usage()
    previous_response_id: str | None = None
    pending_input: list = [{"role": "user", "content": user_prompt}]

    while turns < max_turns:
        turns += 1
        kwargs: dict = {
            "model": model,
            "tools": tools,
            "instructions": system_prompt,
            "input": pending_input,
        }
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id

        response = client.responses.create(**kwargs)
        previous_response_id = response.id

        if response.usage:
            usage["input_tokens"] += response.usage.input_tokens or 0
            usage["output_tokens"] += response.usage.output_tokens or 0
            details = getattr(response.usage, "input_tokens_details", None)
            usage["cache_read_tokens"] += (
                (getattr(details, "cached_tokens", 0) or 0) if details else 0
            )

        function_calls = [
            item for item in response.output if getattr(item, "type", None) == "function_call"
        ]
        if not function_calls:
            final_text = response.output_text or ""
            break

        pending_input = []
        for fc in function_calls:
            try:
                args = json.loads(fc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute(fc.name, args)
            pending_input.append(
                {"type": "function_call_output", "call_id": fc.call_id, "output": result}
            )
    else:
        final_text = "(turn budget exhausted)"

    return {"turns": turns, "final_text": final_text, "usage": usage}
