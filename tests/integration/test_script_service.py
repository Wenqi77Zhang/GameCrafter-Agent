from datetime import UTC, datetime
from uuid import UUID

import pytest
from test_marketing_service import _seed

from gamecrafter.infrastructure.database.marketing_service import DatabaseMarketingService
from gamecrafter.infrastructure.database.script_service import (
    DatabaseScriptService,
    ScriptServiceConflictError,
)


def _approved_task():
    sessions, project_id, snapshot_id = _seed()
    marketing = DatabaseMarketingService(sessions)
    task, _ = marketing.create_task(
        project_id=project_id,
        knowledge_snapshot_id=snapshot_id,
        platform="TikTok",
        markets=["US"],
        audience="English-speaking players",
        goal="Qualified awareness",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key="script-marketing-task",
    )
    marketing.add_signal(
        project_id=project_id,
        source_name="TikTok Creative Center",
        source_url="https://ads.tiktok.com/business/creativecenter/script-test",
        observed_at=datetime.now(UTC),
        region="US",
        signal_type="hashtag",
        title="#NTE",
        keywords=["NTE", "Neverness to Everness"],
        metric_name="posts",
        metric_value=1200,
        notes="Manually verified.",
        actor_id="local-user",
        command_key="script-trend-signal",
    )
    candidate = marketing.analyze(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        actor_id="local-system",
    )[0]
    marketing.review_topic(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        candidate_id=UUID(str(candidate["id"])),
        decision="approve",
        reason="Verified fit for the first script.",
        actor_id="local-user",
        command_key="script-topic-approval",
    )
    return sessions, project_id, UUID(str(task["id"]))


def test_script_generation_evaluation_human_gate_and_export() -> None:
    sessions, project_id, task_id = _approved_task()
    service = DatabaseScriptService(sessions)
    run, created = service.create_run(
        project_id=project_id,
        marketing_task_id=task_id,
        revision_budget=2,
        score_threshold=80,
        actor_id="local-user",
        command_key="script-run-first-release",
    )
    assert created is True and run["revision_budget"] == 2
    run_id = UUID(str(run["id"]))
    generated, _ = service.generate(
        project_id=project_id,
        run_id=run_id,
        actor_id="local-system",
        command_key="script-generate-v1",
    )
    generated_id = UUID(str(generated["id"]))
    evaluation, _ = service.evaluate(
        project_id=project_id,
        run_id=run_id,
        version_id=generated_id,
        command_key="script-evaluate-v1",
    )
    assert evaluation["score"] == 100 and evaluation["passed"] is True

    with pytest.raises(ScriptServiceConflictError, match="approval"):
        service.export(
            project_id=project_id,
            run_id=run_id,
            version_id=generated_id,
            format="markdown",
            command_key="script-export-too-early",
        )
    final, _ = service.final_review(
        project_id=project_id,
        run_id=run_id,
        version_id=generated_id,
        decision="approve",
        reason="Evidence, pacing, and CTA checked by the creator.",
        actor_id="local-user",
        command_key="script-final-approval",
    )
    assert final["decision"] == "approve"
    exported, _ = service.export(
        project_id=project_id,
        run_id=run_id,
        version_id=generated_id,
        format="markdown",
        command_key="script-export-markdown",
    )
    assert exported["content"].startswith("# ")
    assert len(exported["sha256"]) == 64


def test_failed_human_edit_uses_bounded_revision() -> None:
    sessions, project_id, task_id = _approved_task()
    service = DatabaseScriptService(sessions)
    run, _ = service.create_run(
        project_id=project_id,
        marketing_task_id=task_id,
        revision_budget=1,
        score_threshold=80,
        actor_id="local-user",
        command_key="script-run-revision",
    )
    run_id = UUID(str(run["id"]))
    generated, _ = service.generate(
        project_id=project_id,
        run_id=run_id,
        actor_id="local-system",
        command_key="script-generate-before-edit",
    )
    edited_content = generated["content"]
    for section in edited_content["sections"]:
        section["purpose"] = "beat"
        section["voiceover"] = "Short."
    edited, _ = service.edit(
        project_id=project_id,
        run_id=run_id,
        content=edited_content,
        actor_id="local-user",
        command_key="script-human-edit-failing",
    )
    failed, _ = service.evaluate(
        project_id=project_id,
        run_id=run_id,
        version_id=UUID(str(edited["id"])),
        command_key="script-evaluate-failing-edit",
    )
    assert failed["passed"] is False and failed["issues"]
    revised, _ = service.revise(
        project_id=project_id,
        run_id=run_id,
        actor_id="local-system",
        command_key="script-auto-revision-one",
    )
    assert revised["origin"] == "auto_revision"
    with pytest.raises(ScriptServiceConflictError, match="evaluate"):
        service.revise(
            project_id=project_id,
            run_id=run_id,
            actor_id="local-system",
            command_key="script-auto-revision-two",
        )
