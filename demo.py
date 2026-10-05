"""No-key fixture demo: a multi-file evidence trail plus an abstention case.

Runs entirely on the miniature fixtures with canned model claims, so it
needs no GROQ_API_KEY, no network, and no tracing credentials. It exercises
the production investigate/explain/validate path and optionally saves a
versioned report (explicit path only).
"""

from __future__ import annotations

import argparse
import sys
import time

from eval_cases import CASES, DATASET_REVISION, RETRIEVAL_CUTOFF_K, EvalCase
from evaluate import base_state, explain_with_mocked_claims
from evidence import MAX_EVIDENCE_RECORDS, MAX_EXCERPT_CHARS, format_evidence, summarize_checks
from nodes import explain_node, investigate_node
from report import build_investigation_report, save_report

DEMO_CASE_ID = "flow-control"
ABSTAIN_CASE_ID = "auth-unanswerable"


def find_case(case_id: str) -> EvalCase:
    for case in CASES:
        if case.case_id == case_id:
            return case
    raise ValueError(f"Unknown demo case: {case_id}")


def run_demo(save_path: str | None) -> int:
    print("Shirabe demo (no model key required)")
    print("=" * 80)

    case = find_case(DEMO_CASE_ID)
    print(f"\nCase 1 - multi-file investigation [{case.fixture}]")
    print(f"Question: {case.question}")
    print(f"Planned queries: {', '.join(case.queries)}")

    started = time.perf_counter()
    investigated = investigate_node(base_state(case))
    records = investigated["evidence_records"]
    result = explain_with_mocked_claims({**base_state(case), **investigated}, records)
    elapsed = time.perf_counter() - started

    snapshot = records[0].snapshot_id if records else ""
    print(f"\nEvidence trail ({len(records)} ranges, snapshot {snapshot or 'unknown'}):")
    for record in records:
        print(f"\n{format_evidence(record)}")
    print(f"\nAnswer:\n{result['answer']}")
    print("\nCitation integrity:")
    for line in summarize_checks(result["citation_report"]):
        print(f"  {line}")
    print(
        "\nLimitation: lexical retrieval misses code reachable only through "
        "imports (models.py here). The benchmark records this gap; run "
        "`python evaluate.py --mode fixture` to reproduce it."
    )

    if save_path:
        report = build_investigation_report(
            question=case.question,
            repo_label=f"fixture:{case.fixture}",
            snapshot_id=snapshot,
            answer=result["answer"],
            abstained=result["abstained"],
            answer_claims=result.get("answer_claims", []),
            records=records,
            checks=result["citation_report"],
            method="demo",
            limits={
                "max_evidence_records": MAX_EVIDENCE_RECORDS,
                "max_excerpt_chars": MAX_EXCERPT_CHARS,
                "retrieval_cutoff_k": RETRIEVAL_CUTOFF_K,
            },
            dataset_revision=DATASET_REVISION,
            elapsed_s=elapsed,
        )
        print(f"\nSaved investigation report: {save_report(report, save_path)}")

    abstain_case = find_case(ABSTAIN_CASE_ID)
    print("\n" + "=" * 80)
    print(f"\nCase 2 - abstention [{abstain_case.fixture}]")
    print(f"Question: {abstain_case.question}")
    empty = investigate_node(base_state(abstain_case))
    abstained = explain_node({**base_state(abstain_case), **empty})
    print(f"\nEvidence ranges: {len(empty['evidence_records'])}")
    print(f"\n{abstained['answer']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shirabe no-key fixture demo")
    parser.add_argument("--save-report", default=None, metavar="PATH")
    args = parser.parse_args(argv)
    try:
        return run_demo(args.save_report)
    except (ValueError, OSError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
