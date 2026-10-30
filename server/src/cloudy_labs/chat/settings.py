"""Which LLM the chat calls (PRD F5.5, F5.7). The learner brings their own provider and key.

Read from the environment, then from `llm.env` (`KEY=VALUE` lines) in CLOUDY_LABS_HOME, which
lives outside the repo. The environment wins. Read again on every request, so editing the file
needs no server restart. The key is only ever sent in the header of a request to the provider.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..config import home

ENV_FILE = "llm.env"
NAMES = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_API_FORMAT")
FORMATS = ("openai", "anthropic")
ApiFormat = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    api_format: ApiFormat


@dataclass(frozen=True)
class Missing:
    """The chat is off: these settings are not set, or `error` says why the ones set are unusable."""
    names: list[str]
    error: str | None = None


def read_env_file(path: Path) -> dict[str, str]:
    """`KEY=VALUE` lines; blank lines and `#` comments skipped, surrounding quotes removed."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def load_settings(environ: Mapping[str, str] | None = None, home_dir: Path | None = None) -> LlmSettings | Missing:
    environ = os.environ if environ is None else environ
    from_file = read_env_file((home_dir or home()) / ENV_FILE)
    values = {name: (environ.get(name) or from_file.get(name) or "").strip() for name in NAMES}
    if missing := [name for name in NAMES if not values[name]]:
        return Missing(missing)
    api_format = values["LLM_API_FORMAT"].lower()
    if api_format not in FORMATS:
        return Missing([], "LLM_API_FORMAT must be openai (OpenAI, OpenRouter, Ollama "
                           "and other OpenAI-compatible endpoints) or anthropic")
    if not values["LLM_BASE_URL"].startswith(("http://", "https://")):
        return Missing([], "LLM_BASE_URL must start with http:// or https://, for example https://api.openai.com/v1")
    return LlmSettings(values["LLM_BASE_URL"], values["LLM_API_KEY"], values["LLM_MODEL"], api_format)  # type: ignore[arg-type]
