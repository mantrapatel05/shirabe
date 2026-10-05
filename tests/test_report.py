import json

import pytest

import demo as demo_module
import main as main_module
from evidence import Citation, CitationCheck, EvidenceRecord
from report import (
    REPORT_VERSION,
    attach_review,
    build_investigation_report,
    delete_report,
    inspect_report,
    load_report,
    save_report,
)


def _record():
    return EvidenceRecord(
        evidence_id="E1",
        path="a.py",
        start_line=1,
        end_line=2,
        reason="query: test",
        excerpt="1: x = 1\n2: y = 2",
        snapshot_id="s" * 40,
    )


def _report(**overrides):
    record = _record()
    check = CitationCheck(
        Citation(evidence_id="E1", path="a.py", start_line=1, end_line=2), True, "ok"
    )
    report = build_investigation_report(
        question="What does this do?",
        repo_label="fixture:test",
        snapshot_id="s" * 40,
        answer="- It works. [E1 (a.py:1-2)]",
        abstained=False,
        answer_claims=[
            {
                "text": "It works.",
                "citations": [{"evidence_id": "E1", "path": "a.py", "start_line": 1, "end_line": 2}],
            }
        ],
        records=[record],
        checks=[check],
        method="demo",
        limits={"max_evidence_records": 40},
    )
    report.update(overrides)
    return report


def test_report_schema_has_fixed_keys():
    assert set(_report()) == {
        "report_version",
        "question",
        "repository",
        "answer",
        "abstained",
        "claims",
        "evidence",
        "citation_checks",
        "limits",
        "run",
        "review",
    }
    assert _report()["report_version"] == REPORT_VERSION == "v1"


def test_report_contains_no_secrets_or_traces(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-secret-groq-123")
    monkeypatch.setenv("LANGSMITH_API_KEY", "sk-secret-langsmith-456")
    dumped = json.dumps(_report())
    assert "sk-secret-groq-123" not in dumped
    assert "sk-secret-langsmith-456" not in dumped
    assert "prompt" not in _report()
    assert "trace" not in _report()


def test_report_excerpts_stay_bounded():
    long_record = EvidenceRecord(
        evidence_id="E1",
        path="a.py",
        start_line=1,
        end_line=1,
        reason="query: test",
        excerpt="x" * 5000,
    )
    report = build_investigation_report(
        question="q",
        repo_label="r",
        snapshot_id="",
        answer="a",
        abstained=False,
        answer_claims=[],
        records=[long_record],
        checks=[],
        method="demo",
        limits={},
    )
    assert len(report["evidence"][0]["excerpt"]) <= 2000


def test_save_load_round_trip(tmp_path):
    path = str(tmp_path / "report.json")
    assert save_report(_report(), path) == path
    loaded = load_report(path)
    saved = _report()
    assert {k: v for k, v in loaded.items() if k != "run"} == {
        k: v for k, v in saved.items() if k != "run"
    }
    assert loaded["run"]["method"] == "demo"


def test_save_report_needs_explicit_path():
    with pytest.raises(ValueError):
        save_report(_report(), "  ")


def test_load_rejects_missing_bad_and_versioned(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_report(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError):
        load_report(str(bad))
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"report_version": "v0"}))
    with pytest.raises(ValueError):
        load_report(str(old))


def test_inspect_and_delete(tmp_path, capsys):
    path = str(tmp_path / "report.json")
    save_report(_report(), path)
    summary = inspect_report(path)
    assert "What does this do?" in summary
    assert "1/1 valid" in summary
    assert "Review: none" in summary
    delete_report(path)
    assert not (tmp_path / "report.json").exists()
    with pytest.raises(FileNotFoundError):
        delete_report(path)


def test_attach_review_validates_labels(tmp_path):
    path = str(tmp_path / "report.json")
    save_report(_report(), path)
    updated = attach_review(path, [True])
    assert updated["review"]["supported"] == 1
    assert updated["review"]["total"] == 1
    assert "1/1 valid" in inspect_report(path)
    assert "1/1 claims supported" in inspect_report(path)
    with pytest.raises(ValueError):
        attach_review(path, [True, False])
    with pytest.raises(ValueError):
        attach_review(path, ["yes"])


def test_attach_review_empty_claims(tmp_path):
    report = _report()
    report["claims"] = []
    report["abstained"] = True
    path = str(tmp_path / "report.json")
    save_report(report, path)
    assert attach_review(path, [])["review"]["total"] == 0
    with pytest.raises(ValueError):
        attach_review(path, [True])


def test_parse_labels():
    assert main_module.parse_labels("1,0,TRUE,no") == [True, False, True, False]
    with pytest.raises(ValueError):
        main_module.parse_labels("")
    with pytest.raises(ValueError):
        main_module.parse_labels("1,2")


def _mock_success(monkeypatch, tmp_path, answer_claims=True):
    fake_root = tmp_path / "shirabe_report1"
    fake_repo = fake_root / "repo"
    fake_repo.mkdir(parents=True)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(main_module, "clone_repository", lambda url, timeout_seconds=120: str(fake_repo))
    monkeypatch.setattr(main_module, "check_repo_budget", lambda *a, **k: None)
    record = _record()
    check = CitationCheck(
        Citation(evidence_id="E1", path="a.py", start_line=1, end_line=2), True, "ok"
    )
    claims = (
        [
            {
                "text": "It works.",
                "citations": [{"evidence_id": "E1", "path": "a.py", "start_line": 1, "end_line": 2}],
            }
        ]
        if answer_claims
        else []
    )
    monkeypatch.setattr(
        main_module.app,
        "invoke",
        lambda state: {
            "answer": "done",
            "answer_claims": claims,
            "evidence_records": [record],
            "citation_report": [check],
            "abstained": False,
        },
    )
    return fake_root


def test_main_save_report(monkeypatch, tmp_path):
    _mock_success(monkeypatch, tmp_path)
    out = str(tmp_path / "saved.json")
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/o/r", "q", "--save-report", out])
    assert main_module.main() == 0
    loaded = load_report(out)
    assert loaded["report_version"] == "v1"
    assert loaded["run"]["provider"] == "groq"
    assert loaded["claims"][0]["text"] == "It works."


def test_main_report_commands(monkeypatch, tmp_path, capsys):
    path = str(tmp_path / "report.json")
    save_report(_report(), path)

    monkeypatch.setattr("sys.argv", ["main.py", "--inspect-report", path])
    assert main_module.main() == 0
    assert "What does this do?" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv", ["main.py", "--attach-review", path, "--labels", "1"]
    )
    assert main_module.main() == 0
    assert load_report(path)["review"]["supported"] == 1

    monkeypatch.setattr("sys.argv", ["main.py", "--delete-report", path])
    assert main_module.main() == 0
    assert "Deleted" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["main.py", "--inspect-report", path])
    assert main_module.main() == 1
    assert "Report error" in capsys.readouterr().err


def test_demo_runs_without_key(monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert demo_module.main([]) == 0
    out = capsys.readouterr().out
    assert "Evidence trail" in out
    assert "Citation integrity" in out
    assert "abstain" in out


def test_demo_save_report_is_loadable(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = str(tmp_path / "demo.json")
    assert demo_module.main(["--save-report", out]) == 0
    assert f"Saved investigation report: {out}" in capsys.readouterr().out
    loaded = load_report(out)
    assert loaded["run"]["method"] == "demo"
    assert loaded["run"]["model"] is None
