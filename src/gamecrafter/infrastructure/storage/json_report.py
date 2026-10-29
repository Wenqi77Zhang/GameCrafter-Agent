"""Small local QA reports: flush a sibling file before replacing the previous checkpoint."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_json_report(path: Path, report: dict) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
