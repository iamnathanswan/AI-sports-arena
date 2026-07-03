"""OpenAI adapter (GPT models), via Chat Completions function calling."""

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
    tools = [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
            },
        }
        for s in schemas
    ]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    turns = 0
    final_text = ""
    usage = empty_usage()

    while turns < max_turns:
        turns += 1
        response = client.chat.completions.create(model=model, messages=messages, tools=tools)
        if response.usage:
            usage["input_tokens"] += response.usage.prompt_tokens or 0
            usage["output_tokens"] += response.usage.completion_tokens or 0
            details = response.usage.prompt_tokens_details
            usage["cache_read_tokens"] += (getattr(details, "cached_tokens", 0) or 0) if details else 0
        message = response.choices[0].message
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls]
                if message.tool_calls
                else None,
            }
        )

        if not message.tool_calls:
            final_text = message.content or ""
            break

        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    else:
        final_text = "(turn budget exhausted)"

    return {"turns": turns, "final_text": final_text, "usage": usage}
