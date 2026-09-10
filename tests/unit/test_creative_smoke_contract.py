from pathlib import Path
from runpy import run_path

smoke_exit_code = run_path(
    str(Path(__file__).resolve().parents[2] / "scripts" / "creative_model_smoke.py")
)["smoke_exit_code"]


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
