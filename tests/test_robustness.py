import json
import os
from pathlib import Path

import pytest

import demo as demo_module
import evaluate as evaluate_module
import main as main_module
import nodes as nodes_module
from config import load_settings, tracing_disabled
from errors import ConfigError, ProviderError
from tools import iter_text_files, load_text_lines, search_hits


def _node_state(**overrides):
    state = {
        "repo_url": "https://github.com/example/repo",
        "repo_path": "",
        "question": "What does this do?",
        "plan": ["test"],
        "evidence": [],
        "evidence_records": [],
        "max_evidence_chars": 30000,
        "analysis": "",
        "answer": "",
        "answer_claims": [],
        "citation_report": [],
        "abstained": False,
        "iteration": 0,
        "max_iterations": 3,
        "needs_more_evidence": False,
    }
    state.update(overrides)
    return state


def test_analyzer_honors_evidence_budget(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def target_function():\n    pass\n")
    found = nodes_module.investigate_node(_node_state(repo_path=str(tmp_path), plan=["target"]))
    assert found["evidence"]

    captured = {}

    def _fake_analyze(prompt):
        captured["prompt"] = prompt
        return "analysis done\nNEEDS_MORE_EVIDENCE: false"

    monkeypatch.setattr(nodes_module, "_invoke", _fake_analyze)
    tight = _node_state(
        repo_path=str(tmp_path),
        evidence=found["evidence"],
        evidence_records=found["evidence_records"],
        max_evidence_chars=5,
    )
    result = nodes_module.analyze_node(tight)
    assert result["needs_more_evidence"] is False
    assert "target_function" not in captured["prompt"]


def test_explainer_honors_evidence_budget(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def target_function():\n    pass\n")
    found = nodes_module.investigate_node(_node_state(repo_path=str(tmp_path), plan=["target"]))

    payload = json.dumps({"claims": [{"text": "Works.", "evidence": ["E1"]}]})
    captured = {}

    def _fake_explain(prompt):
        captured["p"] = prompt
        return payload

    monkeypatch.setattr(nodes_module, "_invoke", _fake_explain)
    state = _node_state(
        repo_path=str(tmp_path),
        evidence=found["evidence"],
        evidence_records=found["evidence_records"],
        max_evidence_chars=5,
    )
    result = nodes_module.explain_node(state)
    assert result["abstained"] is False
    assert "target_function" not in captured["p"]


def test_analyzer_flag_parsing(monkeypatch):
    monkeypatch.setattr(nodes_module, "_invoke", lambda _prompt: "x\nNEEDS_MORE_EVIDENCE: TRUE")
    assert nodes_module.analyze_node(_node_state())["needs_more_evidence"] is True


def test_planner_accepts_valid_and_fenced_output(monkeypatch):
    monkeypatch.setattr(nodes_module, "_invoke", lambda _p: '{"queries": ["alpha", "beta"]} ')
    assert nodes_module.plan_node(_node_state()) == {"plan": ["alpha", "beta"]}
    monkeypatch.setattr(
        nodes_module, "_invoke", lambda _p: '```json\n{"queries": ["only"]}\n```'
    )
    assert nodes_module.plan_node(_node_state()) == {"plan": ["only"]}


@pytest.mark.parametrize(
    "output",
    [
        "not json",
        '{"nope": []}',
        '{"queries": []}',
        '{"queries": "alpha"}',
        '{"queries": ["", "  "]}',
        '{"queries": ["ok", 42]}',
    ],
)
def test_planner_rejects_malformed_output(monkeypatch, output):
    monkeypatch.setattr(nodes_module, "_invoke", lambda _p: output)
    with pytest.raises(ProviderError):
        nodes_module.plan_node(_node_state())


def test_route_respects_iteration_budget():
    route = nodes_module.route_after_analysis
    assert route(_node_state(needs_more_evidence=True, iteration=0)) == "investigate"
    assert route(_node_state(needs_more_evidence=True, iteration=2)) == "investigate"
    assert route(_node_state(needs_more_evidence=True, iteration=3)) == "explain"
    assert route(_node_state(needs_more_evidence=False, iteration=0)) == "explain"


def test_search_cache_matches_uncached():
    fixture_dir = str(Path(__file__).parent / "fixtures" / "flow")
    cached = load_text_lines(fixture_dir)
    assert set(cached) == {"handler.py", "service.py", "models.py"}
    for query in ["handle_order", "price_order", "discount rate", "for_customer"]:
        assert search_hits(fixture_dir, query, lines_cache=cached) == search_hits(fixture_dir, query)
    assert search_hits(fixture_dir, "handle_order") == search_hits(fixture_dir, "handle_order")


def test_text_scan_is_sorted(tmp_path):
    for name in ["z.py", "a.py", "m.py"]:
        (tmp_path / name).write_text("x = 1\n")
    found = [path.name for path in iter_text_files(str(tmp_path))]
    assert found == sorted(found)


def test_tracing_disabled_restores_environment(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    with tracing_disabled():
        assert os.environ["LANGSMITH_TRACING"] == "false"
        assert "LANGCHAIN_TRACING_V2" not in os.environ
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_tracing_disabled_when_nothing_set(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    with tracing_disabled():
        assert os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_TRACING" not in os.environ


def test_fixture_eval_forces_tracing_off_without_keys(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    report = evaluate_module.run_fixture_evaluation()
    assert report["failures"] == []
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_demo_forces_tracing_off_without_keys(monkeypatch, capsys):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert demo_module.main([]) == 0
    assert "Evidence trail" in capsys.readouterr().out
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_tracing_without_key_is_a_config_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="LANGSMITH_API_KEY"):
        load_settings()


def test_tracing_settings_load_with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "trace-key-123")
    settings = load_settings()
    assert settings.langsmith_api_key == "trace-key-123"
    assert settings.langsmith_project == "shirabe"
    assert "trace-key-123" not in repr(settings)

    monkeypatch.setenv("LANGSMITH_PROJECT", "custom")
    assert load_settings().langsmith_project == "custom"


def test_main_enables_tracing_explicitly(monkeypatch, tmp_path):
    fake_root = tmp_path / "shirabe_trace1"
    fake_repo = fake_root / "repo"
    fake_repo.mkdir(parents=True)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "trace-key-123")
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.setattr(main_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["main.py", "https://github.com/o/r", "q"])
    monkeypatch.setattr(main_module, "clone_repository", lambda url, timeout_seconds=120: str(fake_repo))
    monkeypatch.setattr(main_module, "check_repo_budget", lambda *a, **k: None)
    monkeypatch.setattr(
        main_module.app,
        "invoke",
        lambda state: {
            "answer": "done",
            "answer_claims": [],
            "evidence_records": [],
            "citation_report": [],
            "abstained": True,
        },
    )
    assert main_module.main() == 0
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "trace-key-123"
    assert os.environ["LANGSMITH_PROJECT"] == "shirabe"
