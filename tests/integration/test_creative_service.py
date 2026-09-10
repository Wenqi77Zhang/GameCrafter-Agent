"""Contract fixtures are deliberately synthetic; live model evidence is recorded separately."""

import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from test_script_service import _approved_task

from gamecrafter.application.creative import CreativeError, fingerprint
from gamecrafter.application.jobs import Worker
from gamecrafter.config.settings import Settings
from gamecrafter.infrastructure.database.creative_service import (
    CREATIVE_TASK,
    DatabaseCreativeService,
)
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue, JobLeaseError
from gamecrafter.infrastructure.database.models import (
    CreativeOperationRecord,
    ProjectRecord,
    WorkflowJobRecord,
)
from gamecrafter.infrastructure.database.project_portability import (
    DatabaseProjectPortabilityService,
)
from gamecrafter.infrastructure.database.script_service import (
    DatabaseScriptService,
    ScriptServiceConflictError,
)
from gamecrafter.infrastructure.database.workspace_service import DatabaseWorkspaceService
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

VOICEOVERS = [
    "Ever wondered what this game is called?",
    "The official title is Neverness to Everness.",
    "Before making promises about gameplay, start with the name and check the official source.",
    "What would you want to know next about Neverness to Everness?",
    "Save this update and tell us what you want to see next.",
]


class FixtureGateway:
    def __init__(self):
        self.calls = []
        self.fail_critic = False
        self.block = False
        self.invalid_ref = False
        self.on_call = None

    def call(self, role, context, schema):
        self.calls.append(role)
        if self.on_call:
            callback, self.on_call = self.on_call, None
            callback()
        if role in {"critique", "strategy_review"}:
            if self.fail_critic:
                raise CreativeError("fixture failure")
            result = {"summary": "这是用于自动测试的独立评审结果。", "strengths": [], "issues": []}
            if self.block:
                result["issues"] = [
                    {
                        "draft_quote": context["draft"].get("marketing_direction", "")
                        or context["draft"]["sections"][1]["voiceover"],
                        "section_index": 1 if role == "critique" else None,
                        "severity": "blocking",
                        "category": "evidence",
                        "message": "测试中发现需要修改的表述。",
                        "fix": "请简化表述并重新核验证据。",
                    }
                ]
        elif role == "strategy":
            result = {
                "marketing_direction": "用官方名称做低风险的首次认知",
                "recommended_topic": "介绍名称并征集玩家的问题",
                "why_it_fits": "目前只有名称证据，不应声称存在尚未证实的玩法。",
                "target_audience": "英语使用地区的新玩家",
                "english_hooks": ["What is NTE?", "Heard this name?"],
                "execution_steps": ["展示标题", "提出问题", "引导评论"],
                "risks": ["尚无玩法证据"],
                "knowledge_member_ids": [context["facts"][0]["snapshot_member_id"]],
                "measurement_plan": "对照两个开场的留存和评论，不预设增长结果。",
            }
        else:
            ref = (
                "wrong"
                if self.invalid_ref
                else next(
                    f["snapshot_member_id"]
                    for f in context["facts"]
                    if f["predicate"] == "game.name"
                )
            )
            voices = list(VOICEOVERS)
            if "issues" in context:
                voices[1] = "Meet the game named Neverness to Everness."
            result = {
                "title": "What is NTE?",
                "caption": "A name-first introduction.",
                "hashtags": ["#NTE"],
                "beats": [
                    {
                        "voiceover": v,
                        "on_screen_text": "Neverness to Everness",
                        "visual_direction": "Use title typography; verify any footage rights.",
                        "knowledge_member_ids": [ref],
                    }
                    for v in voices
                ],
            }
        parsed = schema.model_validate(result)
        return parsed, {
            "mode": "test_fixture",
            "model": "synthetic-test-only",
            "role": role,
            "input_tokens": 12,
            "output_tokens": 20,
            "input_sha256": fingerprint(context),
        }


def setup_creative(sessions=None):
    sessions, project_id, task_id = _approved_task(sessions, story_fact=True)
    scripts = DatabaseScriptService(sessions)
    run, _ = scripts.create_run(
        project_id=project_id,
        marketing_task_id=task_id,
        revision_budget=1,
        score_threshold=80,
        actor_id="tester",
        command_key="creative-run",
    )
    gateway = FixtureGateway()
    settings = Settings(_env_file=None, model_provider="disabled", worker_id="creative-test")
    service = DatabaseCreativeService(sessions, settings, gateway)
    queue = DatabaseJobQueue(sessions)
    worker = Worker(
        queue=queue,
        handlers={CREATIVE_TASK: service.execute},
        worker_id=settings.worker_id,
        lease_seconds=60,
    )
    return sessions, project_id, task_id, UUID(run["id"]), scripts, gateway, service, worker, queue


def enqueue(service, project, target, operation="write", key=None):
    return service.enqueue(
        project_id=project,
        target_id=target,
        operation=operation,
        command_key=key or str(uuid4()),
        actor_id="tester",
    )[0]


def test_title_only_material_is_explained_before_spending_model_tokens():
    sessions, project, task = _approved_task()
    gateway = FixtureGateway()
    service = DatabaseCreativeService(sessions, Settings(_env_file=None), gateway)
    assert service.readiness(project, task)["reason"] == "insufficient_story_evidence"
    with pytest.raises(CreativeError, match="缺少可讲述"):
        enqueue(service, project, task, "strategy")
    assert not gateway.calls and not service.list(project, task)


def test_genre_label_alone_cannot_support_an_automatic_campaign():
    sessions, project, task = _approved_task(story_fact=True, genre_only=True)
    gateway = FixtureGateway()
    service = DatabaseCreativeService(sessions, Settings(_env_file=None), gateway)
    with pytest.raises(CreativeError, match="类型等基础资料"):
        enqueue(service, project, task, "strategy")
    assert not gateway.calls


def test_blocked_strategy_is_visible_but_not_used_as_writer_evidence():
    sessions, project, task, run, _, gateway, service, worker, _ = setup_creative()
    gateway.block = True
    enqueue(service, project, task, "strategy")
    worker.run_once()
    result = service.list(project, task)[0]["result"]
    assert result["passed"] is False and result["review"]["issues"]
    enqueue(service, project, run)
    with sessions() as session:
        item = session.scalar(
            select(CreativeOperationRecord).where(CreativeOperationRecord.target_id == run)
        )
        assert "strategy_suggestion" not in item.input_data


def test_inflight_critic_cannot_replace_a_concurrent_human_edit():
    _, project, _, run, scripts, gateway, service, worker, _ = setup_creative()
    enqueue(service, project, run)
    worker.run_once()
    content = deepcopy(scripts.get_run(project_id=project, run_id=run)["versions"][-1]["content"])
    content["title"] = "My corrected title"
    enqueue(service, project, run, "critique")
    gateway.on_call = lambda: scripts.edit(
        project_id=project,
        run_id=run,
        content=content,
        actor_id="tester",
        command_key="concurrent-edit",
    )
    worker.run_once()
    result = scripts.get_run(project_id=project, run_id=run)
    assert result["versions"][-1]["content"]["title"] == "My corrected title"
    assert len(result["evaluations"]) == 1
    assert "已被修改" in service.list(project, run)[0]["error"]


def test_disabled_model_never_silently_uses_a_fixture_or_cloud():
    sessions, project, task = _approved_task(story_fact=True)
    service = DatabaseCreativeService(sessions, Settings(_env_file=None, model_provider="disabled"))
    assert service.capability()["available"] is False
    with pytest.raises(CreativeError, match="本地模型未就绪"):
        enqueue(service, project, task, "strategy")
    assert not service.list(project, task)


def test_creative_model_override_does_not_change_knowledge_model():
    sessions, _, _ = _approved_task(story_fact=True)
    settings = Settings(
        _env_file=None, ollama_model="knowledge-model", creative_ollama_model="creative-model"
    )
    service = DatabaseCreativeService(sessions, settings)
    assert service.model == "creative-model" and settings.ollama_model == "knowledge-model"


def test_overview_does_not_use_historical_approval_after_a_new_edit():
    sessions, project, _, run, scripts, _, service, worker, _ = setup_creative()
    enqueue(service, project, run)
    worker.run_once()
    record = scripts.get_run(project_id=project, run_id=run)
    version = UUID(record["versions"][-1]["id"])
    scripts.final_review(
        project_id=project,
        run_id=run,
        version_id=version,
        decision="approve",
        reason="Isolated test approval",
        actor_id="tester",
        command_key="overview-approve",
    )
    scripts.export(
        project_id=project,
        run_id=run,
        version_id=version,
        format="json",
        command_key="overview-export",
    )
    workspace = DatabaseWorkspaceService(sessions)
    before = {s["key"]: s["status"] for s in workspace.project_overview(project)["stages"]}
    assert before["creation"] == before["delivery"] == "complete"
    content = deepcopy(record["versions"][-1]["content"])
    content["title"] = "Edited and not approved"
    scripts.edit(
        project_id=project,
        run_id=run,
        content=content,
        actor_id="tester",
        command_key="overview-edit",
    )
    after = {s["key"]: s["status"] for s in workspace.project_overview(project)["stages"]}
    assert after["creation"] != "complete" and after["delivery"] != "complete"


def test_creative_stages_and_lineage_survive_project_backup_restore(tmp_path):
    sessions, project, task, run, scripts, _, service, worker, _ = setup_creative()
    enqueue(service, project, task, "strategy")
    worker.run_once()
    enqueue(service, project, run)
    worker.run_once()
    before = scripts.get_run(project_id=project, run_id=run)
    operations = service.list(project, None)
    portable = DatabaseProjectPortabilityService(sessions, LocalObjectStorage(tmp_path / "objects"))
    with sessions() as session:
        slug = session.get(ProjectRecord, project).slug
    _, archive = portable.export_zip(project)
    portable.delete_project(project_id=project, confirmation=f"DELETE {slug}")
    portable.restore_zip(archive)
    assert scripts.get_run(project_id=project, run_id=run) == before
    assert service.list(project, None) == operations


@pytest.mark.postgres
def test_postgres_creative_durable_workflow_and_immutable_version_metadata():
    url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        _, project, task, run, scripts, _, service, worker, _ = setup_creative(sessions)
        enqueue(service, project, task, "strategy")
        assert worker.run_once()
        assert service.list(project, task)[0]["result"]["passed"]
        enqueue(service, project, run)
        assert worker.run_once()
        result = scripts.get_run(project_id=project, run_id=run)
        assert result["versions"][0]["generation_metadata"]["mode"] == "local_model"
        assert result["evaluations"][0]["semantic_report"]["mode"] == "local_model"
        assert not result["final_reviews"]
    finally:
        engine.dispose()


def test_real_orchestration_is_durable_idempotent_and_final_gate_is_not_model_controlled():
    sessions, project, task, run, scripts, gateway, service, worker, _ = setup_creative()
    first = enqueue(service, project, run, key="durable-command")
    duplicate = enqueue(service, project, run, key="second-click-command")
    assert first["id"] == duplicate["id"]
    assert (
        first["status"] == "queued"
        and not scripts.get_run(project_id=project, run_id=run)["versions"]
    )
    assert worker.run_once()
    result = scripts.get_run(project_id=project, run_id=run)
    assert gateway.calls == ["write", "critique"]
    assert result["evaluations"][0]["passed"] and result["evaluations"][0]["score"] == 100
    assert not result["final_reviews"]
    version = UUID(result["versions"][0]["id"])
    assert any(f["sources"][0]["quote"] == "Neverness to Everness" for f in result["evidence"])
    with pytest.raises(ScriptServiceConflictError):
        scripts.evaluate(
            project_id=project, run_id=run, version_id=version, command_key="bypass-critic"
        )
    with pytest.raises(ScriptServiceConflictError, match="approval"):
        scripts.export(
            project_id=project,
            run_id=run,
            version_id=version,
            format="markdown",
            command_key="early-export",
        )
    for decision in ("approve", "reject"):
        scripts.final_review(
            project_id=project,
            run_id=run,
            version_id=version,
            decision=decision,
            reason="Checked the actual script.",
            actor_id="tester",
            command_key="review-" + decision,
        )
        if decision == "approve":
            exported, _ = scripts.export(
                project_id=project,
                run_id=run,
                version_id=version,
                format="markdown",
                command_key="approved-export",
            )
            assert "https://nte.perfectworld.com/en/main.html" in exported["content"]
            assert "Quote: Neverness to Everness" in exported["content"]
    with pytest.raises(ScriptServiceConflictError, match="approval"):
        scripts.export(
            project_id=project,
            run_id=run,
            version_id=version,
            format="markdown",
            command_key="revoked-export",
        )
    # Durable retry reuses output, but never creates a duplicate version.
    assert enqueue(service, project, run, key="durable-command")["id"] == first["id"]
    assert len(scripts.get_run(project_id=project, run_id=run)["versions"]) == 1


def test_failed_critic_reuses_writer_and_revision_changes_the_actual_draft():
    sessions, project, _, run, scripts, gateway, service, worker, _ = setup_creative()
    gateway.fail_critic = True
    item = enqueue(service, project, run)
    worker.run_once()
    assert service.list(project, run)[0]["status"] == "needs_attention"
    assert not scripts.get_run(project_id=project, run_id=run)["versions"]
    gateway.fail_critic = False
    gateway.block = True
    DatabaseWorkspaceService(sessions).retry_run(
        run_id=UUID(item["run_id"]), command_key="retry-one", actor_id="tester"
    )
    worker.run_once()
    assert gateway.calls == ["write", "critique", "critique"]
    assert not scripts.get_run(project_id=project, run_id=run)["evaluations"][-1]["passed"]
    gateway.block = False
    enqueue(service, project, run, "revise")
    worker.run_once()
    result = scripts.get_run(project_id=project, run_id=run)
    assert len(result["versions"]) == 2
    assert result["versions"][1]["content"] != result["versions"][0]["content"]
    assert result["versions"][1]["parent_version_id"] == result["versions"][0]["id"]
    assert result["revisions_used"] == 1 and result["evaluations"][-1]["passed"]


def test_cancel_and_foreign_citations_cannot_publish_late_or_invalid_output():
    sessions, project, _, run, scripts, gateway, service, worker, _ = setup_creative()
    item = enqueue(service, project, run)
    gateway.on_call = lambda: service.cancel(project, UUID(item["id"]), "tester")
    worker.run_once()
    assert service.list(project, run)[0]["status"] == "cancelled"
    assert not scripts.get_run(project_id=project, run_id=run)["versions"]
    gateway.invalid_ref = True
    enqueue(service, project, run)
    worker.run_once()
    assert service.list(project, run)[0]["status"] == "needs_attention"
    assert gateway.calls == ["write", "write"]
    assert not scripts.get_run(project_id=project, run_id=run)["versions"]


def test_frozen_context_strategy_and_cross_project_boundary():
    sessions, project, task, run, _, gateway, service, worker, _ = setup_creative()
    enqueue(service, project, task, "strategy")
    worker.run_once()
    assert service.list(project, task)[0]["result"]["strategy"]["english_hooks"]
    with pytest.raises(Exception, match="not found"):
        enqueue(service, uuid4(), run)
    enqueue(service, project, run)
    with sessions.begin() as session:
        record = session.scalar(
            select(CreativeOperationRecord).where(CreativeOperationRecord.target_id == run)
        )
        changed = deepcopy(record.input_data)
        changed["model"] = "tampered"
        record.input_data = changed
    worker.run_once()
    assert gateway.calls == ["strategy", "strategy_review"]
    assert service.list(project, run)[0]["status"] == "needs_attention"


def test_worker_cannot_complete_a_newer_attempt_with_the_same_worker_id():
    sessions, project, _, run, _, _, service, _, queue = setup_creative()
    enqueue(service, project, run)
    old = queue.claim_next(worker_id="creative-test", lease_seconds=60)
    with sessions.begin() as session:
        record = session.get(WorkflowJobRecord, old.id)
        record.attempts += 1
    with pytest.raises(JobLeaseError):
        queue.complete(old, worker_id="creative-test")


@pytest.mark.parametrize("value", [[{}], [["nested"]], [1]])
def test_malformed_citation_ids_are_a_conflict_not_a_server_crash(value):
    _, project, _, run, scripts, _, _, _, _ = setup_creative()
    version, _ = scripts.generate(
        project_id=project, run_id=run, actor_id="tester", command_key="manual-draft"
    )
    content = deepcopy(version["content"])
    content["sections"][0]["knowledge_member_ids"] = value
    with pytest.raises(ScriptServiceConflictError):
        scripts.edit(
            project_id=project,
            run_id=run,
            content=content,
            actor_id="tester",
            command_key="bad-edit",
        )
