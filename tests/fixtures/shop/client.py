"""HTTP client honoring the configured timeout default."""

from config import DEFAULT_TIMEOUT_SECONDS


def fetch(url, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Fetch a URL, waiting at most timeout seconds for a response."""
    return _get(url, timeout=timeout)


def _get(url, timeout):
    """Low-level GET. Implemented elsewhere in this miniature example."""
    raise NotImplementedError("miniature fixture has no network layer")
