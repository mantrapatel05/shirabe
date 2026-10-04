import pytest

from config import load_settings
from errors import ConfigError


def test_missing_api_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        load_settings()


def test_api_key_not_required_mode(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = load_settings(require_api_key=False)
    assert settings.groq_api_key == ""


def test_defaults_are_applied(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    for var in [
        "GROQ_MODEL", "LANGSMITH_TRACING", "SHIRABE_MAX_ITERATIONS",
        "SHIRABE_CLONE_TIMEOUT_SECONDS", "SHIRABE_MAX_REPO_FILES",
        "SHIRABE_MAX_REPO_TOTAL_BYTES", "SHIRABE_MAX_FILE_BYTES",
        "SHIRABE_MAX_EVIDENCE_CHARS",
    ]:
        monkeypatch.delenv(var, raising=False)

    settings = load_settings()
    assert settings.groq_model == "openai/gpt-oss-120b"
    assert settings.langsmith_tracing is False
    assert settings.max_iterations == 3
    assert settings.clone_timeout_seconds == 120
    assert settings.max_repo_files == 4000
    assert settings.max_repo_total_bytes == 200_000_000
    assert settings.max_file_bytes == 500_000
    assert settings.max_evidence_chars == 30_000


def test_custom_int_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("SHIRABE_MAX_ITERATIONS", "5")
    settings = load_settings()
    assert settings.max_iterations == 5


def test_invalid_int_env_raises(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("SHIRABE_MAX_ITERATIONS", "not_a_number")
    with pytest.raises(ConfigError, match="must be an integer"):
        load_settings()


def test_non_positive_int_env_raises(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("SHIRABE_MAX_ITERATIONS", "0")
    with pytest.raises(ConfigError, match="must be a positive integer"):
        load_settings()


def test_bool_parsing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    for truthy in ["1", "true", "True", "YES", "on"]:
        monkeypatch.setenv("LANGSMITH_TRACING", truthy)
        assert load_settings().langsmith_tracing is True

    for falsy in ["0", "false", "no", "off", "anything"]:
        monkeypatch.setenv("LANGSMITH_TRACING", falsy)
        assert load_settings().langsmith_tracing is False


def test_repr_and_str_never_contain_api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-key-12345")
    settings = load_settings()
    assert "super-secret-key-12345" not in repr(settings)
    assert "super-secret-key-12345" not in str(settings)
