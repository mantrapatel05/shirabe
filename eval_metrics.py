"""Deterministic evaluation metrics with explicit denominators.

Every metric returns a MetricValue carrying its numerator and denominator,
so a report can never present a bare fraction. Metrics that need human
judgment (claim support) report "no score" instead of 0 when unlabeled.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricValue:
    value: float | None
    numerator: int
    denominator: int
    note: str = ""


def ranges_overlap(first: tuple[str, int, int], second: tuple[str, int, int]) -> bool:
    return first[0] == second[0] and first[1] <= second[2] and second[1] <= first[2]


def file_recall_at_k(
    retrieved_files: list[str], relevant_files: set[str], k: int
) -> MetricValue:
    """Fraction of relevant files present in the first k retrieved files."""
    top = retrieved_files[:k]
    if not relevant_files:
        return MetricValue(1.0 if not top else 0.0, len(top), 0, "no relevant files labeled")
    hits = len(set(top) & relevant_files)
    return MetricValue(hits / len(relevant_files), hits, len(relevant_files))


def range_recall(
    retrieved: list[tuple[str, int, int]], relevant: list[tuple[str, int, int]]
) -> MetricValue:
    """Fraction of labeled ranges overlapped by at least one retrieved range."""
    if not relevant:
        return MetricValue(1.0 if not retrieved else 0.0, len(retrieved), 0, "no relevant ranges")
    hits = sum(
        1 for want in relevant if any(ranges_overlap(got, want) for got in retrieved)
    )
    return MetricValue(hits / len(relevant), hits, len(relevant))


def citation_integrity_score(valid: int, total: int) -> MetricValue:
    """Fraction of citations resolving to supplied evidence."""
    if total == 0:
        return MetricValue(None, 0, 0, "no citations to check")
    return MetricValue(valid / total, valid, total)


def abstention_precision_recall(
    outcomes: list[tuple[bool, bool]],
) -> tuple[MetricValue, MetricValue]:
    """Precision/recall of abstention over (answerable, abstained) outcomes."""
    abstained = [(a, b) for a, b in outcomes if b]
    unanswerable = [(a, b) for a, b in outcomes if not a]
    precision = (
        MetricValue(None, 0, 0, "nothing abstained")
        if not abstained
        else MetricValue(
            sum(1 for a, _ in abstained if not a) / len(abstained),
            sum(1 for a, _ in abstained if not a),
            len(abstained),
        )
    )
    recall = (
        MetricValue(None, 0, 0, "no unanswerable cases")
        if not unanswerable
        else MetricValue(
            sum(1 for _, b in unanswerable if b) / len(unanswerable),
            sum(1 for _, b in unanswerable if b),
            len(unanswerable),
        )
    )
    return precision, recall


def claim_support_score(labels: list[bool]) -> MetricValue:
    """Human-judged fraction of supported material claims.

    An empty label list means "not reviewed", reported as no score: absence
    of review must never read as a zero.
    """
    if not labels:
        return MetricValue(None, 0, 0, "no human labels; see tests/fixtures/README.md rubric")
    supported = sum(1 for label in labels if label)
    return MetricValue(supported / len(labels), supported, len(labels))
