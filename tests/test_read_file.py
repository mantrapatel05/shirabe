import pytest

from tools import read_file


def test_read_file_returns_content_within_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("hello world")
    assert read_file(str(repo), "a.txt") == "hello world"


def test_read_file_truncates_to_max_chars(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("x" * 100)
    assert len(read_file(str(repo), "a.txt", max_chars=10)) == 10


def test_read_file_rejects_parent_traversal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    with pytest.raises(ValueError):
        read_file(str(repo), "../secret.txt")


def test_read_file_rejects_absolute_escape(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    with pytest.raises(ValueError):
        read_file(str(repo), str(outside))


def test_read_file_rejects_symlink_escape(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    link = repo / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")
    with pytest.raises(ValueError):
        read_file(str(repo), "link.txt")


def test_read_file_missing_file_raises(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(FileNotFoundError):
        read_file(str(repo), "missing.txt")
