from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from errors import RepositoryError

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next", "dist", "build", "target"}
TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".cc", ".c", ".h",
    ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".sql", ".md", ".txt",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".xml", ".html", ".css", ".sh", ".bash",
}
MAX_FILE_BYTES = 500_000
DEFAULT_CLONE_TIMEOUT_SECONDS = 120
TEMP_DIR_PREFIX = "shirabe_"


def _validate_github_url(repo_url: str) -> None:
    parsed = urlparse(repo_url)

    if parsed.scheme not in {"http", "https"}:
        raise RepositoryError("Repository URL must use http or https.")

    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise RepositoryError("Shirabe currently supports only github.com URLs.")

    if not re.match(r"^/[^/]+/[^/]+/?$", parsed.path):
        raise RepositoryError("Expected a URL of the form https://github.com/owner/repository")


def clone_repository(repo_url: str, timeout_seconds: int = DEFAULT_CLONE_TIMEOUT_SECONDS) -> str:
    """Shallow-clone a public GitHub repository into a fresh temp directory.

    Raises RepositoryError (never a raw subprocess exception) on invalid
    input, timeout, or clone failure. On failure the temp directory is
    removed before the error propagates. On success, the caller is
    responsible for calling cleanup_repository() when done.
    """
    _validate_github_url(repo_url)

    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    destination = os.path.join(temp_dir, "repo")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, destination],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RepositoryError(f"Cloning the repository timed out after {timeout_seconds}s.") from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RepositoryError(
            "git clone failed. Confirm the repository exists, is public, and the URL is correct."
        ) from exc
    except OSError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RepositoryError("Could not run git. Confirm git is installed and on PATH.") from exc
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return destination


def cleanup_repository(repo_path: str) -> None:
    """Remove the temp directory created by clone_repository, if it exists.

    Safe to call more than once, and safe to call with an unrelated path:
    it only removes a directory whose name carries this module's own temp
    prefix, so it can never be pointed at an arbitrary directory.
    """
    if not repo_path:
        return
    root = Path(repo_path).resolve().parent
    if root.name.startswith(TEMP_DIR_PREFIX) and root.exists():
        shutil.rmtree(root, ignore_errors=True)


def check_repo_budget(repo_path: str, max_files: int, max_total_bytes: int) -> None:
    """Raise RepositoryError if the cloned repository exceeds size budgets.

    Counts every non-ignored file (not just supported text files), since the
    goal is to bound total disk/scan work, not just text-search work.
    """
    total_files = 0
    total_bytes = 0
    for path in Path(repo_path).rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts) or not path.is_file():
            continue
        total_files += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue
        if total_files > max_files or total_bytes > max_total_bytes:
            raise RepositoryError(
                f"Repository exceeds configured limits (max {max_files} files / "
                f"{max_total_bytes} bytes). Try a smaller repository, or raise "
                "SHIRABE_MAX_REPO_FILES / SHIRABE_MAX_REPO_TOTAL_BYTES."
            )


def _iter_text_files(repo_path: str, max_file_bytes: int = MAX_FILE_BYTES):
    root = Path(repo_path)

    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue
        yield path


def iter_text_files(repo_path: str, max_file_bytes: int = MAX_FILE_BYTES):
    yield from _iter_text_files(repo_path, max_file_bytes)


def search_repository(
    repo_path: str,
    query: str,
    max_results: int = 8,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> list[str]:
    terms = [x.lower() for x in query.split() if x.strip()]

    if not terms:
        return []

    results = []

    for path in _iter_text_files(repo_path, max_file_bytes):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for index, line in enumerate(lines):
            if all(term in line.lower() for term in terms):
                start = max(0, index - 2)
                end = min(len(lines), index + 3)
                relative = path.relative_to(repo_path)
                snippet = "\n".join(
                    f"{start + offset + 1}: {lines[start + offset]}" for offset in range(end - start)
                )
                results.append(f"FILE: {relative}\nLINES: {start + 1}-{end}\n{snippet}")
                if len(results) >= max_results:
                    return results

    return results


def search_repo(repo_path: str, query: str, max_results: int = 8) -> list[str]:
    return search_repository(repo_path, query, max_results)


def read_file(repo_path: str, relative_path: str, max_chars: int = 8000) -> str:
    root = Path(repo_path).resolve()
    candidate = (root / relative_path).resolve()

    if root not in candidate.parents and candidate != root:
        raise ValueError("Path escapes repository root.")
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate.read_text(encoding="utf-8", errors="ignore")[:max_chars]
