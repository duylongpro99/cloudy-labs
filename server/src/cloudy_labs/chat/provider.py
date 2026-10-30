"""One completion from the learner's LLM, in the OpenAI or Anthropic wire format (PRD F5.5).

Plain HTTP with httpx: no provider SDKs. The key goes only into the request header; every
error message is redacted before it can reach the browser, and nothing here logs a request
or a response.
"""

from typing import Literal, TypedDict

import httpx

from .settings import LlmSettings

ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 4096
ERROR_BODY_MAX = 300


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class ProviderError(Exception):
    """A message for the learner: what went wrong talking to their provider, without the key."""


def redact(text: str, settings: LlmSettings) -> str:
    return text.replace(settings.api_key, "***") if settings.api_key else text


def api_root(base_url: str) -> str:
    """The base URL without a trailing `/` or `/v1`: both `https://api.openai.com` and
    `https://api.openai.com/v1` work."""
    root = base_url.rstrip("/")
    return root.removesuffix("/v1")


def _request(settings: LlmSettings, system: str, messages: list[Message]) -> tuple[str, dict[str, str], dict]:
    root = api_root(settings.base_url)
    if settings.api_format == "anthropic":
        headers = {"x-api-key": settings.api_key, "anthropic-version": ANTHROPIC_VERSION}
        body = {"model": settings.model, "system": system, "messages": list(messages),
                "max_tokens": MAX_TOKENS, "temperature": 0}
        return f"{root}/v1/messages", headers, body
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    body = {"model": settings.model, "messages": [{"role": "system", "content": system}, *messages], "temperature": 0}
    return f"{root}/v1/chat/completions", headers, body


def _text(settings: LlmSettings, data: object) -> str | None:
    try:
        if settings.api_format == "anthropic":
            blocks = data["content"]  # type: ignore[index]
            return "".join(b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
        content = data["choices"][0]["message"]["content"]  # type: ignore[index]
        return content if isinstance(content, str) else None
    except (KeyError, IndexError, TypeError):
        return None


async def complete(settings: LlmSettings, system: str, messages: list[Message], *,
                   client: httpx.AsyncClient | None = None, timeout: float = 60) -> str:
    """The model's reply text. Raises ProviderError with a redacted message."""
    url, headers, body = _request(settings, system, messages)
    owned = client is None
    client = client or httpx.AsyncClient()
    try:
        response = await client.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException:
        raise ProviderError(redact(f"{settings.model} did not answer within {timeout:g} seconds ({url})", settings)) from None
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        raise ProviderError(redact(f"could not reach {url}: {type(e).__name__}: {e}", settings)) from None
    finally:
        if owned:
            await client.aclose()
    if not response.is_success:
        hint = " (check LLM_API_KEY)" if response.status_code in (401, 403) else \
               " (check LLM_BASE_URL and LLM_MODEL)" if response.status_code == 404 else ""
        detail = response.text[:ERROR_BODY_MAX]
        raise ProviderError(redact(f"{url} answered HTTP {response.status_code}{hint}: {detail}", settings))
    try:
        data = response.json()
    except ValueError:
        raise ProviderError(redact(f"{url} did not answer with JSON: {response.text[:ERROR_BODY_MAX]}", settings)) from None
    text = _text(settings, data)
    if text is None:
        shape = "choices[0].message.content" if settings.api_format == "openai" else "content[].text"
        raise ProviderError(redact(f"{url} answered without {shape}; is LLM_API_FORMAT right?", settings))
    return text
