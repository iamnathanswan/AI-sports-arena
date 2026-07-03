"""Google adapter (Gemini models), via the google-genai SDK."""

from __future__ import annotations

import json
from typing import Callable

from google import genai
from google.genai import types

from ..pricing import empty_usage


def run(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schemas: list[dict],
    execute: Callable[[str, dict], str],
    max_turns: int,
) -> dict:
    client = genai.Client()  # reads GEMINI_API_KEY
    declarations = [
        {
            "name": s["name"],
            "description": s["description"],
            "parameters": s["parameters"],
        }
        for s in schemas
    ]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents: list = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
    turns = 0
    final_text = ""
    usage = empty_usage()

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

        function_calls = [
            part.function_call
            for part in (candidate.content.parts or [])
            if getattr(part, "function_call", None)
        ]
        if not function_calls:
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

    return {"turns": turns, "final_text": final_text, "usage": usage}
