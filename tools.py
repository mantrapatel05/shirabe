from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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


def _validate_github_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)

    if parsed.scheme not in {"http", "https"}:
        raise RepositoryError("Repository URL must use http or https.")

    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise RepositoryError("Shirabe currently supports only github.com URLs.")

    match = re.match(r"^/([^/]+)/([^/]+)", parsed.path)
    if not match:
        raise RepositoryError("Expected a URL of the form https://github.com/owner/repository")

    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"https://github.com/{owner}/{repo}"


def clone_repository(repo_url: str, timeout_seconds: int = DEFAULT_CLONE_TIMEOUT_SECONDS) -> str:
    """Shallow-clone a public GitHub repository into a fresh temp directory.

    Raises RepositoryError (never a raw subprocess exception) on invalid
    input, timeout, or clone failure. On failure the temp directory is
    removed before the error propagates. On success, the caller is
    responsible for calling cleanup_repository() when done.
    """
    repo_url = _validate_github_url(repo_url)

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

    candidates = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIRS for part in path.parts)
    )
    for path in candidates:
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
    return [
        format_search_hit(hit) for hit in search_hits(repo_path, query, max_results, max_file_bytes)
    ]


@dataclass(frozen=True)
class SearchHit:
    """One structured search match: POSIX relative path, 1-indexed range, raw lines."""

    path: str
    start_line: int
    end_line: int
    lines: tuple[str, ...]


def format_search_hit(hit: SearchHit) -> str:
    snippet = "\n".join(
        f"{hit.start_line + offset}: {line}" for offset, line in enumerate(hit.lines)
    )
    return f"FILE: {hit.path}\nLINES: {hit.start_line}-{hit.end_line}\n{snippet}"


def search_hits(
    repo_path: str,
    query: str,
    max_results: int = 8,
    max_file_bytes: int = MAX_FILE_BYTES,
    lines_cache: dict[str, list[str]] | None = None,
) -> list[SearchHit]:
    """Keyword search returning structured hits in deterministic file order.

    Pass lines_cache from load_text_lines to scan the checkout once per
    investigation pass instead of re-reading every file per query; results
    are identical either way.
    """
    terms = [x.lower() for x in query.split() if x.strip()]

    if not terms:
        return []

    if lines_cache is not None:
        sources: list[tuple[str, list[str]]] = sorted(lines_cache.items())
    else:
        sources = list(_walk_text_lines(repo_path, max_file_bytes))

    hits: list[SearchHit] = []
    for relative, lines in sources:
        for index, line in enumerate(lines):
            if all(term in line.lower() for term in terms):
                start = max(0, index - 2)
                end = min(len(lines), index + 3)
                hits.append(
                    SearchHit(
                        path=relative,
                        start_line=start + 1,
                        end_line=end,
                        lines=tuple(lines[start:end]),
                    )
                )
                if len(hits) >= max_results:
                    return hits

    return hits


def _walk_text_lines(repo_path: str, max_file_bytes: int):
    root = Path(repo_path)
    for path in _iter_text_files(repo_path, max_file_bytes):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        yield path.relative_to(root).as_posix(), lines


def load_text_lines(
    repo_path: str, max_file_bytes: int = MAX_FILE_BYTES
) -> dict[str, list[str]]:
    """Read every searchable file once: POSIX relative path to its lines."""
    return dict(_walk_text_lines(repo_path, max_file_bytes))


def search_repo(repo_path: str, query: str, max_results: int = 8) -> list[str]:
    return search_repository(repo_path, query, max_results)


def _resolve_within_root(repo_path: str, relative_path: str) -> Path:
    root = Path(repo_path).resolve()
    candidate = (root / relative_path).resolve()

    if root not in candidate.parents and candidate != root:
        raise ValueError("Path escapes repository root.")
    return candidate


def read_file(repo_path: str, relative_path: str, max_chars: int = 8000) -> str:
    candidate = _resolve_within_root(repo_path, relative_path)

    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def read_range(
    repo_path: str,
    relative_path: str,
    start_line: int,
    end_line: int,
    max_chars: int = 8000,
) -> list[str]:
    """Read whole lines [start_line, end_line] (1-indexed, inclusive).

    The path must stay inside the repository root, exactly like read_file.
    Ranges are clamped to the end of the file; out-of-range requests raise
    ValueError instead of silently returning unrelated lines.
    """
    if (
        not isinstance(start_line, int)
        or isinstance(start_line, bool)
        or not isinstance(end_line, int)
        or isinstance(end_line, bool)
        or start_line < 1
        or end_line < start_line
    ):
        raise ValueError(f"Invalid line range: {start_line}-{end_line}.")

    candidate = _resolve_within_root(repo_path, relative_path)
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)

    lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
    if start_line > len(lines):
        raise ValueError(f"Start line {start_line} is beyond the end of {relative_path}.")

    selected = lines[start_line - 1 : min(end_line, len(lines))]
    kept: list[str] = []
    used = 0
    for line in selected:
        if kept and used + len(line) + 1 > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    return kept


def get_repo_revision(repo_path: str) -> str:
    """Return the checkout's commit SHA, or "" when it cannot be determined.

    Never raises: a missing SHA degrades to "unknown snapshot", never to a
    failed investigation.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    sha = completed.stdout.strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else ""
