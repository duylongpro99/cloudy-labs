import asyncio
import json

import httpx
import pytest

from cloudy_labs.chat.provider import ProviderError, api_root, complete
from cloudy_labs.chat.settings import LlmSettings

KEY = "sk-very-secret-key"
OPENAI = LlmSettings("https://llm.example/v1", KEY, "gpt-test", "openai")
ANTHROPIC = LlmSettings("https://llm.example", KEY, "claude-test", "anthropic")
MESSAGES = [{"role": "user", "content": "make a VPC"}]


def call(settings, handler, **kw):
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as client:
            return await complete(settings, "SYSTEM", MESSAGES, client=client, **kw)

    return asyncio.run(go()), seen


@pytest.mark.parametrize("base, root", [
    ("https://llm.example", "https://llm.example"),
    ("https://llm.example/", "https://llm.example"),
    ("https://llm.example/v1", "https://llm.example"),
    ("https://llm.example/v1/", "https://llm.example"),
    ("https://openrouter.ai/api/v1", "https://openrouter.ai/api"),
])
def test_api_root(base, root):
    assert api_root(base) == root


def test_openai_request_and_reply():
    text, [req] = call(OPENAI, lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}))
    assert text == "hi"
    assert str(req.url) == "https://llm.example/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}" and "x-api-key" not in req.headers
    body = json.loads(req.content)
    assert body["model"] == "gpt-test" and body["temperature"] == 0
    assert body["messages"] == [{"role": "system", "content": "SYSTEM"}, *MESSAGES]


def test_anthropic_request_and_reply():
    reply = {"content": [{"type": "text", "text": "a"}, {"type": "thinking", "thinking": "x"}, {"type": "text", "text": "b"}]}
    text, [req] = call(ANTHROPIC, lambda r: httpx.Response(200, json=reply))
    assert text == "ab"
    assert str(req.url) == "https://llm.example/v1/messages"
    assert req.headers["x-api-key"] == KEY and req.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in req.headers
    body = json.loads(req.content)
    assert body["model"] == "claude-test" and body["system"] == "SYSTEM" and body["messages"] == MESSAGES
    assert body["max_tokens"] > 0


@pytest.mark.parametrize("status, hint", [(401, "LLM_API_KEY"), (404, "LLM_BASE_URL"), (500, "HTTP 500")])
def test_http_errors_are_explained_and_redacted(status, hint):
    with pytest.raises(ProviderError) as e:
        call(OPENAI, lambda r: httpx.Response(status, text=f"bad key {KEY} " + "x" * 1000))
    message = str(e.value)
    assert hint in message and KEY not in message and "***" in message
    assert "https://llm.example/v1/chat/completions" in message and len(message) < 500


def test_timeout():
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderError, match="did not answer within 5 seconds"):
        call(OPENAI, slow, timeout=5)


def test_connection_error():
    def down(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderError, match="could not reach"):
        call(OPENAI, down)


@pytest.mark.parametrize("settings, body", [(OPENAI, {"choices": []}), (ANTHROPIC, {"id": "x"})])
def test_reply_of_the_wrong_shape(settings, body):
    with pytest.raises(ProviderError, match="LLM_API_FORMAT"):
        call(settings, lambda r: httpx.Response(200, json=body))


def test_reply_that_is_not_json():
    with pytest.raises(ProviderError, match="JSON"):
        call(OPENAI, lambda r: httpx.Response(200, text="<html>"))


def test_key_is_not_logged(caplog):
    import logging

    with caplog.at_level(logging.DEBUG):
        call(OPENAI, lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}))
        with pytest.raises(ProviderError):
            call(ANTHROPIC, lambda r: httpx.Response(401, text=f"bad {KEY}"))
    assert KEY not in caplog.text


def test_malformed_base_url():
    with pytest.raises(ProviderError, match="could not reach"):
        call(LlmSettings("http://\x00bad", KEY, "m", "openai"), lambda r: httpx.Response(200))


def test_anthropic_blocks_that_are_not_text_are_skipped():
    body = {"content": ["odd", {"type": "text", "text": 5}, {"type": "text", "text": "hi"}]}
    assert call(ANTHROPIC, lambda r: httpx.Response(200, json=body))[0] == "hi"
