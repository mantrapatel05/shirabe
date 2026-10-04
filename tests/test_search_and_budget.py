import pytest

from errors import RepositoryError
from tools import check_repo_budget, iter_text_files, search_repository


def test_ignored_directories_are_skipped(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("function search_repository() {}")
    (tmp_path / "app.py").write_text("def search_repository(): pass")

    found = {str(p.relative_to(tmp_path)) for p in iter_text_files(str(tmp_path))}
    assert found == {"app.py"}


def test_oversized_files_are_skipped(tmp_path):
    small = tmp_path / "small.py"
    small.write_text("x = 1\n")
    big = tmp_path / "big.py"
    big.write_text("x = 1\n" * 1000)

    found = {str(p.relative_to(tmp_path)) for p in iter_text_files(str(tmp_path), max_file_bytes=100)}
    assert found == {"small.py"}


def test_unsupported_extensions_are_skipped(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "notes.md").write_text("hello")

    found = {str(p.relative_to(tmp_path)) for p in iter_text_files(str(tmp_path))}
    assert found == {"notes.md"}


def test_search_returns_empty_for_blank_query(tmp_path):
    (tmp_path / "a.py").write_text("def foo(): pass")
    assert search_repository(str(tmp_path), "   ") == []


def test_search_returns_empty_when_no_match(tmp_path):
    (tmp_path / "a.py").write_text("def foo(): pass")
    assert search_repository(str(tmp_path), "nonexistent_symbol_xyz") == []


def test_search_finds_line_and_reports_range(tmp_path):
    filler = "\n".join(f"line {i}" for i in range(10))
    (tmp_path / "a.py").write_text(filler + "\ndef target_function():\n    pass\n")
    results = search_repository(str(tmp_path), "target_function")
    assert len(results) == 1
    assert "FILE: a.py" in results[0]
    assert "target_function" in results[0]


def test_search_respects_max_results(tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("def shared_symbol(): pass")
    results = search_repository(str(tmp_path), "shared_symbol", max_results=2)
    assert len(results) == 2


def test_repo_budget_passes_within_limits(tmp_path):
    (tmp_path / "a.py").write_text("hello")
    check_repo_budget(str(tmp_path), max_files=10, max_total_bytes=1_000_000)


def test_repo_budget_raises_on_too_many_files(tmp_path):
    for i in range(5):
        (tmp_path / f"file_{i}.py").write_text("x")
    with pytest.raises(RepositoryError):
        check_repo_budget(str(tmp_path), max_files=3, max_total_bytes=1_000_000)


def test_repo_budget_raises_on_too_many_bytes(tmp_path):
    (tmp_path / "big.py").write_text("x" * 10_000)
    with pytest.raises(RepositoryError):
        check_repo_budget(str(tmp_path), max_files=10, max_total_bytes=1_000)


def test_repo_budget_ignores_ignored_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "pack.bin").write_text("x" * 10_000)
    (tmp_path / "a.py").write_text("hello")
    check_repo_budget(str(tmp_path), max_files=5, max_total_bytes=1_000)
