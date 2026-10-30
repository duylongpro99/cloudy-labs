from cloudy_labs.chat.settings import LlmSettings, Missing, load_settings, read_env_file

FULL = {"LLM_BASE_URL": "https://api.openai.com/v1", "LLM_API_KEY": "sk-env-secret",
        "LLM_MODEL": "gpt-test", "LLM_API_FORMAT": "openai"}


def test_from_environment_only(tmp_path):
    s = load_settings(FULL, tmp_path)
    assert s == LlmSettings("https://api.openai.com/v1", "sk-env-secret", "gpt-test", "openai")


def test_from_file_only(tmp_path):
    (tmp_path / "llm.env").write_text(
        "# my provider\n\nLLM_BASE_URL=https://api.anthropic.com\nexport LLM_API_KEY='sk-file-secret'\n"
        'LLM_MODEL="claude-test"\nLLM_API_FORMAT=Anthropic\n')
    s = load_settings({}, tmp_path)
    assert s == LlmSettings("https://api.anthropic.com", "sk-file-secret", "claude-test", "anthropic")


def test_environment_wins_over_file(tmp_path):
    (tmp_path / "llm.env").write_text("LLM_API_KEY=sk-file\nLLM_MODEL=from-file\n")
    s = load_settings({**FULL, "LLM_MODEL": ""}, tmp_path)
    assert isinstance(s, LlmSettings) and s.api_key == "sk-env-secret" and s.model == "from-file"


def test_missing_names(tmp_path):
    s = load_settings({"LLM_MODEL": "x"}, tmp_path)
    assert s == Missing(["LLM_BASE_URL", "LLM_API_KEY", "LLM_API_FORMAT"])


def test_unknown_format_is_explained(tmp_path):
    s = load_settings({**FULL, "LLM_API_FORMAT": "gemini"}, tmp_path)
    assert isinstance(s, Missing) and s.names == [] and "openai" in s.error
    assert "gemini" not in s.error  # a value set in the wrong variable is never echoed


def test_base_url_needs_a_scheme(tmp_path):
    s = load_settings({**FULL, "LLM_BASE_URL": "api.openai.com"}, tmp_path)
    assert isinstance(s, Missing) and "http" in s.error


def test_repr_hides_the_key(tmp_path):
    s = load_settings(FULL, tmp_path)
    assert "sk-env-secret" not in repr(s) and "gpt-test" in repr(s)


def test_default_home_is_cloudy_labs_home(isolated_home):
    isolated_home.mkdir(parents=True)
    (isolated_home / "llm.env").write_text("\n".join(f"{k}={v}" for k, v in FULL.items()))
    assert isinstance(load_settings({}), LlmSettings)


def test_unreadable_file_is_empty(tmp_path):
    assert read_env_file(tmp_path / "nope.env") == {}


def test_file_that_is_not_text_is_empty(tmp_path):
    (tmp_path / "llm.env").write_bytes(b"LLM_MODEL=\xff\xfe")
    assert read_env_file(tmp_path / "llm.env") == {}
