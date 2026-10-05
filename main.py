from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv

from config import load_settings
from errors import ShirabeError
from evidence import summarize_checks
from graph import app
from report import attach_review, build_investigation_report, delete_report, inspect_report, save_report
from tools import check_repo_budget, cleanup_repository, clone_repository


def _report_command(action: str, path: str | None, labels: str | None) -> int:
    if not path:
        print("A report path is required.", file=sys.stderr)
        return 1
    try:
        if action == "inspect":
            print(inspect_report(path))
        elif action == "delete":
            delete_report(path)
            print(f"Deleted saved report: {path}")
        else:
            parsed = parse_labels(labels)
            attach_review(path, parsed)
            print(f"Attached {len(parsed)} review labels to: {path}")
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Report error: {exc}", file=sys.stderr)
        return 1
    return 0


def parse_labels(raw: str | None) -> list[bool]:
    if not raw:
        raise ValueError("review needs --labels like '1,0,1' (one per saved claim).")
    labels = []
    for item in raw.split(","):
        token = item.strip().lower()
        if token in {"1", "true", "yes"}:
            labels.append(True)
        elif token in {"0", "false", "no"}:
            labels.append(False)
        else:
            raise ValueError(f"invalid label {item!r}: use 1/0 per saved claim.")
    return labels


def save_investigation_report(
    path: str, question: str, repo_url: str, records: list, result: dict, settings, started: float
) -> int:
    snapshot = records[0].snapshot_id if records else ""
    try:
        report = build_investigation_report(
            question=question,
            repo_label=repo_url,
            snapshot_id=snapshot,
            answer=result.get("answer", ""),
            abstained=result.get("abstained", False),
            answer_claims=result.get("answer_claims", []),
            records=records,
            checks=result.get("citation_report", []),
            method="live",
            limits={
                "max_iterations": settings.max_iterations,
                "clone_timeout_seconds": settings.clone_timeout_seconds,
                "max_repo_files": settings.max_repo_files,
                "max_repo_total_bytes": settings.max_repo_total_bytes,
                "max_file_bytes": settings.max_file_bytes,
                "max_evidence_chars": settings.max_evidence_chars,
            },
            model=settings.groq_model,
            provider="groq",
            elapsed_s=time.perf_counter() - started,
        )
        saved = save_report(report, path)
    except (OSError, ValueError) as exc:
        print(f"Could not save report: {exc}", file=sys.stderr)
        return 1
    print(f"Saved investigation report: {saved}")
    return 0


def main() -> int:
    # Prevent UnicodeEncodeError on Windows consoles (cp1252) when printing
    # LLM output that may contain arbitrary Unicode characters.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()

    parser = argparse.ArgumentParser(description="Shirabe autonomous codebase investigation agent")
    parser.add_argument("repo_url", nargs="?")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--save-report", default=None, metavar="PATH")
    parser.add_argument("--inspect-report", default=None, metavar="PATH")
    parser.add_argument("--delete-report", default=None, metavar="PATH")
    parser.add_argument("--attach-review", default=None, metavar="PATH")
    parser.add_argument("--labels", default=None, metavar="1,0,1")
    args = parser.parse_args()

    if args.inspect_report:
        return _report_command("inspect", args.inspect_report, None)
    if args.delete_report:
        return _report_command("delete", args.delete_report, None)
    if args.attach_review:
        return _report_command("review", args.attach_review, args.labels)

    try:
        settings = load_settings()
    except ShirabeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    repo_url = args.repo_url or input("GitHub repository URL: ").strip()
    question = args.question or input("Engineering question: ").strip()
    if not repo_url or not question:
        print("A repository URL and a question are both required.", file=sys.stderr)
        return 1

    repo_path: str | None = None
    try:
        print("\n[1/2] Loading repository...")
        repo_path = clone_repository(repo_url, timeout_seconds=settings.clone_timeout_seconds)
        check_repo_budget(repo_path, settings.max_repo_files, settings.max_repo_total_bytes)

        print("[2/2] Running investigation...\n")
        started = time.perf_counter()
        result = app.invoke(
            {
                "repo_url": repo_url,
                "repo_path": repo_path,
                "question": question,
                "plan": [],
                "evidence": [],
                "evidence_records": [],
                "analysis": "",
                "answer": "",
                "answer_claims": [],
                "citation_report": [],
                "abstained": False,
                "iteration": 0,
                "max_iterations": settings.max_iterations,
                "needs_more_evidence": False,
            }
        )
        print("\n" + "=" * 80)
        print(result["answer"])
        print("=" * 80)
        records = result.get("evidence_records", [])
        if records:
            snapshot = records[0].snapshot_id or "unknown"
            print(f"\nEvidence: {len(records)} ranges (snapshot {snapshot})")
        checks = result.get("citation_report", [])
        if checks:
            print("Citation integrity:")
            for line in summarize_checks(checks):
                print(f"  {line}")
        if result.get("abstained"):
            print("Shirabe abstained: the checkout did not contain enough evidence.")
        if args.save_report:
            return save_investigation_report(
                args.save_report,
                question,
                repo_url,
                records,
                result,
                settings,
                started,
            )
        return 0
    except ShirabeError as exc:
        print(f"Investigation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if repo_path:
            cleanup_repository(repo_path)


if __name__ == "__main__":
    raise SystemExit(main())