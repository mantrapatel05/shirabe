"""Token check: validates a bearer token against a fixed allowlist."""


ALLOWED_TOKENS = frozenset({"dev-token"})


def is_authorized(token):
    """Return True only for tokens in the static allowlist."""
    return token in ALLOWED_TOKENS
