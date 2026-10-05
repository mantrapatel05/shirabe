"""Versioned evaluation cases over miniature fixtures (dataset v1).

Each case pins a fixture directory, an engineering question, planner-like
queries, answerability, and manually checked relevant source ranges. Fixture
mode bypasses the planner on purpose: the queries stand in for planner
output so retrieval is measured deterministically. Planner quality is only
exercised in live mode.
"""

from __future__ import annotations

from dataclasses import dataclass

DATASET_REVISION = "v1"

# Retrieval cutoff for recall@k. Kept small on purpose: fixtures are tiny,
# so a miss at this cutoff is a real lexical gap, not an indexing artifact.
RETRIEVAL_CUTOFF_K = 5


@dataclass(frozen=True)
class RelevantRange:
    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    fixture: str
    question: str
    queries: tuple[str, ...]
    answerable: bool
    relevant: tuple[RelevantRange, ...] = ()


CASES: tuple[EvalCase, ...] = (
    EvalCase(
        case_id="calc-single",
        fixture="calc",
        question="What does total() return for a list of numbers, and how is it computed?",
        queries=("total values", "add result"),
        answerable=True,
        relevant=(
            RelevantRange("calc.py", 5, 7),
            RelevantRange("calc.py", 10, 15),
        ),
    ),
    EvalCase(
        case_id="flow-control",
        fixture="flow",
        question="What happens between handle_order receiving an order and the total being returned?",
        queries=("handle_order", "price_order"),
        answerable=True,
        relevant=(
            RelevantRange("handler.py", 7, 10),
            RelevantRange("service.py", 7, 10),
            RelevantRange("models.py", 12, 16),
        ),
    ),
    EvalCase(
        case_id="flow-data",
        fixture="flow",
        question="Where does the discount rate applied to an order come from?",
        queries=("discount rate", "for_customer"),
        answerable=True,
        relevant=(
            RelevantRange("service.py", 9, 10),
            RelevantRange("models.py", 12, 16),
        ),
    ),
    EvalCase(
        case_id="shop-config",
        fixture="shop",
        question="Where does the fetch timeout come from and what is its default?",
        queries=("DEFAULT_TIMEOUT_SECONDS", "fetch timeout"),
        answerable=True,
        relevant=(
            RelevantRange("config.py", 5, 5),
            RelevantRange("client.py", 7, 9),
        ),
    ),
    EvalCase(
        case_id="guarded-failure",
        fixture="guarded",
        question="Which code paths can raise NegativeError, and what condition selects them?",
        queries=("NegativeError", "raise Negative"),
        answerable=True,
        relevant=(
            RelevantRange("parser.py", 5, 6),
            RelevantRange("parser.py", 12, 13),
        ),
    ),
    EvalCase(
        case_id="auth-unanswerable",
        fixture="auth",
        question="How does retry with backoff work in this service?",
        queries=("retry backoff",),
        answerable=False,
        relevant=(),
    ),
)
