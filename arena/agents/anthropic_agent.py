"""Anthropic adapter (Claude models)."""

from __future__ import annotations

from typing import Callable

import anthropic

from ..pricing import empty_usage


def run(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schemas: list[dict],
    execute: Callable[[str, dict], str],
    max_turns: int,
) -> dict:
    client = anthropic.Anthropic()
    # Native server-side web search (executed on Anthropic's side, results
    # injected automatically) alongside our client-side betting tools. This is
    # Anthropic's own search engine -- see the fairness note in the README.
    tools: list = [{"type": "web_search_20260209", "name": "web_search"}]
    tools += [
        {
            "name": s["name"],
            "description": s["description"],
            "input_schema": s["parameters"],
        }
        for s in schemas
    ]
    system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    messages: list[dict] = [{"role": "user", "content": user_prompt}]
    turns = 0
    final_text = ""
    usage = empty_usage()

    while turns < max_turns:
        turns += 1
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.usage:
            usage["input_tokens"] += response.usage.input_tokens or 0
            usage["output_tokens"] += response.usage.output_tokens or 0
            usage["cache_write_tokens"] += response.usage.cache_creation_input_tokens or 0
            usage["cache_read_tokens"] += response.usage.cache_read_input_tokens or 0

        if response.stop_reason == "refusal":
            final_text = "(model refused the request)"
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute(block.name, dict(block.input or {}))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "pause_turn":
            continue

        final_text = "\n".join(b.text for b in response.content if b.type == "text")
        break
    else:
        final_text = "(turn budget exhausted)"

    return {"turns": turns, "final_text": final_text, "usage": usage}
