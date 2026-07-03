"""Adapter loop tests with stubbed provider clients.

These don't hit any API — they verify each adapter drives the
tool-call -> execute -> result -> final-answer loop correctly and
returns the shared summary shape.
"""

from types import SimpleNamespace

from arena.tools import TOOL_SCHEMAS

EXECUTED = []


def fake_execute(name, args):
    EXECUTED.append((name, args))
    return '{"ok": true}'


def setup_function(_):
    EXECUTED.clear()


# ---------------- Anthropic ----------------


class FakeAnthropicClient:
    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            block = SimpleNamespace(
                type="tool_use", id="tu_1", name="get_bankroll", input={}
            )
            usage = SimpleNamespace(
                input_tokens=100, output_tokens=20,
                cache_creation_input_tokens=0, cache_read_input_tokens=0,
            )
            return SimpleNamespace(stop_reason="tool_use", content=[block], usage=usage)
        text = SimpleNamespace(type="text", text="Done betting.")
        usage = SimpleNamespace(
            input_tokens=150, output_tokens=30,
            cache_creation_input_tokens=5, cache_read_input_tokens=40,
        )
        return SimpleNamespace(stop_reason="end_turn", content=[text], usage=usage)


def test_anthropic_adapter_loop(monkeypatch):
    import anthropic as anthropic_sdk
    from arena.agents import anthropic_agent

    fake = FakeAnthropicClient()
    monkeypatch.setattr(anthropic_sdk, "Anthropic", lambda: fake)
    result = anthropic_agent.run(
        model="m", system_prompt="s", user_prompt="go",
        schemas=TOOL_SCHEMAS, execute=fake_execute, max_turns=5,
    )
    assert EXECUTED == [("get_bankroll", {})]
    assert result["final_text"] == "Done betting."
    assert result["turns"] == 2
    assert result["usage"] == {
        "input_tokens": 250, "output_tokens": 50,
        "cache_write_tokens": 5, "cache_read_tokens": 40,
    }


# ---------------- OpenAI ----------------


class FakeResponses:
    """Stands in for client.responses (the Responses API)."""

    def __init__(self):
        self.calls = 0
        self.seen_previous_ids = []

    def create(self, **kwargs):
        self.calls += 1
        self.seen_previous_ids.append(kwargs.get("previous_response_id"))
        if self.calls == 1:
            fc = SimpleNamespace(
                type="function_call", name="record_note",
                arguments='{"text": "hi"}', call_id="call_1",
            )
            usage = SimpleNamespace(input_tokens=200, output_tokens=15, input_tokens_details=None)
            return SimpleNamespace(id="resp_1", output=[fc], output_text="", usage=usage)
        msg = SimpleNamespace(type="message")
        details = SimpleNamespace(cached_tokens=50)
        usage = SimpleNamespace(input_tokens=210, output_tokens=25, input_tokens_details=details)
        return SimpleNamespace(id="resp_2", output=[msg], output_text="All set.", usage=usage)


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_openai_adapter_loop(monkeypatch):
    import openai as openai_sdk
    from arena.agents import openai_agent

    fake = FakeOpenAIClient()
    monkeypatch.setattr(openai_sdk, "OpenAI", lambda: fake)
    monkeypatch.setattr(openai_agent, "OpenAI", lambda: fake)
    result = openai_agent.run(
        model="m", system_prompt="s", user_prompt="go",
        schemas=TOOL_SCHEMAS, execute=fake_execute, max_turns=5,
    )
    assert EXECUTED == [("record_note", {"text": "hi"})]
    assert result["final_text"] == "All set."
    assert result["turns"] == 2
    # second turn chains on the first response's id
    assert fake.responses.seen_previous_ids == [None, "resp_1"]
    assert result["usage"] == {
        "input_tokens": 410, "output_tokens": 40,
        "cache_write_tokens": 0, "cache_read_tokens": 50,
    }


# ---------------- Gemini ----------------


class FakeGeminiModels:
    def __init__(self):
        self.calls = 0

    def generate_content(self, **kwargs):
        from google.genai import types

        self.calls += 1
        if self.calls == 1:
            part = SimpleNamespace(
                function_call=SimpleNamespace(name="get_bankroll", args={})
            )
            content = SimpleNamespace(role="model", parts=[part])
            usage = SimpleNamespace(
                prompt_token_count=90, candidates_token_count=10,
                thoughts_token_count=0, cached_content_token_count=0,
            )
            return SimpleNamespace(
                candidates=[SimpleNamespace(content=content)], text=None, usage_metadata=usage
            )
        content = types.Content(role="model", parts=[types.Part(text="Finished.")])
        usage = SimpleNamespace(
            prompt_token_count=95, candidates_token_count=12,
            thoughts_token_count=3, cached_content_token_count=20,
        )
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=content)], text="Finished.", usage_metadata=usage
        )


def test_gemini_adapter_loop(monkeypatch):
    from google import genai as genai_sdk
    from arena.agents import gemini_agent

    fake = SimpleNamespace(models=FakeGeminiModels())
    monkeypatch.setattr(genai_sdk, "Client", lambda: fake)
    monkeypatch.setattr(gemini_agent.genai, "Client", lambda: fake)
    result = gemini_agent.run(
        model="m", system_prompt="s", user_prompt="go",
        schemas=TOOL_SCHEMAS, execute=fake_execute, max_turns=5,
    )
    assert EXECUTED == [("get_bankroll", {})]
    assert result["final_text"] == "Finished."
    assert result["turns"] == 2
    # thinking tokens (3) fold into output_tokens alongside candidates_token_count
    assert result["usage"] == {
        "input_tokens": 185, "output_tokens": 25,
        "cache_write_tokens": 0, "cache_read_tokens": 20,
    }
