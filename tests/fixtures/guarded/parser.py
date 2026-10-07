"""Number parser with one explicit failure path."""


class NegativeError(ValueError):
    """Raised when a count parses but is negative."""


def parse_count(raw):
    """Parse raw text as a non-negative int count."""
    value = int(raw)
    if value < 0:
        raise NegativeError(f"count must be non-negative, got {value}")
    return value
