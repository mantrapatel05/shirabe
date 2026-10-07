import main as main_module
from errors import RepositoryError


def test_main_fails_cleanly_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/psf/requests", "a question"])

    exit_code = main_module.main()

    assert exit_code == 1
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_main_requires_repo_url_and_question(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "", ""])

    class MockQuestionaryText:
        def __init__(self, *a, **k): pass
        def ask(self): return ""

    monkeypatch.setattr(main_module.questionary, "text", MockQuestionaryText)

    exit_code = main_module.main()

    assert exit_code == 1
    output = capsys.readouterr()
    assert "required" in output.out.lower() or "required" in output.err.lower()


def test_main_surfaces_clone_failure_without_traceback(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/psf/requests", "a question"])

    def _raise_repository_error(url, timeout_seconds=120):
        raise RepositoryError("git clone failed. Confirm the repository exists and is public.")

    monkeypatch.setattr(main_module, "clone_repository", _raise_repository_error)

    exit_code = main_module.main()

    assert exit_code == 1
    assert "Investigation failed" in capsys.readouterr().err


def test_main_cleans_up_temp_repo_after_success(monkeypatch, tmp_path):
    fake_root = tmp_path / "shirabe_fake123"
    fake_repo = fake_root / "repo"
    fake_repo.mkdir(parents=True)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/psf/requests", "a question"])
    monkeypatch.setattr(main_module, "clone_repository", lambda url, timeout_seconds=120: str(fake_repo))
    monkeypatch.setattr(main_module, "check_repo_budget", lambda *a, **k: None)
    monkeypatch.setattr(main_module.app, "invoke", lambda state: {"answer": "done"})

    exit_code = main_module.main()

    assert exit_code == 0
    assert not fake_root.exists()


def test_main_cleans_up_temp_repo_after_budget_failure(monkeypatch, tmp_path):
    fake_root = tmp_path / "shirabe_fake456"
    fake_repo = fake_root / "repo"
    fake_repo.mkdir(parents=True)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/psf/requests", "a question"])
    monkeypatch.setattr(main_module, "clone_repository", lambda url, timeout_seconds=120: str(fake_repo))

    def _raise_budget_error(*a, **k):
        raise RepositoryError("Repository exceeds configured limits")

    monkeypatch.setattr(main_module, "check_repo_budget", _raise_budget_error)

    exit_code = main_module.main()

    assert exit_code == 1
    assert not fake_root.exists()
