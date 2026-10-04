"""Central exception hierarchy for Shirabe.

All errors that should be shown to the CLI user (as opposed to raw bugs)
inherit from ShirabeError. main.py catches ShirabeError at the top level and
prints a short, sanitized message instead of a raw traceback.
"""


class ShirabeError(Exception):
    """Base class for expected, user-facing Shirabe failures."""


class ConfigError(ShirabeError):
    """Required configuration is missing or invalid."""


class RepositoryError(ShirabeError):
    """A repository could not be cloned, read, or satisfies no budget."""


class ProviderError(ShirabeError):
    """The model provider call failed or returned unusable output."""
