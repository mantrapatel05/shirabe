"""Versioned investigation reports: explicit, inspectable, deletable.

A report carries the question, repository label and snapshot, answer,
structured claims, bounded evidence excerpts, citation-check outcomes, the
limits that bound the run, and run provenance. It never carries secrets,
full repository contents, raw model prompts, or tracing data: callers pass
only the fields below, so there is nothing to strip after the fact.

Saving is always explicit (no automatic writes). Review labels are opt-in
and stored inside the same file, which stays inspectable and deletable with
the helpers here.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence import CitationCheck, EvidenceRecord

REPORT_VERSION = "v1"


def _record_to_dict(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_id": record.evidence_id,
        "path": record.path,
        "start_line": record.start_line,
        "end_line": record.end_line,
        "reason": record.reason,
        "excerpt": record.excerpt,
        "snapshot_id": record.snapshot_id,
    }


def _check_to_dict(check: CitationCheck) -> dict[str, Any]:
    return {
        "evidence_id": check.citation.evidence_id,
        "path": check.citation.path,
        "start_line": check.citation.start_line,
        "end_line": check.citation.end_line,
        "valid": check.valid,
        "reason": check.reason,
    }


def build_investigation_report(
    question: str,
    repo_label: str,
    snapshot_id: str,
    answer: str,
    abstained: bool,
    answer_claims: list[dict[str, Any]],
    records: list[EvidenceRecord],
    checks: list[CitationCheck],
    method: str,
    limits: dict[str, Any],
    model: str | None = None,
    provider: str | None = None,
    dataset_revision: str | None = None,
    elapsed_s: float = 0.0,
) -> dict[str, Any]:
    """Assemble a versioned report from validated run artifacts."""
    return {
        "report_version": REPORT_VERSION,
        "question": question,
        "repository": {"label": repo_label, "snapshot": snapshot_id or "unknown"},
        "answer": answer,
        "abstained": abstained,
        "claims": answer_claims,
        "evidence": [_record_to_dict(record) for record in records],
        "citation_checks": [_check_to_dict(check) for check in checks],
        "limits": limits,
        "run": {
            "method": method,
            "model": model,
            "provider": provider,
            "dataset_revision": dataset_revision,
            "elapsed_s": round(elapsed_s, 3),
            "created_at": datetime.now(UTC).isoformat(),
        },
        "review": None,
    }


def save_report(report: dict[str, Any], path: str) -> str:
    """Write a report to an explicit path. Creates no other files."""
    if not path or not path.strip():
        raise ValueError("A report path is required; reports are never saved implicitly.")
    destination = Path(path)
    if destination.parent != Path("") and str(destination.parent) not in (".", ""):
        os.makedirs(destination.parent, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return str(destination)


def load_report(path: str) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(f"No saved report at: {path}")
    try:
        report = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Saved report is not valid JSON: {path} ({exc})") from None
    if not isinstance(report, dict) or report.get("report_version") != REPORT_VERSION:
        raise ValueError(f"Unsupported report version in: {path}")
    return report


def inspect_report(path: str) -> str:
    """Render a short human-readable summary of a saved report."""
    report = load_report(path)
    checks = report.get("citation_checks", [])
    valid = sum(1 for check in checks if check.get("valid"))
    lines = [
        f"Report {report.get('report_version')} - {path}",
        f"Question: {report.get('question')}",
        f"Repository: {report.get('repository', {}).get('label')} "
        f"(snapshot {report.get('repository', {}).get('snapshot')})",
        f"Abstained: {report.get('abstained')}",
        f"Claims: {len(report.get('claims', []))}, "
        f"evidence ranges: {len(report.get('evidence', []))}, "
        f"citation checks: {valid}/{len(checks)} valid",
        f"Method: {report.get('run', {}).get('method')}",
    ]
    review = report.get("review")
    if review:
        lines.append(
            f"Review: {review.get('supported')}/{review.get('total')} claims supported "
            f"(labeled {review.get('labeled_at')})"
        )
    else:
        lines.append("Review: none (opt-in human labels only)")
    return "\n".join(lines)


def delete_report(path: str) -> None:
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(f"No saved report at: {path}")
    candidate.unlink()


def attach_review(path: str, labels: list[bool]) -> dict[str, Any]:
    """Attach opt-in human claim-support labels to a saved report.

    Labels are one boolean per saved claim, in order. The file stays plain
    JSON: inspectable with inspect_report, removable with delete_report.
    """
    if not isinstance(labels, list) or any(not isinstance(label, bool) for label in labels):
        raise ValueError("Review labels must be a list of booleans, one per saved claim.")
    report = load_report(path)
    claims = report.get("claims", [])
    if len(labels) != len(claims):
        raise ValueError(
            f"Need one label per saved claim: got {len(labels)} labels for {len(claims)} claims."
        )
    supported = sum(1 for label in labels if label)
    report["review"] = {
        "labels": labels,
        "supported": supported,
        "total": len(labels),
        "labeled_at": datetime.now(UTC).isoformat(),
    }
    Path(path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
