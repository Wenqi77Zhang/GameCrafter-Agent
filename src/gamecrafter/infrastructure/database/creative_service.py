"""Durable local creative orchestration with frozen inputs and fenced publication."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID

from sqlalchemy import func, select

from gamecrafter.application.creative import (
    PROMPT_VERSION,
    RULE_VERSION,
    CreativeError,
    Critique,
    ScriptDraft,
    Strategy,
    assemble_script,
    check_references,
    evidence_readiness,
    fingerprint,
    readiness_report,
)
from gamecrafter.application.jobs import ClaimedJob, TerminalJobError
from gamecrafter.infrastructure.database.creative_context import snapshot_facts
from gamecrafter.infrastructure.database.marketing_service import DatabaseMarketingService
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    CreativeOperationRecord,
    MarketingTaskRecord,
    ScriptEvaluationRecord,
    ScriptRunRecord,
    ScriptVersionRecord,
    TopicCandidateRecord,
    TrendSignalRecord,
    WorkflowJobRecord,
    WorkflowRunRecord,
)
from gamecrafter.infrastructure.database.script_service import DatabaseScriptService
from gamecrafter.infrastructure.local_ai.creative import CreativeCallError, LocalCreativeGateway
from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport

CREATIVE_TASK = "creative.assist"
ACTIVE = ("queued", "running", "retry_wait")


class DatabaseCreativeService:
    def __init__(self, sessions, settings, gateway=None):
        self.sessions = sessions
        self.settings = settings
        self.gateway = gateway
        self.scripts = DatabaseScriptService(sessions)
        self.model = settings.creative_ollama_model or settings.ollama_model

    def capability(self):
        available = False
        if self.settings.model_provider == "ollama":
            try:
                available = OllamaLoopbackTransport(
                    base_url=str(self.settings.ollama_base_url),
                    timeout_seconds=3,
                ).has_model(self.model)
            except Exception:
                available = False
        return {
            "available": available,
            "mode": "local_model",
            "model": self.model,
            "paid_api_calls": 0,
            "prompt_version": PROMPT_VERSION,
            "reason": "ready" if available else "local_model_unavailable",
        }

    def enqueue(self, *, project_id, target_id, operation, command_key, actor_id):
        if operation not in {"strategy", "write", "revise", "critique"}:
            raise CreativeError("不支持的创作操作。")
        key = self.scripts._key(command_key)
        with self.sessions.begin() as session:
            self.scripts._lock_project(session, project_id)
            existing = session.scalar(
                select(WorkflowRunRecord).where(
                    WorkflowRunRecord.project_id == project_id,
                    WorkflowRunRecord.idempotency_key == key,
                )
            )
            if existing:
                item = session.scalar(
                    select(CreativeOperationRecord).where(
                        CreativeOperationRecord.workflow_run_id == existing.id
                    )
                )
                if not item or item.target_id != target_id or item.operation != operation:
                    raise CreativeError("同一提交标识已用于另一项操作。")
                return self._public(item, existing), False
            pending = session.scalar(
                select(CreativeOperationRecord)
                .join(
                    WorkflowRunRecord,
                    CreativeOperationRecord.workflow_run_id == WorkflowRunRecord.id,
                )
                .where(
                    CreativeOperationRecord.project_id == project_id,
                    CreativeOperationRecord.target_id == target_id,
                    WorkflowRunRecord.status.in_(ACTIVE),
                )
            )
            if pending:
                if pending.operation != operation:
                    raise CreativeError("当前目标已有运行中的操作，请等待或取消后再提交。")
                return self._public(
                    pending, session.get(WorkflowRunRecord, pending.workflow_run_id)
                ), False
            if not self.gateway and not self.capability()["available"]:
                raise CreativeError(
                    "本地模型未就绪，请先启动 Ollama 并加载已配置模型。不会调用付费接口。"
                )
            context = self._context(session, project_id, target_id, operation)
            context["model"] = self.model
            context["as_of_utc"] = datetime.now(UTC).isoformat()
            context["prompt_version"] = PROMPT_VERSION
            if len(str(context).encode()) > 90_000:
                raise CreativeError("创作材料过多，请发布更聚焦的知识快照。")
            run = WorkflowRunRecord(
                project_id=project_id, idempotency_key=key, workflow_kind=CREATIVE_TASK
            )
            session.add(run)
            session.flush()
            item = CreativeOperationRecord(
                project_id=project_id,
                workflow_run_id=run.id,
                operation=operation,
                target_id=target_id,
                input_data=context,
                input_sha256=fingerprint(context),
            )
            session.add(item)
            session.flush()
            session.add(
                WorkflowJobRecord(
                    run_id=run.id,
                    task_type=CREATIVE_TASK,
                    payload={"operation_id": str(item.id)},
                    max_attempts=2,
                    available_at=datetime.now(UTC),
                )
            )
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=run.id,
                    event_type="creative.queued",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "operation_id": str(item.id),
                        "operation": operation,
                        "input_sha256": item.input_sha256,
                        "prompt_version": PROMPT_VERSION,
                    },
                )
            )
            return self._public(item, run), True

    def list(self, project_id, target_id):
        with self.sessions() as session:
            self.scripts._require_project(session, project_id)
            query = select(CreativeOperationRecord).where(
                CreativeOperationRecord.project_id == project_id
            )
            if target_id:
                query = query.where(CreativeOperationRecord.target_id == target_id)
            return [
                self._public(item, session.get(WorkflowRunRecord, item.workflow_run_id))
                for item in session.scalars(
                    query.order_by(CreativeOperationRecord.created_at.desc()).limit(50)
                )
            ]

    def readiness(self, project_id, target_id):
        if not target_id:
            return None
        with self.sessions() as session:
            self.scripts._require_project(session, project_id)
            target = session.get(MarketingTaskRecord, target_id) or session.get(
                ScriptRunRecord, target_id
            )
            if not target or target.project_id != project_id:
                raise CreativeError("创作目标不存在。")
            return evidence_readiness(snapshot_facts(session, target.knowledge_snapshot_id))

    def cancel(self, project_id, operation_id, actor_id):
        with self.sessions.begin() as session:
            item = session.get(CreativeOperationRecord, operation_id)
            if not item or item.project_id != project_id:
                raise CreativeError("创作任务不存在。")
            job = session.scalar(
                select(WorkflowJobRecord)
                .where(WorkflowJobRecord.run_id == item.workflow_run_id)
                .with_for_update()
            )
            run = session.get(WorkflowRunRecord, item.workflow_run_id, with_for_update=True)
            if run.status not in ACTIVE:
                return self._public(item, run)
            job.status = "cancelled"
            job.lease_owner = None
            job.lease_expires_at = None
            run.status = "cancelled"
            run.version += 1
            run.finished_at = datetime.now(UTC)
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=run.id,
                    event_type="creative.cancelled",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={"operation_id": str(item.id)},
                )
            )
            return self._public(item, run)

    @staticmethod
    def _public(item, run):
        return {
            "id": str(item.id),
            "run_id": str(run.id),
            "target_id": str(item.target_id),
            "operation": item.operation,
            "review_current": item.input_data.get("prompt_version") == PROMPT_VERSION,
            "status": run.status,
            "checkpoint": run.checkpoint,
            "error": run.last_error_detail,
            "result": item.result or {},
            "model": item.input_data.get("model"),
            "candidate_id": item.input_data.get("brief", {}).get("candidate_id"),
            "input_sha256": item.input_sha256,
            "created_at": item.created_at.isoformat(),
        }

    def _context(self, session, project_id, target_id, operation):
        if operation == "strategy":
            brief = DatabaseMarketingService(self.sessions).get_strategy_brief(
                project_id=project_id, task_id=target_id
            )
            task = session.get(MarketingTaskRecord, target_id)
            # Deterministic scores must never become evidence of marketing effectiveness.
            model_brief = {
                key: brief[key]
                for key in (
                    "candidate_id",
                    "game_name",
                    "audience",
                    "goal",
                    "platform",
                    "markets",
                    "duration_seconds",
                )
            }
            # A manually entered popularity number is neither a verified metric nor a media library.
            model_brief["topic_reference"] = {
                key: brief["trend_evidence"].get(key)
                for key in ("title", "region", "source_url", "observed_at")
            }
            model_brief["topic_reference"]["independently_verified"] = False
            facts = snapshot_facts(session, task.knowledge_snapshot_id)
            readiness = evidence_readiness(facts)
            if not readiness["ready"]:
                raise CreativeError(readiness["message"])
            context = {"brief": model_brief, "facts": facts}
            previous = session.scalar(
                select(CreativeOperationRecord)
                .where(
                    CreativeOperationRecord.project_id == project_id,
                    CreativeOperationRecord.target_id == task.id,
                    CreativeOperationRecord.operation == "strategy",
                )
                .order_by(CreativeOperationRecord.created_at.desc())
            )
            if (
                previous
                and previous.result.get("passed") is False
                and previous.result.get("strategy")
                and previous.input_data["brief"]["candidate_id"] == brief["candidate_id"]
            ):
                context["previous_strategy"] = previous.result["strategy"]
                context["revision_issues"] = previous.result.get("review", {}).get("issues", [])
            return context
        run = self.scripts._require_run(session, project_id, target_id)
        latest = self.scripts._latest_version(session, run.id)
        if operation == "write" and latest:
            raise CreativeError("已有脚本，请选择评审或修订，不要重复生成初稿。")
        if operation != "write" and not latest:
            raise CreativeError("请先生成或保存一份脚本。")
        task = session.get(MarketingTaskRecord, run.marketing_task_id)
        if not 15 <= task.duration_seconds <= 90:
            raise CreativeError("本地模型创作目前支持 15–90 秒英语 TikTok 脚本。")
        candidate = session.get(TopicCandidateRecord, run.topic_candidate_id)
        trend = session.get(TrendSignalRecord, candidate.trend_signal_id)
        context = {
            "brief": {
                "audience": task.audience,
                "goal": task.goal,
                "markets": task.markets,
                "approved_topic_title": trend.title,
                "candidate_id": str(candidate.id),
            },
            "facts": snapshot_facts(session, run.knowledge_snapshot_id),
            "trend": {
                "id": str(trend.id),
                "title": trend.title,
                "source": trend.source_name,
                "url": trend.source_url,
                "observed_at": trend.observed_at.isoformat(),
                "region": trend.region,
            },
            "skeleton": self.scripts._template(session, run),
            "base_version_id": str(latest.id) if latest else None,
        }
        if operation in {"write", "revise"}:
            readiness = evidence_readiness(context["facts"])
            if not readiness["ready"]:
                raise CreativeError(readiness["message"])
        strategy = session.scalar(
            select(CreativeOperationRecord)
            .where(
                CreativeOperationRecord.project_id == project_id,
                CreativeOperationRecord.target_id == task.id,
                CreativeOperationRecord.operation == "strategy",
            )
            .order_by(CreativeOperationRecord.created_at.desc())
        )
        if (
            strategy
            and strategy.result.get("strategy")
            and strategy.result.get("passed") is True
            and strategy.input_data.get("prompt_version") == PROMPT_VERSION
            and (strategy.input_data["brief"]["candidate_id"] == str(candidate.id))
        ):
            context["strategy_suggestion"] = strategy.result["strategy"]
        if latest:
            context["previous_script"] = latest.content
        if operation == "revise":
            evaluation = session.scalar(
                select(ScriptEvaluationRecord)
                .where(ScriptEvaluationRecord.script_version_id == latest.id)
                .order_by(
                    ScriptEvaluationRecord.created_at.desc(), ScriptEvaluationRecord.id.desc()
                )
            )
            if not evaluation:
                raise CreativeError("请先评审当前版本，让修订有明确的问题依据。")
            if evaluation.passed:
                raise CreativeError("当前版本已通过检查；如需改动，可在逐镜编辑中保存新版本。")
            used = session.scalar(
                select(func.count())
                .select_from(ScriptVersionRecord)
                .where(
                    ScriptVersionRecord.run_id == run.id,
                    ScriptVersionRecord.origin == "auto_revision",
                )
            )
            if used >= run.revision_budget:
                raise CreativeError("自动修订次数已用完，请手动编辑后重新评审。")
            context["issues"] = {"rules": evaluation.issues, "semantic": evaluation.semantic_report}
        return deepcopy(context)

    def execute(self, job: ClaimedJob):
        stopped = Event()
        lost = Event()

        def pulse():
            while not stopped.wait(10):
                try:
                    self._touch(job)
                except Exception:
                    lost.set()
                    return

        self._touch(job)
        thread = Thread(target=pulse, daemon=True)
        thread.start()
        try:
            with self.sessions() as session:
                item = session.get(CreativeOperationRecord, UUID(job.payload["operation_id"]))
                if item.result:
                    return
                context = deepcopy(item.input_data)
                operation, project_id, target_id = item.operation, item.project_id, item.target_id
                if fingerprint(context) != item.input_sha256:
                    raise CreativeError("创作输入完整性校验失败。")
                if context.get("prompt_version") != PROMPT_VERSION:
                    raise CreativeError("创作提示版本已更新，请发起新的操作，不要重试旧任务。")
            gateway = self.gateway or LocalCreativeGateway(
                model=context["model"],
                transport=OllamaLoopbackTransport(
                    base_url=str(self.settings.ollama_base_url),
                    timeout_seconds=self.settings.ollama_timeout_seconds,
                ),
            )
            if operation == "strategy":
                result, usage = self._stage(job, "strategy", context, Strategy, gateway)
                check_references(result.knowledge_member_ids, context["facts"])
                review, review_usage = self._stage(
                    job,
                    "strategy_review",
                    {**context, "draft": result.model_dump()},
                    Critique,
                    gateway,
                )
                self._publish(
                    job,
                    {
                        "strategy": result.model_dump(),
                        "review": review.model_dump(),
                        "passed": not any(i.severity == "blocking" for i in review.issues),
                        "provenance": [usage, review_usage],
                    },
                    lost,
                )
                return
            if operation == "critique":
                content = context["previous_script"]
                usages = []
            else:
                draft, usage = self._stage(job, "write", context, ScriptDraft, gateway)
                content = assemble_script(draft, context)
                usages = [usage]
                if operation == "revise" and content == context["previous_script"]:
                    raise CreativeError("模型未产生实际修改；未消耗已保存版本的修订预算。")
            with self.sessions() as session:
                run = self.scripts._require_run(session, project_id, target_id)
                self.scripts._validate_content(session, run, content)
            critique_context = {
                "as_of_utc": context["as_of_utc"],
                "brief": context["brief"],
                "facts": context["facts"],
                "trend": context["trend"],
                "draft": content,
                "mechanical_checks": readiness_report(content),
            }
            critique, usage = self._stage(job, "critique", critique_context, Critique, gateway)
            if any(
                i.section_index is not None and i.section_index >= len(content["sections"])
                for i in critique.issues
            ):
                raise CreativeError("评审结果指向不存在的分镜。")
            usages.append(usage)
            self._publish(
                job,
                {"content": content, "critique": critique.model_dump(), "provenance": usages},
                lost,
            )
        except CreativeError as error:
            raise TerminalJobError(str(error)) from None
        finally:
            stopped.set()
            thread.join(timeout=2)

    def _locked(self, session, job):
        record = session.get(WorkflowJobRecord, job.id, with_for_update=True)
        run = session.get(WorkflowRunRecord, job.run_id, with_for_update=True)
        if (
            not record
            or not run
            or record.status != "leased"
            or run.status != "running"
            or record.attempts != job.attempts
            or record.lease_owner != self.settings.worker_id
        ):
            raise CreativeError("任务已取消或执行权已变更，迟到结果不会覆盖当前内容。")
        item = session.scalar(
            select(CreativeOperationRecord)
            .where(CreativeOperationRecord.workflow_run_id == run.id)
            .with_for_update()
        )
        if not item or str(item.id) != job.payload.get("operation_id"):
            raise CreativeError("创作任务关联无效。")
        return record, run, item

    def _touch(self, job):
        with self.sessions.begin() as session:
            record, _, _ = self._locked(session, job)
            record.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=max(60, self.settings.job_lease_seconds)
            )

    def _stage(self, job, role, context, schema, gateway):
        with self.sessions.begin() as session:
            _, run, item = self._locked(session, job)
            cached = item.stages.get(role)
            if cached:
                return schema.model_validate(cached["output"]), cached["provenance"]
            run.checkpoint = "creative." + role
        try:
            output, provenance = gateway.call(role, context, schema)
        except CreativeCallError as error:
            with self.sessions.begin() as session:
                _, run, item = self._locked(session, job)
                session.add(
                    AuditEventRecord(
                        project_id=item.project_id,
                        run_id=run.id,
                        event_type="creative.stage_failed",
                        actor_type="model",
                        actor_id=role,
                        payload=error.provenance,
                    )
                )
            raise
        # Cache only validated stages; retrying an invalid output must call the model again.
        if role == "strategy":
            check_references(output.knowledge_member_ids, context["facts"])
        elif role == "write":
            assembled = assemble_script(output, context)
            if "issues" in context and assembled == context.get("previous_script"):
                raise CreativeError("模型未产生实际修改，请重试或手动编辑。")
        elif role == "strategy_review" and any(i.section_index is not None for i in output.issues):
            raise CreativeError("营销建议评审应指向整体建议，而不是不存在的分镜。")
        elif role == "critique" and any(
            i.section_index is not None and i.section_index >= len(context["draft"]["sections"])
            for i in output.issues
        ):
            raise CreativeError("评审结果指向不存在的分镜。")
        with self.sessions.begin() as session:
            _, run, item = self._locked(session, job)
            item.stages = {
                **item.stages,
                role: {"output": output.model_dump(), "provenance": provenance},
            }
            session.add(
                AuditEventRecord(
                    project_id=item.project_id,
                    run_id=run.id,
                    event_type="creative.stage_completed",
                    actor_type="model",
                    actor_id={
                        "strategy": "marketing.campaign_strategist",
                        "write": "creation.script_writer",
                        "critique": "creation.quality_critic",
                        "strategy_review": "creation.quality_critic",
                    }[role],
                    payload=provenance,
                )
            )
        return output, provenance

    def _publish(self, job, output, lost):
        if lost.is_set():
            raise CreativeError("后台任务心跳中断，请检查运行记录后重试。")
        with self.sessions.begin() as session:
            project_id = session.get(WorkflowRunRecord, job.run_id).project_id
            self.scripts._lock_project(session, project_id)
            _, workflow, item = self._locked(session, job)
            if item.result:
                return
            if item.operation == "strategy":
                item.result = output
            else:
                run = self.scripts._require_run(session, project_id, item.target_id)
                latest = self.scripts._latest_version(session, run.id)
                current_id = str(latest.id) if latest else None
                if current_id != item.input_data["base_version_id"]:
                    raise CreativeError("生成期间脚本已被修改；保留你的版本，请基于最新版本重试。")
                content = self.scripts._validate_content(session, run, output["content"])
                if item.operation == "critique":
                    version = latest
                else:
                    version = ScriptVersionRecord(
                        run_id=run.id,
                        version_number=latest.version_number + 1 if latest else 1,
                        parent_version_id=latest.id if latest else None,
                        origin="auto_revision" if item.operation == "revise" else "generated",
                        content=content,
                        content_sha256=self.scripts._digest(content),
                        generation_metadata={
                            "mode": "local_model",
                            "provenance": output["provenance"],
                            "operation_id": str(item.id),
                        },
                        created_by="creation.script_writer",
                        command_key="creative-" + str(item.id),
                    )
                    session.add(version)
                    session.flush()
                mechanical = readiness_report(content)
                critique = output["critique"]
                blockers = [i["message"] for i in critique["issues"] if i["severity"] == "blocking"]
                evaluation = ScriptEvaluationRecord(
                    run_id=run.id,
                    script_version_id=version.id,
                    score=mechanical["score"],
                    passed=not blockers and not mechanical["issues"],
                    dimensions=mechanical["dimensions"],
                    issues=mechanical["issues"] + blockers,
                    semantic_report={
                        **critique,
                        "mode": "local_model",
                        "provenance": output["provenance"][-1],
                        "word_count": mechanical["word_count"],
                        "words_per_minute": mechanical["words_per_minute"],
                    },
                    rule_version=RULE_VERSION,
                    command_key="creative-" + str(item.id),
                )
                session.add(evaluation)
                session.flush()
                item.result = {
                    "version_id": str(version.id),
                    "evaluation_id": str(evaluation.id),
                    "passed": evaluation.passed,
                    "provenance": output["provenance"],
                }
            workflow.checkpoint = "creative.saved"
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=workflow.id,
                    event_type="creative.result_saved",
                    actor_type="system",
                    actor_id="creative.harness",
                    payload={
                        "operation_id": str(item.id),
                        "operation": item.operation,
                        "human_approval_granted": False,
                    },
                )
            )
