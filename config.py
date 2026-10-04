"""Centralized configuration loading and validation.

Nothing in this module ever prints or logs `groq_api_key`. `Settings.__repr__`
deliberately omits it (see the `repr=False` field metadata below) so that an
accidental `print(settings)` or an error message built from `repr(settings)`
never leaks the key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from errors import ConfigError


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got: {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got: {value}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = field(repr=False)
    groq_model: str
    langsmith_tracing: bool
    max_iterations: int
    clone_timeout_seconds: int
    max_repo_files: int
    max_repo_total_bytes: int
    max_file_bytes: int
    max_evidence_chars: int


def load_settings(require_api_key: bool = True) -> Settings:
    """Load and validate configuration from the environment.

    Raises ConfigError with a short, actionable message (never the value of
    any secret) if required configuration is missing or malformed.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if require_api_key and not api_key:
        raise ConfigError(
            "GROQ_API_KEY is not configured. Copy .env.example to .env and "
            "set your key."
        )

    return Settings(
        groq_api_key=api_key,
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
        langsmith_tracing=_bool_env("LANGSMITH_TRACING", False),
        max_iterations=_int_env("SHIRABE_MAX_ITERATIONS", 3),
        clone_timeout_seconds=_int_env("SHIRABE_CLONE_TIMEOUT_SECONDS", 120),
        max_repo_files=_int_env("SHIRABE_MAX_REPO_FILES", 4000),
        max_repo_total_bytes=_int_env("SHIRABE_MAX_REPO_TOTAL_BYTES", 200_000_000),
        max_file_bytes=_int_env("SHIRABE_MAX_FILE_BYTES", 500_000),
        max_evidence_chars=_int_env("SHIRABE_MAX_EVIDENCE_CHARS", 30_000),
    )
