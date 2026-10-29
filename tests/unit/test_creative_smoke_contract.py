import json
import sys
from pathlib import Path
from runpy import run_path

import pytest

smoke_exit_code = run_path(
    str(Path(__file__).resolve().parents[2] / "scripts" / "creative_model_smoke.py")
)["smoke_exit_code"]
critic = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "creative_critic_smoke.py"))


def test_successful_execution_is_not_a_quality_pass():
    operations = [
        {"operation": "strategy", "status": "succeeded", "result": {"passed": True}},
        {"operation": "write", "status": "succeeded", "result": {"passed": False}},
    ]
    assert smoke_exit_code(operations, False) == 2
    assert smoke_exit_code(operations, True) == 0
    operations[0]["result"]["passed"] = False
    assert smoke_exit_code(operations, True) == 2
    operations[-1]["status"] = "needs_attention"
    assert smoke_exit_code(operations, True) == 1
    assert smoke_exit_code([], False) == 1


def test_critic_corpus_is_balanced_and_runtime_errors_are_not_successful_rejections():
    cases = critic["build_cases"]()
    assert len(cases) == 14 and len({c["case"] for c in cases}) == 14
    assert sum(c["expected_blocked"] for c in cases) == 8

    class BrokenGateway:
        def call(self, *args):
            raise TimeoutError("private-text")

    result = critic["evaluate_case"](BrokenGateway(), cases[1])
    assert result["status"] == "error" and result["passed"] is False
    assert "private-text" not in str(result)
    metrics = critic["metrics"]([result])
    assert metrics["errors"] == 1 and metrics["passed"] == 0 and metrics["evaluated"] == 0


def test_critic_must_flag_the_labelled_claim_not_an_unrelated_field():
    from gamecrafter.application.creative import Critique

    class WrongFieldGateway:
        def call(self, *args):
            return Critique.model_validate(
                {
                    "summary": "发现了其他问题但漏审目标原句",
                    "issues": [
                        {
                            "draft_quote": "other",
                            "section_index": None,
                            "severity": "blocking",
                            "category": "evidence",
                            "message": "另一个问题",
                            "fix": "另行处理",
                        }
                    ],
                    "strengths": [],
                    "fact_checks": [],
                }
            ), {}

    case = critic["build_cases"]()[1]
    result = critic["evaluate_case"](WrongFieldGateway(), case)
    assert result["blocked"] is True and result["target_blocked"] is False
    assert result["passed"] is False and critic["metrics"]([result])["misses"] == 1


def test_regression_and_holdout_inputs_are_frozen_separately():
    from gamecrafter.application.evidence_review import review_texts

    assert critic["fingerprint"](critic["build_cases"]()) == (
        "d7df46783065aee493ce8d9cde5014078914640796deb76602eb3e82c5278eef"
    )
    corpus = critic["holdout_corpus"]()
    assert corpus["version"] == "creative-support-holdout-v1"
    assert critic["fingerprint"](corpus["cases"]) == (
        "6c570fac4180a08756de493d9b34367ba0b175bb445c8e71f27082aebffd19be"
    )
    assert len(corpus["cases"]) == 16
    assert sum(case["expected_blocked"] for case in corpus["cases"]) == 8
    assert len({case["case"] for case in corpus["cases"]}) == 16
    for case in corpus["cases"]:
        fields = {text.field for text in review_texts(case["draft"])}
        assert set(case["expected_verdicts"]) == fields
        if case["expected_blocked"]:
            assert case["must_block_field"] in fields
        assert case["label_reason"]


def test_factual_positive_cannot_pass_by_being_misclassified_as_nonfactual():
    from gamecrafter.application.creative import Critique
    from gamecrafter.application.evidence_review import review_texts

    class AllNonfactualGateway:
        def call(self, role, context, schema):
            return Critique(
                summary="测试模型把所有句子都视为非事实",
                issues=[],
                strengths=[],
                fact_checks=[
                    {
                        "text_id": text.text_id,
                        "field": text.field,
                        "section_index": None,
                        "text": text.text,
                        "verdict": "NOT_A_FACT",
                        "knowledge_member_ids": [],
                        "reason": "非事实",
                    }
                    for text in review_texts(context["draft"])
                ],
            ), {}

    result = critic["evaluate_case"](AllNonfactualGateway(), critic["holdout_corpus"]()["cases"][0])
    assert result["blocked"] is False and result["passed"] is False
    assert critic["metrics"]([result])["verdict_mismatches"] == 1


def test_usage_and_errors_are_counted_without_treating_errors_as_misses():
    attempts = [
        {"status": "error", "provenance": {"duration_ms": 250, "output_tokens": 9}},
        {
            "status": "evaluated",
            "expected_blocked": True,
            "blocked": True,
            "target_blocked": False,
            "passed": False,
            "provenance": {"input_tokens": 100},
        },
    ]
    result = critic["metrics"](attempts)
    assert result["errors"] == 1 and result["misses"] == 1
    assert result["duration_ms"] == 250 and result["input_tokens"] == 100
    assert result["output_tokens"] == 9 and result["passed"] == 0
    assert result["usage_complete"] is False


def test_model_identity_is_loopback_only_and_never_downloads(monkeypatch):
    requests = []
    models = [{"name": "local:tag", "digest": "sha256"}]

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    class Client:
        def __init__(self, **options):
            assert options == {"trust_env": False, "timeout": 3}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            requests.append(url)
            return Response(
                {"version": "local-version"} if url.endswith("/version") else {"models": models}
            )

    monkeypatch.setattr(critic["httpx2"], "Client", Client)
    assert critic["local_model_identity"]("local:tag") == {
        "digest": "sha256",
        "ollama_version": "local-version",
    }
    with pytest.raises(ValueError, match="no download"):
        critic["local_model_identity"]("missing:tag")
    models.append({"name": "local:tag", "digest": "another-digest"})
    with pytest.raises(ValueError, match="ambiguous"):
        critic["local_model_identity"]("local:tag")
    models[-1]["digest"] = None
    with pytest.raises(ValueError, match="missing"):
        critic["local_model_identity"]("local:tag")
    models[-1]["digest"] = "sha256"
    assert critic["local_model_identity"]("local:tag")["digest"] == "sha256"
    assert set(requests) == {
        "http://127.0.0.1:11434/api/tags",
        "http://127.0.0.1:11434/api/version",
    }


@pytest.mark.parametrize("after", ["same", "changed", "unavailable"])
def test_finished_cases_cannot_pass_with_changed_or_unknown_model_identity(
    tmp_path, monkeypatch, after
):
    main = critic["main"]
    identities = iter(["same", after])

    def identity(model):
        value = next(identities)
        if value == "unavailable":
            raise ConnectionError("private transport detail")
        return {"digest": value, "ollama_version": "local-version"}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["critic", "--repeats", "1", "--case", "supported_genre_introduction"],
    )
    monkeypatch.setitem(main.__globals__, "local_model_identity", identity)
    monkeypatch.setitem(main.__globals__, "LocalCreativeGateway", lambda **options: object())
    monkeypatch.setitem(
        main.__globals__,
        "evaluate_case",
        lambda *args: {
            "case": "supported_genre_introduction",
            "status": "evaluated",
            "passed": True,
            "expected_blocked": False,
            "target_blocked": False,
            "blocked": False,
        },
    )
    assert main() == (0 if after == "same" else 1)
    report = json.loads(next((tmp_path / "data/qa").glob("*.json")).read_text())
    assert report["complete"] is True and report["metrics"]["passed"] == 1
    assert report["identity_unchanged"] is (after == "same")
    if after == "unavailable":
        assert report["postflight_error"] == "ConnectionError"
        assert "private transport detail" not in str(report)
    else:
        assert report["model_identity_after"]["digest"] == after


def test_ambiguous_identity_stops_before_inference(tmp_path, monkeypatch):
    main = critic["main"]

    def ambiguous(model):
        raise ValueError("Local model identity is ambiguous")

    def unexpected_inference(*args):
        pytest.fail("Ambiguous model identity must not start inference")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["critic"])
    monkeypatch.setitem(main.__globals__, "local_model_identity", ambiguous)
    monkeypatch.setitem(main.__globals__, "LocalCreativeGateway", lambda **options: object())
    monkeypatch.setitem(main.__globals__, "evaluate_case", unexpected_inference)
    assert main() == 1
    report = json.loads(next((tmp_path / "data/qa").glob("*.json")).read_text())
    assert report["complete"] is False and report["cases"] == []
    assert report["metrics"]["attempts"] == 0 and report["preflight_error"] == "ValueError"
