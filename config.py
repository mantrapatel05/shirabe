"""Centralized configuration loading and validation.

Nothing in this module ever prints or logs `openrouter_api_key`. `Settings.__repr__`
deliberately omits it (see the `repr=False` field metadata below) so that an
accidental `print(settings)` or an error message built from `repr(settings)`
never leaks the key.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from dataclasses import dataclass, field

from errors import ConfigError

DEFAULT_MAX_EVIDENCE_CHARS = 30_000

# Environment variables that switch LangSmith/LangChain tracing on. Fixture,
# demo, and benchmark paths force these off so keyless runs never emit
# traces; the live CLI path sets them explicitly only when tracing is
# configured with a key.
TRACING_ENV_VARS = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")


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
    openrouter_api_key: str = field(repr=False)
    openrouter_model: str
    langsmith_tracing: bool
    langsmith_api_key: str = field(repr=False)
    langsmith_project: str
    max_iterations: int
    clone_timeout_seconds: int
    max_repo_files: int
    max_repo_total_bytes: int
    max_file_bytes: int
    max_evidence_chars: int


@contextlib.contextmanager
def tracing_disabled() -> Iterator[None]:
    """Force tracing off for the wrapped block, then restore the environment.

    Keyless paths (tests, fixture benchmark, no-key demo) run inside this so
    a stray LANGSMITH_TRACING=true in the environment can never emit traces
    containing questions or repository excerpts.
    """
    saved = {name: os.environ.get(name) for name in TRACING_ENV_VARS}
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def load_settings(require_api_key: bool = True) -> Settings:
    """Load and validate configuration from the environment.

    Raises ConfigError with a short, actionable message (never the value of
    any secret) if required configuration is missing or malformed.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if require_api_key and not api_key:
        raise ConfigError(
            "OPENROUTER_API_KEY is not configured. Copy .env.example to .env and "
            "set your key."
        )

    tracing = _bool_env("LANGSMITH_TRACING", False)
    tracing_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    if tracing and not tracing_key:
        raise ConfigError(
            "LANGSMITH_TRACING is enabled but LANGSMITH_API_KEY is not configured. "
            "Add your key or set LANGSMITH_TRACING=false."
        )

    return Settings(
        openrouter_api_key=api_key,
        openrouter_model=os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free").strip(),
        langsmith_tracing=tracing,
        langsmith_api_key=tracing_key,
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "shirabe").strip(),
        max_iterations=_int_env("SHIRABE_MAX_ITERATIONS", 3),
        clone_timeout_seconds=_int_env("SHIRABE_CLONE_TIMEOUT_SECONDS", 120),
        max_repo_files=_int_env("SHIRABE_MAX_REPO_FILES", 4000),
        max_repo_total_bytes=_int_env("SHIRABE_MAX_REPO_TOTAL_BYTES", 200_000_000),
        max_file_bytes=_int_env("SHIRABE_MAX_FILE_BYTES", 500_000),
        max_evidence_chars=_int_env("SHIRABE_MAX_EVIDENCE_CHARS", DEFAULT_MAX_EVIDENCE_CHARS),
    )
