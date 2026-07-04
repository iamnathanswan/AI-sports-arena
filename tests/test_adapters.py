"""Adapter loop tests with stubbed provider clients.

These don't hit any API — they verify each adapter drives the
tool-call -> execute -> result -> final-answer loop correctly and
returns the shared summary shape.
"""

from types import SimpleNamespace

from arena.agents.base import RunOptions
from arena.tools import TOOL_SCHEMAS

EXECUTED = []


def fake_execute(name, args):
    EXECUTED.append((name, args))
    return '{"ok": true}'


def setup_function(_):
    EXECUTED.clear()


def _anthropic_usage(inp=100, out=20, cw=0, cr=0):
    return SimpleNamespace(
        input_tokens=inp, output_tokens=out,
        cache_creation_input_tokens=cw, cache_read_input_tokens=cr,
    )


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
    # input excludes cached tokens (200 uncached + (210-50) uncached = 360);
    # cached 50 tracked separately so it isn't charged at the full input rate.
    assert result["usage"] == {
        "input_tokens": 360, "output_tokens": 40,
        "cache_write_tokens": 0, "cache_read_tokens": 50,
    }


# ---------------- Gemini ----------------


class FakeGeminiModels:
    def __init__(self):
        self.calls = 0
        self.configs = []

    def generate_content(self, **kwargs):
        from google.genai import types

        self.calls += 1
        self.configs.append(kwargs.get("config"))
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
    # thinking tokens (3) fold into output_tokens; input excludes cached tokens
    # (90 uncached + (95-20) uncached = 165), cached 20 tracked separately.
    assert result["usage"] == {
        "input_tokens": 165, "output_tokens": 25,
        "cache_write_tokens": 0, "cache_read_tokens": 20,
    }
    # google_search + function calling in one request requires this flag, or
    # Gemini 3 rejects the call with INVALID_ARGUMENT.
    cfg = fake.models.configs[0]
    assert cfg.tool_config.include_server_side_tool_invocations is True


# ---------------- Cost-control options (Anthropic as representative) ----------------


class ConfigurableAnthropicClient:
    """Fake whose per-turn behavior is scripted, and which records the kwargs
    passed to messages.create (to check effort / max_uses wiring)."""

    def __init__(self, script):
        # script: list of ("tool"|"end", usage) describing each turn's response
        self.script = script
        self.turn = 0
        self.create_kwargs = []
        self.message_snapshots = []  # copy of messages at each call (list is mutated in place)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        self.message_snapshots.append(list(kwargs.get("messages", [])))
        kind, usage = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        if kind == "tool":
            block = SimpleNamespace(type="tool_use", id=f"tu_{self.turn}", name="get_bankroll", input={})
            return SimpleNamespace(stop_reason="tool_use", content=[block], usage=usage)
        text = SimpleNamespace(type="text", text="done")
        return SimpleNamespace(stop_reason="end_turn", content=[text], usage=usage)


def _patch_anthropic(monkeypatch, client):
    import anthropic as anthropic_sdk
    from arena.agents import anthropic_agent
    monkeypatch.setattr(anthropic_sdk, "Anthropic", lambda: client)


def test_anthropic_effort_and_search_cap_wired(monkeypatch):
    from arena.agents import anthropic_agent

    client = ConfigurableAnthropicClient([("end", _anthropic_usage())])
    _patch_anthropic(monkeypatch, client)
    anthropic_agent.run(
        model="m", system_prompt="s", user_prompt="go", schemas=TOOL_SCHEMAS,
        execute=fake_execute, max_turns=5,
        options=RunOptions(effort="medium", max_searches=5),
    )
    kwargs = client.create_kwargs[0]
    assert kwargs["output_config"] == {"effort": "medium"}
    web_search = kwargs["tools"][0]
    assert web_search["type"] == "web_search_20260209"
    assert web_search["max_uses"] == 5


def test_anthropic_in_session_followup(monkeypatch):
    """Model ends without betting; should_continue True -> adapter injects the
    followup and continues the SAME conversation once, no second run()."""
    from arena.agents import anthropic_agent

    client = ConfigurableAnthropicClient([("end", _anthropic_usage()), ("end", _anthropic_usage())])
    _patch_anthropic(monkeypatch, client)
    bets = []
    result = anthropic_agent.run(
        model="m", system_prompt="s", user_prompt="go", schemas=TOOL_SCHEMAS,
        execute=fake_execute, max_turns=5,
        options=RunOptions(
            followup_prompt="PLACE A BET NOW",
            should_continue=lambda: not bets,  # never bets -> always wants followup
        ),
    )
    assert result["forced_followup"] is True
    # create called twice: initial end, then again after the followup injection
    assert len(client.create_kwargs) == 2
    # the followup was appended as a user turn on the second call
    assert client.message_snapshots[1][-1] == {"role": "user", "content": "PLACE A BET NOW"}


def test_anthropic_followup_not_triggered_when_bet_placed(monkeypatch):
    from arena.agents import anthropic_agent

    client = ConfigurableAnthropicClient([("end", _anthropic_usage())])
    _patch_anthropic(monkeypatch, client)
    result = anthropic_agent.run(
        model="m", system_prompt="s", user_prompt="go", schemas=TOOL_SCHEMAS,
        execute=fake_execute, max_turns=5,
        options=RunOptions(followup_prompt="X", should_continue=lambda: False),
    )
    assert result["forced_followup"] is False
    assert len(client.create_kwargs) == 1


def test_anthropic_cost_ceiling_stops_session(monkeypatch):
    """Budget exceeded after turn 1 -> session stops even though the model
    asked for another tool call."""
    from arena.agents import anthropic_agent

    # turn 1 asks for a tool (would normally continue), but usage is huge
    client = ConfigurableAnthropicClient([("tool", _anthropic_usage(inp=10_000_000))])
    _patch_anthropic(monkeypatch, client)
    result = anthropic_agent.run(
        model="m", system_prompt="s", user_prompt="go", schemas=TOOL_SCHEMAS,
        execute=fake_execute, max_turns=10,
        options=RunOptions(budget_cents=10, cost_of=lambda u: u["input_tokens"] // 1000),
    )
    assert "cost ceiling" in result["final_text"]
    assert len(client.create_kwargs) == 1  # stopped after the first turn
