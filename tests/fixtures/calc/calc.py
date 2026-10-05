# Miniature fixture for Shirabe evaluation (original example, MIT, see ../README.md).
"""Tiny calculator used to test single-file behavior questions."""


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def total(values):
    """Return the sum of every number in values."""
    result = 0
    for value in values:
        result = add(result, value)
    return result
