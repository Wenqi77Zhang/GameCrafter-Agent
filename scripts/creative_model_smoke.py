"""Opt-in live Ollama smoke using an isolated SQLite database and labelled evidence fixture.

No paid API and no writes to the user's project/database. This is not a live web ingestion test.
"""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "integration"))
from test_script_service import _approved_task  # noqa: E402

from gamecrafter.application.jobs import Worker  # noqa: E402
from gamecrafter.config.settings import Settings  # noqa: E402
from gamecrafter.infrastructure.database.creative_service import (  # noqa: E402
    CREATIVE_TASK,
    DatabaseCreativeService,
)
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue  # noqa: E402
from gamecrafter.infrastructure.database.models import Base  # noqa: E402
from gamecrafter.infrastructure.database.script_service import DatabaseScriptService  # noqa: E402
from gamecrafter.infrastructure.local_ai.creative import LocalCreativeGateway  # noqa: E402
from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport  # noqa: E402


def smoke_exit_code(operations, latest_review_passed):
    """Transport completion is not content acceptance, and neither is human approval."""
    if not operations or any(item["status"] != "succeeded" for item in operations):
        return 1
    strategy_passed = any(
        item["operation"] == "strategy" and item["result"].get("passed") is True
        for item in operations
    )
    return 0 if strategy_passed and latest_review_passed else 2


def main():
    from uuid import UUID

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--debug-fixture", action="store_true")
    parser.add_argument("--revisions", type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()

    output = Path("data/qa")
    output.mkdir(parents=True, exist_ok=True)
    database = output / f"creative-live-{uuid4().hex[:10]}.sqlite3"
    url = "sqlite+pysqlite:///" + database.resolve().as_posix()
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    sessions, project, task = _approved_task(sessions, story_fact=True)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=url,
        model_provider="ollama",
        ollama_model=args.model,
        ollama_timeout_seconds=300,
        worker_id="creative-live-smoke",
    )
    gateway = None
    if args.debug_fixture:
        transport = OllamaLoopbackTransport(
            base_url=str(settings.ollama_base_url), timeout_seconds=300
        )

        def captured_transport(request):
            response = transport(request)
            (output / "creative-fixture-raw.json").write_text(
                json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return response

        gateway = LocalCreativeGateway(model=settings.ollama_model, transport=captured_transport)
    service = DatabaseCreativeService(sessions, settings, gateway)
    scripts = DatabaseScriptService(sessions)
    worker = Worker(
        queue=DatabaseJobQueue(sessions),
        handlers={CREATIVE_TASK: service.execute},
        worker_id=settings.worker_id,
        lease_seconds=60,
    )
    report = {
        "evidence_mode": (
            "controlled official name, genre and location quote fixtures; not live ingestion"
        ),
        "model_mode": "real_loopback_ollama",
        "database": str(database.resolve()),
        "project_id": str(project),
        "task_id": str(task),
        "operations": [],
    }

    def save_report():
        body = json.dumps(report, ensure_ascii=False, indent=2)
        (output / "creative-live-latest.json").write_text(body, encoding="utf-8")
        database.with_suffix(".json").write_text(body, encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items() if k != "operations"}), flush=True)
    for operation in ("strategy", "write"):
        target = task
        if operation == "write":
            run, _ = scripts.create_run(
                project_id=project,
                marketing_task_id=task,
                revision_budget=2,
                score_threshold=80,
                actor_id="acceptance-test",
                command_key="live-script-run",
            )
            target = UUID(run["id"])
            report["script_run_id"] = str(target)
        queued, _ = service.enqueue(
            project_id=project,
            target_id=target,
            operation=operation,
            actor_id="acceptance-test",
            command_key=f"live-{operation}-smoke",
        )
        print(f"Running real local {operation}: {queued['id']}", flush=True)
        worker.run_once()
        result = service.list(project, target)[0]
        report["operations"].append(result)
        print(
            json.dumps(
                {k: result[k] for k in ("id", "status", "checkpoint", "error")}, ensure_ascii=False
            ),
            flush=True,
        )
        save_report()
        if result["status"] != "succeeded":
            report.update(exit_code=1, latest_review_passed=False, human_approval_granted=False)
            save_report()
            return 1
    run = scripts.get_run(project_id=project, run_id=target)
    for index in range(args.revisions):
        if run["evaluations"][-1]["passed"]:
            break
        service.enqueue(
            project_id=project,
            target_id=target,
            operation="revise",
            actor_id="acceptance-test",
            command_key=f"live-revise-{index}",
        )
        worker.run_once()
        revised = service.list(project, target)[0]
        report["operations"].append(revised)
        print(
            json.dumps(
                {k: revised[k] for k in ("id", "status", "checkpoint", "error")}, ensure_ascii=False
            ),
            flush=True,
        )
        run = scripts.get_run(project_id=project, run_id=target)
        if revised["status"] != "succeeded":
            break
    report["script"] = run
    passed = bool(run["evaluations"] and run["evaluations"][-1]["passed"])
    report["exit_code"] = smoke_exit_code(report["operations"], passed)
    report["latest_review_passed"] = passed
    report["human_approval_granted"] = False
    save_report()
    print("Live model results saved; final human approval was NOT granted.", flush=True)
    print(
        json.dumps(
            {
                "versions": len(run["versions"]),
                "latest_review_passed": passed,
                "exit_code": report["exit_code"],
            }
        ),
        flush=True,
    )
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
