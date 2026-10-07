import evaluate as evaluate_module
from errors import ConfigError
from eval_cases import CASES, DATASET_REVISION, RETRIEVAL_CUTOFF_K
from eval_metrics import (
    abstention_precision_recall,
    citation_integrity_score,
    claim_support_score,
    file_recall_at_k,
    range_recall,
)
from evaluate import check_labels, retrieve_case, run_fixture_evaluation


def _without_elapsed(report):
    scrubbed = {**report, "cases": []}
    for row in report["cases"]:
        scrubbed["cases"].append({k: v for k, v in row.items() if k != "elapsed_s"})
    metrics = {**report["metrics"]}
    metrics.pop("efficiency", None)
    scrubbed["metrics"] = metrics
    return scrubbed


def test_dataset_has_expected_coverage():
    kinds = {case.case_id for case in CASES}
    assert kinds == {
        "calc-single",
        "flow-control",
        "flow-data",
        "shop-config",
        "guarded-failure",
        "auth-unanswerable",
    }
    assert DATASET_REVISION == "v1"
    assert RETRIEVAL_CUTOFF_K == 5
    unanswerable = [case for case in CASES if not case.answerable]
    assert len(unanswerable) == 1
    assert unanswerable[0].relevant == ()


def test_all_labels_resolve_to_real_lines():
    for case in CASES:
        assert check_labels(case) == []


def test_file_recall_at_k():
    metric = file_recall_at_k(["a.py", "b.py"], {"a.py", "c.py"}, 5)
    assert (metric.value, metric.numerator, metric.denominator) == (0.5, 1, 2)
    cutoff = file_recall_at_k(["a.py", "b.py"], {"b.py"}, 1)
    assert cutoff.value == 0.0
    empty = file_recall_at_k([], set(), 5)
    assert empty.value == 1.0


def test_range_recall_overlap_and_single_line():
    retrieved = [("a.py", 8, 12)]
    assert range_recall(retrieved, [("a.py", 10, 15)]).value == 1.0
    assert range_recall(retrieved, [("a.py", 5, 7)]).value == 0.0
    assert range_recall(retrieved, [("b.py", 10, 15)]).value == 0.0
    assert range_recall(retrieved, [("a.py", 5, 5)]).value == 0.0
    assert range_recall([("a.py", 3, 6)], [("a.py", 5, 5)]).value == 1.0
    assert range_recall([], []).value == 1.0


def test_citation_integrity_and_empty():
    assert citation_integrity_score(3, 4).value == 0.75
    assert citation_integrity_score(0, 0).value is None


def test_abstention_precision_recall():
    precision, recall = abstention_precision_recall([(True, False), (False, True)])
    assert (precision.value, precision.numerator, precision.denominator) == (1.0, 1, 1)
    assert (recall.value, recall.numerator, recall.denominator) == (1.0, 1, 1)
    precision, recall = abstention_precision_recall([(True, False)])
    assert precision.value is None
    assert recall.value is None


def test_claim_support_requires_labels():
    assert claim_support_score([]).value is None
    scored = claim_support_score([True, True, False])
    assert scored.value == 2 / 3
    assert (scored.numerator, scored.denominator) == (2, 3)


def test_fixture_run_has_no_failures():
    report = run_fixture_evaluation()
    assert report["failures"] == []
    assert report["dataset_revision"] == "v1"
    assert report["case_count"] == len(CASES) == 6


def test_fixture_run_is_deterministic():
    assert _without_elapsed(run_fixture_evaluation()) == _without_elapsed(run_fixture_evaluation())


def test_fixture_run_pins_measured_gaps():
    report = run_fixture_evaluation()
    assert report["retrieval_gap_cases"] == ["calc-single", "flow-control"]
    by_id = {row["case_id"]: row for row in report["cases"]}
    assert by_id["flow-control"]["file_recall_at_k"] == 2 / 3
    assert by_id["auth-unanswerable"]["abstained"] is True
    assert report["metrics"]["citation_integrity"] == {"value": 1.0, "numerator": 18, "denominator": 18}
    assert report["metrics"]["abstention_precision"]["value"] == 1.0
    assert report["metrics"]["abstention_recall"]["value"] == 1.0
    assert report["metrics"]["claim_support"]["value"] is None


def test_retrieve_case_uses_pinned_queries():
    files, _ = retrieve_case(next(case for case in CASES if case.case_id == "flow-control"))
    assert "models.py" not in files


def test_fixture_cli_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["evaluate.py", "--mode", "fixture"])
    assert evaluate_module.main() == 0
    assert "dataset v1" in capsys.readouterr().out


def test_live_mode_needs_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    try:
        evaluate_module.run_live_evaluation()
    except ConfigError:
        return
    raise AssertionError("live evaluation must require OPENROUTER_API_KEY")
