from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from config import load_settings
from errors import ShirabeError
from graph import app
from tools import check_repo_budget, cleanup_repository, clone_repository


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
    args = parser.parse_args()

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
        result = app.invoke(
            {
                "repo_url": repo_url,
                "repo_path": repo_path,
                "question": question,
                "plan": [],
                "evidence": [],
                "analysis": "",
                "answer": "",
                "iteration": 0,
                "max_iterations": settings.max_iterations,
                "needs_more_evidence": False,
            }
        )
        print("\n" + "=" * 80)
        print(result["answer"])
        print("=" * 80)
        return 0
    except ShirabeError as exc:
        print(f"Investigation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if repo_path:
            cleanup_repository(repo_path)


if __name__ == "__main__":
    raise SystemExit(main())