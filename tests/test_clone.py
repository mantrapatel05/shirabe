import subprocess
import tempfile
from pathlib import Path

import pytest

from errors import RepositoryError
from tools import cleanup_repository, clone_repository


def _fake_success(cmd, **kwargs):
    Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
    return subprocess.CompletedProcess(cmd, 0)


def _fake_timeout(cmd, **kwargs):
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1))


def _fake_process_error(cmd, **kwargs):
    raise subprocess.CalledProcessError(
        returncode=128, cmd=cmd, output="", stderr="fatal: repository not found"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/psf/requests",
        "https://github.com/psf/requests/",
        "http://github.com/psf/requests",
        "https://www.github.com/psf/requests",
        "https://github.com/psf/requests.git",
    ],
)
def test_accepted_url_forms(url, monkeypatch):
    monkeypatch.setattr("tools.subprocess.run", _fake_success)
    repo_path = clone_repository(url)
    try:
        assert Path(repo_path).is_dir()
    finally:
        cleanup_repository(repo_path)
    assert not Path(repo_path).exists()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://github.com/psf/requests",
        "https://gitlab.com/psf/requests",
        "https://github.com/psf",
        "https://github.com/psf/requests/tree/main",
        "https://github.com/",
        "not a url",
        "",
    ],
)
def test_rejected_url_forms(url, monkeypatch):
    monkeypatch.setattr("tools.subprocess.run", _fake_success)
    with pytest.raises(RepositoryError):
        clone_repository(url)


def test_rejected_url_never_creates_temp_dir(monkeypatch):
    before = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    monkeypatch.setattr("tools.subprocess.run", _fake_success)
    with pytest.raises(RepositoryError):
        clone_repository("https://gitlab.com/psf/requests")
    after = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    assert after == before


def test_clone_timeout_cleans_up_and_raises(monkeypatch):
    monkeypatch.setattr("tools.subprocess.run", _fake_timeout)
    before = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    with pytest.raises(RepositoryError):
        clone_repository("https://github.com/psf/requests", timeout_seconds=1)
    after = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    assert after == before


def test_clone_process_failure_cleans_up_and_raises(monkeypatch):
    monkeypatch.setattr("tools.subprocess.run", _fake_process_error)
    before = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    with pytest.raises(RepositoryError) as excinfo:
        clone_repository("https://github.com/psf/requests")
    after = set(Path(tempfile.gettempdir()).glob("shirabe_*"))
    assert after == before
    # The raw stderr (which could theoretically contain sensitive detail from
    # a self-hosted remote) must never reach the user-facing message.
    assert "fatal:" not in str(excinfo.value)


def test_cleanup_ignores_unrelated_directory(tmp_path):
    unrelated = tmp_path / "not_a_shirabe_dir" / "repo"
    unrelated.mkdir(parents=True)
    cleanup_repository(str(unrelated))
    assert unrelated.exists()


def test_cleanup_is_idempotent(monkeypatch):
    monkeypatch.setattr("tools.subprocess.run", _fake_success)
    repo_path = clone_repository("https://github.com/psf/requests")
    cleanup_repository(repo_path)
    cleanup_repository(repo_path)  # must not raise on the second call
