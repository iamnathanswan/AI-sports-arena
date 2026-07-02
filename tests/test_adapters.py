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
            return SimpleNamespace(stop_reason="tool_use", content=[block])
        text = SimpleNamespace(type="text", text="Done betting.")
        return SimpleNamespace(stop_reason="end_turn", content=[text])


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


# ---------------- OpenAI ----------------


class FakeToolCall:
    def __init__(self):
        self.id = "call_1"
        self.function = SimpleNamespace(name="record_note", arguments='{"text": "hi"}')

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": "record_note", "arguments": '{"text": "hi"}'},
        }


class FakeOpenAIClient:
    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            msg = SimpleNamespace(content=None, tool_calls=[FakeToolCall()])
        else:
            msg = SimpleNamespace(content="All set.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


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
            return SimpleNamespace(candidates=[SimpleNamespace(content=content)], text=None)
        content = types.Content(role="model", parts=[types.Part(text="Finished.")])
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=content)], text="Finished."
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
