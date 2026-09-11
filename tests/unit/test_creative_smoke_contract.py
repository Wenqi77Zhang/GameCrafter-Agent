from pathlib import Path
from runpy import run_path

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
