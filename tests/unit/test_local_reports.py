import json

import pytest

from gamecrafter.infrastructure.storage import json_report


def test_report_replaces_only_after_complete_serialization(tmp_path):
    path = tmp_path / "report.json"
    json_report.write_json_report(path, {"complete": False, "案例": [1]})
    json_report.write_json_report(path, {"complete": True, "案例": [1, 2]})
    assert json.loads(path.read_text(encoding="utf-8")) == {"complete": True, "案例": [1, 2]}
    with pytest.raises(TypeError):
        json_report.write_json_report(path, {"not_serializable": object()})
    assert json.loads(path.read_text(encoding="utf-8"))["complete"] is True


@pytest.mark.parametrize("step", ["fsync", "replace"])
def test_write_failure_keeps_last_complete_checkpoint(tmp_path, monkeypatch, step):
    path = tmp_path / "report.json"
    json_report.write_json_report(path, {"attempts": 1})

    def broken(*args):
        raise OSError("simulated write failure")

    monkeypatch.setattr(json_report.os, step, broken)
    with pytest.raises(OSError):
        json_report.write_json_report(path, {"attempts": 2})
    assert json.loads(path.read_text()) == {"attempts": 1}
    assert list(tmp_path.iterdir()) == [path]
