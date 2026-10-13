import json

import httpx
import pytest
import respx

from axiom.config import get_settings
from axiom.llm.client import LLMClient, TokenBudget
from axiom.llm.providers import ProviderSpec, build_chain
from axiom.llm.types import AllProvidersFailed, BudgetExceeded, LLMError

A = ProviderSpec("alpha", "https://alpha.test/v1", "k", "model-a")
B = ProviderSpec("beta", "https://beta.test/v1", "k", "model-b")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    get_settings.cache_clear()
    from axiom.llm import client as _client

    _client._COOLDOWN.clear()  # cooldowns are process-wide by design; isolate tests
    yield
    get_settings.cache_clear()


def completion(content="hi", tool_calls=None, usage=(10, 5), model="m"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)},
    }


MSGS = [{"role": "user", "content": "hello"}]


@respx.mock
async def test_basic_completion_strips_think_blocks():
    respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion("<think>secret plan</think>Answer: 42"))
    )
    res = await LLMClient([A], cache_mode="off").chat(MSGS)
    assert res.content == "Answer: 42" and res.provider == "alpha" and res.usage.total == 15


@respx.mock
async def test_tool_calls_parsed_and_bad_json_arguments_flagged():
    calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "get_indicators", "arguments": '{"ticker": "AAPL"}'},
        },
        {"id": "c2", "type": "function", "function": {"name": "get_regime", "arguments": "{not json"}},
    ]
    respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion("", calls))
    )
    res = await LLMClient([A], cache_mode="off").chat(
        MSGS, tools=[{"type": "function", "function": {"name": "x"}}]
    )
    assert res.tool_calls[0].arguments == {"ticker": "AAPL"}
    assert "__error__" in res.tool_calls[1].arguments
    msg = res.assistant_message()
    assert msg["tool_calls"][0]["function"]["name"] == "get_indicators"


@respx.mock
async def test_429_with_long_retry_after_fails_over_and_cools_down():
    a = respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            429, headers={"retry-after": "120"}, json={"error": {"message": "slow down"}}
        )
    )
    b = respx.post("https://beta.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion("from beta"))
    )
    events = []
    client = LLMClient([A, B], cache_mode="off")
    res = await client.chat(MSGS, trace=lambda t, d: events.append((t, d)))
    assert res.provider == "beta" and res.content == "from beta"
    assert any(t == "guardrail" and d["name"] == "provider_failover" for t, d in events)
    await client.chat(MSGS)  # alpha is now cooling down: not called again
    assert a.call_count == 1 and b.call_count == 2


@respx.mock
async def test_short_retry_after_is_waited_out_once(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("axiom.llm.client.asyncio.sleep", fake_sleep)
    route = respx.post("https://alpha.test/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"message": "x"}}),
            httpx.Response(200, json=completion("ok after wait")),
        ]
    )
    res = await LLMClient([A], cache_mode="off").chat(MSGS)
    assert res.content == "ok after wait" and slept == [2.0] and route.call_count == 2


@respx.mock
async def test_all_providers_failing_raises_with_per_provider_reasons():
    respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "x"}})
    )
    respx.post("https://beta.test/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}})
    )
    with pytest.raises(AllProvidersFailed) as e:
        await LLMClient([A, B], cache_mode="off").chat(MSGS)
    assert set(e.value.errors) == {"alpha", "beta"} and "401" in e.value.errors["beta"]


async def test_no_providers_configured_has_helpful_error():
    with pytest.raises(AllProvidersFailed) as e:
        await LLMClient([], cache_mode="off").chat(MSGS)
    assert "no providers configured" in str(e.value)


@respx.mock
async def test_cache_hit_skips_network_and_replay_mode_never_calls_out():
    route = respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion("cached!"))
    )
    client = LLMClient([A], cache_mode="readwrite")
    first = await client.chat(MSGS)
    second = await client.chat(MSGS)
    assert route.call_count == 1 and second.cached and second.content == first.content == "cached!"

    replay = LLMClient([A], cache_mode="replay")
    assert (await replay.chat(MSGS)).content == "cached!"  # replays recorded response
    with pytest.raises(LLMError, match="replay"):
        await replay.chat([{"role": "user", "content": "never seen"}])
    assert route.call_count == 1


@respx.mock
async def test_budget_enforced_and_cached_calls_are_free():
    respx.post("https://alpha.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion("x", usage=(60, 40)))
    )
    budget = TokenBudget(max_tokens=150, max_calls=10)
    client = LLMClient([A], budget=budget, cache_mode="off")
    await client.chat(MSGS)
    await client.chat(MSGS)  # 200 tokens used
    with pytest.raises(BudgetExceeded):
        await client.chat(MSGS)
    assert budget.snapshot()["calls"] == 2

    calls_cap = TokenBudget(max_tokens=10**6, max_calls=1)
    c2 = LLMClient([A], budget=calls_cap, cache_mode="off")
    await c2.chat(MSGS)
    with pytest.raises(BudgetExceeded, match="call budget"):
        await c2.chat(MSGS)


@respx.mock
async def test_usage_estimated_when_provider_omits_it():
    body = completion("twelve chars")
    body["usage"] = None
    respx.post("https://alpha.test/v1/chat/completions").mock(return_value=httpx.Response(200, json=body))
    res = await LLMClient([A], cache_mode="off").chat([{"role": "user", "content": "x" * 400}])
    assert res.usage.total >= 100


def test_chain_skips_unconfigured_providers_and_validates_names(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("LLM_CHAIN", "groq,gemini,ollama")
    get_settings.cache_clear()
    assert [p.name for p in build_chain()] == ["groq", "ollama"]  # gemini has no key
    monkeypatch.setenv("LLM_CHAIN", "groq,bogus")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="bogus"):
        build_chain()


def test_request_key_is_provider_independent():
    from axiom.llm.client import _request_key

    assert _request_key(MSGS, None, 0.2, 100) == _request_key(json.loads(json.dumps(MSGS)), None, 0.2, 100)
    assert _request_key(MSGS, None, 0.2, 100) != _request_key(MSGS, None, 0.3, 100)


def test_local_ollama_is_skipped_on_serverless_hosts(monkeypatch):
    from axiom.llm import providers

    monkeypatch.setenv("LLM_CHAIN", "groq,ollama")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    get_settings.cache_clear()
    monkeypatch.setattr(providers, "ON_SERVERLESS", True)
    assert [p.name for p in build_chain()] == ["groq"]
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.com/v1")  # a real remote Ollama is kept
    get_settings.cache_clear()
    assert [p.name for p in build_chain()] == ["groq", "ollama"]
    get_settings.cache_clear()
