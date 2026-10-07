"""Reproducible code-investigation benchmark.

Fixture mode (default, deterministic, no credentials) runs every labeled
case with real retrieval against the miniature fixtures and mocked model
outputs: planner queries are pinned per case, answer claims are canned from
the records actually collected, and one adversarial probe checks that bad
citations are rejected. Live mode is opt-in, needs GROQ_API_KEY, and records
full provenance. Fixture results are regression signals, never general
accuracy claims.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import nodes as nodes_module
from config import DEFAULT_MAX_EVIDENCE_CHARS, load_settings, tracing_disabled
from errors import ShirabeError
from eval_cases import CASES, DATASET_REVISION, RETRIEVAL_CUTOFF_K, EvalCase
from eval_metrics import (
    MetricValue,
    abstention_precision_recall,
    citation_integrity_score,
    claim_support_score,
    file_recall_at_k,
    range_recall,
)
from evidence import AnswerClaim, Citation, validate_citations
from nodes import explain_node, investigate_node
from state import AgentState
from tools import search_hits

LIMITATIONS = [
    "Fixture mode bypasses the planner: case queries stand in for planner output.",
    "Miniature fixtures exercise the evidence contract, not broad repository accuracy.",
    "Claim support needs human labels and is always unlabeled in deterministic runs.",
    "Model/provider behavior is only measured in live mode with recorded provenance.",
]


def fixture_root() -> Path:
    return Path(__file__).parent / "tests" / "fixtures"


def retrieve_case(case: EvalCase) -> tuple[list[str], list[tuple[str, int, int]]]:
    """Run pinned queries; return sorted distinct files and sorted ranges.

    Sorting by (path, start) keeps the cutoff deterministic across machines
    and filesystems instead of depending on directory iteration order.
    """
    found: set[tuple[str, int, int]] = set()
    fixture_dir = str(fixture_root() / case.fixture)
    for query in case.queries:
        for hit in search_hits(fixture_dir, query):
            found.add((hit.path, hit.start_line, hit.end_line))
    ordered = sorted(found)
    files = sorted({path for path, _, _ in ordered})
    return files, ordered


def check_labels(case: EvalCase) -> list[str]:
    """Confirm every labeled range resolves to real fixture lines."""
    problems = []
    for want in case.relevant:
        candidate = fixture_root() / case.fixture / want.path
        if not candidate.is_file():
            problems.append(f"{case.case_id}: labeled file missing: {want.path}")
            continue
        total = len(candidate.read_text(encoding="utf-8", errors="ignore").splitlines())
        if want.start_line < 1 or want.end_line < want.start_line or want.end_line > total:
            problems.append(
                f"{case.case_id}: labeled range out of bounds: "
                f"{want.path}:{want.start_line}-{want.end_line} (file has {total} lines)"
            )
    return problems


def base_state(case: EvalCase) -> AgentState:
    return {
        "repo_url": f"fixture:{case.fixture}",
        "repo_path": str(fixture_root() / case.fixture),
        "question": case.question,
        "plan": list(case.queries),
        "evidence": [],
        "evidence_records": [],
        "max_evidence_chars": DEFAULT_MAX_EVIDENCE_CHARS,
        "analysis": "",
        "answer": "",
        "answer_claims": [],
        "citation_report": [],
        "abstained": False,
        "iteration": 0,
        "max_iterations": 3,
        "needs_more_evidence": False,
    }


def canned_claims_payload(records: list) -> str:
    claims = [
        {"text": f"Observed behavior shown in {record.evidence_id}.", "evidence": [record.evidence_id]}
        for record in records
    ]
    return json.dumps({"claims": claims})


def explain_with_mocked_claims(state: AgentState, records: list) -> dict:
    """Run the real explainer with canned claims built from collected records.

    Shared by the fixture benchmark and the no-key demo: no model call, but
    the production parse/validate/render path is exercised.
    """
    payload = canned_claims_payload(records)
    original = nodes_module._invoke

    def canned_invoke(prompt: str) -> str:
        return payload

    nodes_module._invoke = canned_invoke
    try:
        return explain_node(state)
    finally:
        nodes_module._invoke = original


def adversarial_probe(records: list) -> list[AnswerClaim]:
    first = records[0].evidence_id if records else "E1"
    return [
        AnswerClaim(text="Unknown reference.", citations=(Citation(evidence_id="E9999"),)),
        AnswerClaim(
            text="Out-of-range reference.",
            citations=(Citation(evidence_id=first, start_line=1, end_line=10**9),),
        ),
    ]


def run_fixture_evaluation() -> dict:
    """Deterministic benchmark entry point. Tracing is forced off here."""
    with tracing_disabled():
        return _run_fixture_evaluation()


def _run_fixture_evaluation() -> dict:
    failures: list[str] = []
    case_rows: list[dict] = []
    outcomes: list[tuple[bool, bool]] = []
    file_num = file_den = range_num = range_den = 0
    cite_valid = cite_total = 0
    total_ranges = 0

    for case in CASES:
        started = time.perf_counter()
        failures.extend(check_labels(case))

        files, ranges = retrieve_case(case)
        relevant_files = {want.path for want in case.relevant}
        relevant_ranges = [(want.path, want.start_line, want.end_line) for want in case.relevant]
        file_metric = file_recall_at_k(files, relevant_files, RETRIEVAL_CUTOFF_K)
        range_metric = range_recall(ranges, relevant_ranges)
        file_num += file_metric.numerator
        file_den += file_metric.denominator
        range_num += range_metric.numerator
        range_den += range_metric.denominator

        state = base_state(case)
        investigated = investigate_node(state)
        records = investigated["evidence_records"]
        total_ranges += len(records)

        if not case.answerable:
            if ranges:
                failures.append(f"{case.case_id}: retrieval returned ranges for an unanswerable case")
            empty = base_state(case)
            result = explain_node(empty)
            if not result["abstained"]:
                failures.append(f"{case.case_id}: unanswerable case was answered")
            outcomes.append((False, result["abstained"]))
            integrity: MetricValue = citation_integrity_score(0, 0)
        else:
            if not records:
                failures.append(f"{case.case_id}: no evidence collected for an answerable case")
                outcomes.append((True, True))
                integrity = citation_integrity_score(0, 0)
            else:
                result = explain_with_mocked_claims({**state, **investigated}, records)
                outcomes.append((True, result["abstained"]))
                if result["abstained"]:
                    failures.append(f"{case.case_id}: answerable case abstained")
                report = result["citation_report"]
                valid = sum(1 for check in report if check.valid)
                cite_valid += valid
                cite_total += len(report)
                integrity = citation_integrity_score(valid, len(report))

                rejected = validate_citations(records, adversarial_probe(records))
                if any(check.valid for check in rejected):
                    failures.append(f"{case.case_id}: adversarial citations were accepted")

        elapsed = time.perf_counter() - started
        case_rows.append(
            {
                "case_id": case.case_id,
                "answerable": case.answerable,
                "abstained": outcomes[-1][1],
                "file_recall_at_k": file_metric.value,
                "range_recall": range_metric.value,
                "citation_integrity": integrity.value,
                "ranges_read": len(records),
                "elapsed_s": round(elapsed, 3),
            }
        )

    precision, recall = abstention_precision_recall(outcomes)
    support = claim_support_score([])
    missed = sorted(
        {
            row["case_id"]
            for row, case in zip(case_rows, CASES)
            if case.answerable
            and (row["file_recall_at_k"] != 1.0 or row["range_recall"] != 1.0)
        }
    )
    report = {
        "dataset_revision": DATASET_REVISION,
        "method": "fixture",
        "model": None,
        "provider": None,
        "case_count": len(CASES),
        "retrieval_cutoff_k": RETRIEVAL_CUTOFF_K,
        "cases": case_rows,
        "metrics": {
            "retrieval_file_recall_at_k": _dump(_ratio(file_num, file_den), file_num, file_den),
            "retrieval_range_recall": _dump(_ratio(range_num, range_den), range_num, range_den),
            "citation_integrity": _dump(
                _ratio(cite_valid, cite_total), cite_valid, cite_total
            ),
            "abstention_precision": _dump(precision.value, precision.numerator, precision.denominator),
            "abstention_recall": _dump(recall.value, recall.numerator, recall.denominator),
            "claim_support": _dump(support.value, support.numerator, support.denominator),
            "efficiency": {"ranges_read": total_ranges},
        },
        "retrieval_gap_cases": missed,
        "limitations": LIMITATIONS,
        "failures": failures,
    }
    return report


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _dump(value: float | None, numerator: int, denominator: int) -> dict:
    return {"value": value, "numerator": numerator, "denominator": denominator}


def run_live_evaluation() -> dict:
    settings = load_settings()
    case_rows: list[dict] = []
    outcomes: list[tuple[bool, bool]] = []
    file_num = file_den = range_num = range_den = 0
    cite_valid = cite_total = 0
    total_ranges = 0

    for case in CASES:
        started = time.perf_counter()
        files, ranges = retrieve_case(case)
        relevant_files = {want.path for want in case.relevant}
        file_metric = file_recall_at_k(files, relevant_files, RETRIEVAL_CUTOFF_K)
        range_metric = range_recall(
            ranges, [(w.path, w.start_line, w.end_line) for w in case.relevant]
        )
        file_num += file_metric.numerator
        file_den += file_metric.denominator
        range_num += range_metric.numerator
        range_den += range_metric.denominator

        investigated = investigate_node(base_state(case))
        records = investigated["evidence_records"]
        total_ranges += len(records)
        result = explain_node({**base_state(case), **investigated})
        outcomes.append((case.answerable, result["abstained"]))
        report = result["citation_report"]
        valid = sum(1 for check in report if check.valid)
        cite_valid += valid
        cite_total += len(report)

        case_rows.append(
            {
                "case_id": case.case_id,
                "answerable": case.answerable,
                "abstained": result["abstained"],
                "file_recall_at_k": file_metric.value,
                "range_recall": range_metric.value,
                "citation_integrity": (valid / len(report)) if report else None,
                "ranges_read": len(records),
                "elapsed_s": round(time.perf_counter() - started, 3),
            }
        )

    precision, recall = abstention_precision_recall(outcomes)
    support = claim_support_score([])
    return {
        "dataset_revision": DATASET_REVISION,
        "method": "live",
        "model": settings.openrouter_model,
        "provider": "openrouter",
        "run_at": datetime.now(UTC).isoformat(),
        "settings": {
            "max_iterations": settings.max_iterations,
            "max_evidence_chars": settings.max_evidence_chars,
        },
        "case_count": len(CASES),
        "retrieval_cutoff_k": RETRIEVAL_CUTOFF_K,
        "cases": case_rows,
        "metrics": {
            "retrieval_file_recall_at_k": _dump(_ratio(file_num, file_den), file_num, file_den),
            "retrieval_range_recall": _dump(_ratio(range_num, range_den), range_num, range_den),
            "citation_integrity": _dump(
                _ratio(cite_valid, cite_total), cite_valid, cite_total
            ),
            "abstention_precision": _dump(precision.value, precision.numerator, precision.denominator),
            "abstention_recall": _dump(recall.value, recall.numerator, recall.denominator),
            "claim_support": _dump(support.value, support.numerator, support.denominator),
            "efficiency": {"ranges_read": total_ranges},
        },
        "limitations": LIMITATIONS
        + ["Live-model answers need human claim-support labels before any support claim is made."],
        "failures": [],
    }


def format_value(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def print_report(report: dict) -> None:
    print(f"Shirabe benchmark (dataset {report['dataset_revision']}, method {report['method']})")
    print(f"Cases: {report['case_count']}, retrieval cutoff k={report['retrieval_cutoff_k']}")
    if report.get("model"):
        print(f"Model: {report['model']} via {report['provider']} at {report.get('run_at')}")
    print()
    header = (
        f"{'case':<20}{'answerable':<12}{'abstained':<11}{'file-rec':<10}"
        f"{'range-rec':<11}{'cite-int':<10}{'ranges'}"
    )
    print(header)
    print("-" * len(header))
    for row in report["cases"]:
        print(
            f"{row['case_id']:<20}{str(row['answerable']):<12}{str(row['abstained']):<11}"
            f"{format_value(row['file_recall_at_k']):<10}{format_value(row['range_recall']):<11}"
            f"{format_value(row['citation_integrity']):<10}{row['ranges_read']}"
        )
    print()
    for name, metric in report["metrics"].items():
        if isinstance(metric, dict) and "value" in metric:
            print(f"{name}: {format_value(metric['value'])} ({metric['numerator']}/{metric['denominator']})")
        else:
            print(f"{name}: {metric}")
    if report.get("retrieval_gap_cases"):
        print(f"\nRetrieval gap cases (recall < 1.0): {', '.join(report['retrieval_gap_cases'])}")
    print("\nLimitations:")
    for limitation in report["limitations"]:
        print(f"  - {limitation}")
    if report.get("failures"):
        print("\nFailures:")
        for failure in report["failures"]:
            print(f"  - {failure}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shirabe investigation benchmark")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    args = parser.parse_args()

    try:
        if args.mode == "live":
            report = run_live_evaluation()
        else:
            report = run_fixture_evaluation()
    except ShirabeError as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    if report.get("failures"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
