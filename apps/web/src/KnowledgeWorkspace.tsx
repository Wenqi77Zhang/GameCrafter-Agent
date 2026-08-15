import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate, idempotencyKey, Language } from "./client";

export type WorkspaceRun = {
  id: string;
  workflow_kind: string;
  task_type: string;
  status: string;
  checkpoint: string;
  last_error_code: string | null;
  last_error_detail: string | null;
  created_at: string;
  finished_at: string | null;
};

export type WorkspaceAuditEvent = {
  id: string;
  event_type: string;
  actor_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

type Entity = {
  id: string;
  canonical_key: string;
  display_name: string;
  aliases: string[];
  status: "active" | "archived";
  revision_number: number;
  created_at: string;
  revised_at: string | null;
};

type SourceVersion = {
  id: string;
  source_id: string;
  version_number: number;
  is_latest: boolean;
  title: string;
  url: string;
  site: string;
  locale: string;
  region: string;
  source_type: string;
  source_status: string;
  fetched_at: string;
  normalized_text_sha256: string;
  normalized_text_available: boolean;
};

type Capability = {
  available: boolean;
  mode: "disabled" | "offline_replay";
  reason_code: string;
  reason: string;
};

type Evidence = {
  source_version_id: string;
  source_id: string;
  source_url: string;
  source_title: string;
  source_version_number: number;
  locale: string;
  region: string;
  fetched_at: string;
  ordinal: number;
  start_offset: number;
  end_offset: number;
  quote: string;
  quote_sha256: string;
};

type Claim = {
  id: string;
  subject_entity_id: string;
  extraction_run_id: string | null;
  predicate: string;
  value_kind: string;
  value: unknown;
  confidence: number;
  locale: string;
  region: string;
  status: "candidate_unreviewed";
  created_at: string;
  evidence: Evidence[];
};

type ConflictMember = {
  relation: "conflicting" | "possibly_coexisting";
  basis: string;
  claim: Claim & { normalized_value: string };
};

type ConflictGroup = {
  id: string;
  predicate: string;
  status: "open" | "resolved" | "dismissed";
  policy_version: string;
  member_count: number;
  distinct_value_count: number;
  members: ConflictMember[];
  subject: Entity | null;
};

type ReconcileResult = {
  policy_version: string;
  compared_scopes: number;
  created_groups: number;
  created_members: number;
  skipped_closed_groups: number;
};

type Props = {
  projectId: string;
  projectName: string;
  language: Language;
  runs: WorkspaceRun[];
  selectedRunId: string | null;
  events: WorkspaceAuditEvent[];
  refreshToken: number;
  onRunQueued: (run: WorkspaceRun) => void;
  onOpenRun: (runId: string) => void;
  onGoSources: () => void;
};

const text = {
  "zh-CN": {
    title: "知识提取工作台",
    subtitle: "选择游戏实体和一个不可变证据版本，运行严格零成本的候选知识提取。",
    entity: "游戏实体",
    createEntity: "新建游戏实体",
    gameName: "游戏名称",
    aliases: "英文名或其他别名",
    aliasHint: "多个别名用逗号或换行分隔",
    create: "创建实体",
    edit: "纠正名称",
    archive: "归档错误实体",
    saveCorrection: "保存纠正",
    reason: "修改原因",
    reasonPlaceholder: "例如：修正输入错误",
    cancel: "取消",
    noEntity: "尚无游戏实体。先创建一个实体；当前验证案例默认使用《异环》。",
    sourceVersion: "证据版本",
    latest: "最新",
    historical: "历史",
    noSource: "尚无可提取的证据版本。请先在来源工作区采集官方资料。",
    goSources: "去添加来源",
    capability: "提取能力",
    checking: "正在校验离线能力…",
    available: "离线回放可用",
    unavailable: "当前不可提取",
    start: "开始提取",
    submitting: "正在加入本地队列…",
    queued: "知识提取已进入本地队列。",
    unreviewed: "AI 候选 · 未经人工审核",
    progress: "实时进度",
    fullRun: "查看完整运行记录",
    stages: ["校验证据", "文本分块", "离线提取", "保存候选知识"],
    noRun: "选择实体和证据版本后开始提取。",
    candidates: "候选知识",
    noClaims: "当前实体尚无候选知识。提取完成后会在这里显示。",
    evidence: "精确证据",
    selectClaim: "选择一条候选知识查看原文证据。",
    confidence: "模型置信度",
    source: "来源",
    version: "版本",
    fetched: "采集时间",
    offsets: "文本位置",
    failed: "操作失败",
    loading: "正在加载知识工作区…",
    refresh: "刷新知识数据",
    conflicts: "事实冲突检查",
    conflictsHint: "仅比较同一实体、谓词和精确作用域；不会自动选择或批准任何值。",
    scanConflicts: "检测冲突",
    scanningConflicts: "正在确定性比较…",
    noConflicts: "尚未发现具有不同规范化值的可比较候选知识。",
    conflicting: "冲突",
    possiblyCoexisting: "可能共存",
    values: "个不同值",
    members: "条候选",
    policyBasis: "查看判定依据",
    conflictScanDone: "冲突检查完成",
    closedSkipped: "个人工已关闭组未被自动重开",
    conflictStatuses: { open: "待处理", resolved: "已解决", dismissed: "已忽略" },
    confirmArchive: "归档后不能恢复该实体，已有 Claim 仍保留。确认继续吗？",
    archiveReason: "用户确认该实体创建错误",
    capabilityReasons: {
      provider_disabled: "模型执行默认关闭；未配置精确离线回放。",
      fixture_missing: "未配置本地离线回放样例。",
      fixture_invalid: "本地离线回放样例未通过完整性校验。",
      target_mismatch: "该实体或证据版本与当前《异环》离线样例不匹配。",
      fixture_incomplete: "离线样例没有覆盖全部确定性文本分块。",
      target_invalid: "所选实体或证据版本不满足提取约束。",
      available: "该实体与证据版本拥有完整、精确、零 API 成本的本地回放。",
    },
  },
  en: {
    title: "Knowledge extraction workspace",
    subtitle: "Select a game entity and one immutable evidence version for strict zero-cost extraction.",
    entity: "Game entity",
    createEntity: "Create game entity",
    gameName: "Game name",
    aliases: "English name or aliases",
    aliasHint: "Separate aliases with commas or new lines",
    create: "Create entity",
    edit: "Correct label",
    archive: "Archive incorrect entity",
    saveCorrection: "Save correction",
    reason: "Reason for change",
    reasonPlaceholder: "For example: correct an input mistake",
    cancel: "Cancel",
    noEntity: "No game entity yet. Create one first; the current validation case defaults to NTE.",
    sourceVersion: "Evidence version",
    latest: "Latest",
    historical: "Historical",
    noSource: "No extractable evidence version yet. Capture official material in Sources first.",
    goSources: "Add a source",
    capability: "Extraction capability",
    checking: "Checking offline capability…",
    available: "Offline replay available",
    unavailable: "Extraction unavailable",
    start: "Start extraction",
    submitting: "Adding to the local queue…",
    queued: "Knowledge extraction was added to the local queue.",
    unreviewed: "AI candidate · not human reviewed",
    progress: "Live progress",
    fullRun: "View full run record",
    stages: ["Validate evidence", "Chunk text", "Offline extraction", "Save candidates"],
    noRun: "Select an entity and evidence version, then start extraction.",
    candidates: "Candidate knowledge",
    noClaims: "This entity has no candidate knowledge yet. Completed extraction appears here.",
    evidence: "Exact evidence",
    selectClaim: "Select a candidate to inspect its exact source evidence.",
    confidence: "Model confidence",
    source: "Source",
    version: "Version",
    fetched: "Captured",
    offsets: "Text offsets",
    failed: "Action failed",
    loading: "Loading Knowledge workspace…",
    refresh: "Refresh Knowledge data",
    conflicts: "Fact conflict check",
    conflictsHint: "Only identical subjects, predicates, and exact scopes are compared. No value is selected or approved automatically.",
    scanConflicts: "Check conflicts",
    scanningConflicts: "Comparing deterministically…",
    noConflicts: "No comparable candidate knowledge with differing normalized values was found.",
    conflicting: "Conflicting",
    possiblyCoexisting: "Possibly coexisting",
    values: "distinct values",
    members: "candidates",
    policyBasis: "View classification basis",
    conflictScanDone: "Conflict check completed",
    closedSkipped: "human-closed groups were not reopened",
    conflictStatuses: { open: "Open", resolved: "Resolved", dismissed: "Dismissed" },
    confirmArchive: "Archival is terminal. Existing Claims remain attached. Continue?",
    archiveReason: "User confirmed that this entity was created by mistake",
    capabilityReasons: {
      provider_disabled: "Model execution is disabled and no exact offline replay is configured.",
      fixture_missing: "No local offline replay fixture is configured.",
      fixture_invalid: "The local replay fixture failed integrity validation.",
      target_mismatch: "This entity or evidence version does not match the current NTE replay.",
      fixture_incomplete: "The replay does not cover every deterministic text chunk.",
      target_invalid: "The selected entity or evidence version violates extraction constraints.",
      available: "This exact entity and evidence version has a complete zero-API-cost local replay.",
    },
  },
} as const;

const predicateNames: Record<Language, Record<string, string>> = {
  "zh-CN": {
    "game.name": "游戏名称",
    "game.alias": "游戏别名",
    "game.developer": "开发商",
    "game.publisher": "发行商",
    "release.status": "发行状态",
    "release.date": "发行日期",
    "platform.availability": "平台",
    "business.model": "商业模式",
    "genre.primary": "主要类型",
    "world.setting": "世界观",
    "world.location": "世界地点",
    "gameplay.combat": "战斗玩法",
    "gameplay.exploration": "探索玩法",
    "gameplay.vehicle": "载具玩法",
    "feature.description": "特色描述",
    unclassified: "未分类",
  },
  en: {
    "game.name": "Game name",
    "game.alias": "Game alias",
    "game.developer": "Developer",
    "game.publisher": "Publisher",
    "release.status": "Release status",
    "release.date": "Release date",
    "platform.availability": "Platform",
    "business.model": "Business model",
    "genre.primary": "Primary genre",
    "world.setting": "World setting",
    "world.location": "World location",
    "gameplay.combat": "Combat",
    "gameplay.exploration": "Exploration",
    "gameplay.vehicle": "Vehicles",
    "feature.description": "Feature",
    unclassified: "Unclassified",
  },
};

function aliases(value: string): string[] {
  return [...new Set(value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean))];
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.join(" · ");
  if (value && typeof value === "object" && "entity_key" in value) {
    return String((value as { entity_key: unknown }).entity_key);
  }
  return JSON.stringify(value);
}

export function KnowledgeWorkspace({
  projectId,
  projectName,
  language,
  runs,
  selectedRunId,
  events,
  refreshToken,
  onRunQueued,
  onOpenRun,
  onGoSources,
}: Props) {
  const t = text[language];
  const [entities, setEntities] = useState<Entity[]>([]);
  const [versions, setVersions] = useState<SourceVersion[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [conflicts, setConflicts] = useState<ConflictGroup[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [selectedClaimId, setSelectedClaimId] = useState("");
  const [capability, setCapability] = useState<Capability | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showCorrect, setShowCorrect] = useState(false);
  const [entityName, setEntityName] = useState(projectName);
  const [entityAliases, setEntityAliases] = useState(
    projectName === "异环" ? "NTE: Neverness to Everness" : "",
  );
  const [correctionName, setCorrectionName] = useState("");
  const [correctionAliases, setCorrectionAliases] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const selectedEntity = entities.find((item) => item.id === selectedEntityId) ?? null;
  const selectedVersion = versions.find((item) => item.id === selectedVersionId) ?? null;
  const selectedClaim = claims.find((item) => item.id === selectedClaimId) ?? null;
  const activeRun = runs.find((item) => item.id === activeRunId) ?? null;
  const activeEvents = selectedRunId === activeRunId ? events : [];

  const loadCatalog = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [entityPayload, versionPayload] = await Promise.all([
        api<{ items: Entity[] }>(`/api/projects/${projectId}/knowledge-entities`),
        api<{ items: SourceVersion[] }>(`/api/projects/${projectId}/source-versions`),
      ]);
      setEntities(entityPayload.items);
      setVersions(versionPayload.items);
      setSelectedEntityId((current) =>
        entityPayload.items.some((item) => item.id === current)
          ? current
          : (entityPayload.items[0]?.id ?? ""),
      );
      setSelectedVersionId((current) => {
        if (versionPayload.items.some((item) => item.id === current)) return current;
        return (
          versionPayload.items.find(
            (item) => item.is_latest && item.normalized_text_available && item.source_status === "active",
          )?.id ??
          versionPayload.items.find(
            (item) => item.normalized_text_available && item.source_status === "active",
          )?.id ??
          ""
        );
      });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setLoading(false);
    }
  }, [projectId, t.failed]);

  const loadClaims = useCallback(async () => {
    if (!projectId || !selectedEntityId) {
      setClaims([]);
      return;
    }
    try {
      const payload = await api<{ items: Claim[] }>(
        `/api/projects/${projectId}/knowledge-claims?subject_entity_id=${selectedEntityId}`,
      );
      setClaims(payload.items);
      setSelectedClaimId((current) =>
        payload.items.some((item) => item.id === current) ? current : (payload.items[0]?.id ?? ""),
      );
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    }
  }, [projectId, selectedEntityId, t.failed]);

  const loadConflicts = useCallback(async () => {
    if (!projectId || !selectedEntityId) {
      setConflicts([]);
      return;
    }
    try {
      const payload = await api<{ items: ConflictGroup[] }>(
        `/api/projects/${projectId}/knowledge-conflicts?subject_entity_id=${selectedEntityId}`,
      );
      setConflicts(payload.items);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    }
  }, [projectId, selectedEntityId, t.failed]);

  useEffect(() => {
    setSelectedEntityId("");
    setSelectedVersionId("");
    setSelectedClaimId("");
    setActiveRunId(null);
    setShowCreate(false);
    setShowCorrect(false);
    setEntityName(projectName);
    setEntityAliases(projectName === "异环" ? "NTE: Neverness to Everness" : "");
    void loadCatalog();
  }, [projectId, projectName, refreshToken, loadCatalog]);

  useEffect(() => {
    void loadClaims();
    void loadConflicts();
  }, [loadClaims, loadConflicts]);

  useEffect(() => {
    if (!selectedEntity || !selectedVersionId) {
      setCapability(null);
      return;
    }
    let active = true;
    setCapabilityLoading(true);
    api<Capability>(
      `/api/projects/${projectId}/knowledge-extraction-capability?source_version_id=${selectedVersionId}&subject_entity_id=${selectedEntity.id}`,
    )
      .then((result) => {
        if (active) setCapability(result);
      })
      .catch((error: unknown) => {
        if (active) {
          setCapability({
            available: false,
            mode: "disabled",
            reason_code: "target_invalid",
            reason: error instanceof Error ? error.message : t.failed,
          });
        }
      })
      .finally(() => {
        if (active) setCapabilityLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, selectedEntity, selectedVersionId, t.failed]);

  useEffect(() => {
    if (activeRun?.status === "succeeded") {
      void loadClaims();
      void loadConflicts();
    }
  }, [activeRun?.status, loadClaims, loadConflicts]);

  useEffect(() => {
    if (!selectedEntity || showCorrect) return;
    setCorrectionName(selectedEntity.display_name);
    setCorrectionAliases(selectedEntity.aliases.join("\n"));
    setCorrectionReason("");
  }, [selectedEntity, showCorrect]);

  const groupedClaims = useMemo(() => {
    const groups = new Map<string, Claim[]>();
    for (const claim of claims) {
      groups.set(claim.predicate, [...(groups.get(claim.predicate) ?? []), claim]);
    }
    return [...groups.entries()];
  }, [claims]);

  const conflictByClaim = useMemo(() => {
    const index = new Map<string, ConflictMember>();
    for (const group of conflicts) {
      for (const member of group.members) index.set(member.claim.id, member);
    }
    return index;
  }, [conflicts]);

  const submitEntity = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("create");
    setMessage(null);
    try {
      const created = await api<Entity>(`/api/projects/${projectId}/knowledge-entities`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: entityName, aliases: aliases(entityAliases) }),
      });
      await loadCatalog();
      setSelectedEntityId(created.id);
      setShowCreate(false);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const correctEntity = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedEntity) return;
    setBusy("correct");
    setMessage(null);
    try {
      const corrected = await api<Entity>(
        `/api/projects/${projectId}/knowledge-entities/${selectedEntity.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: correctionName,
            aliases: aliases(correctionAliases),
            change_reason: correctionReason,
          }),
        },
      );
      await loadCatalog();
      setSelectedEntityId(corrected.id);
      setShowCorrect(false);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const archiveEntity = async () => {
    if (!selectedEntity || !globalThis.confirm(t.confirmArchive)) return;
    setBusy("archive");
    setMessage(null);
    try {
      await api(`/api/projects/${projectId}/knowledge-entities/${selectedEntity.id}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ change_reason: t.archiveReason }),
      });
      await loadCatalog();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const startExtraction = async () => {
    if (!selectedEntity || !selectedVersion || !capability?.available) return;
    setBusy("extract");
    setMessage(null);
    try {
      const run = await api<WorkspaceRun>(`/api/projects/${projectId}/knowledge-extractions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("knowledge-extract"),
        },
        body: JSON.stringify({
          source_version_id: selectedVersion.id,
          subject_entity_id: selectedEntity.id,
        }),
      });
      setActiveRunId(run.id);
      onRunQueued(run);
      setMessage({ kind: "ok", text: t.queued });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const reconcileConflicts = async () => {
    if (!selectedEntity) return;
    setBusy("conflicts");
    setMessage(null);
    try {
      const result = await api<ReconcileResult>(
        `/api/projects/${projectId}/knowledge-conflicts/reconcile`,
        { method: "POST" },
      );
      await loadConflicts();
      const closed = result.skipped_closed_groups
        ? ` · ${result.skipped_closed_groups} ${t.closedSkipped}`
        : "";
      setMessage({
        kind: "ok",
        text: `${t.conflictScanDone}: ${result.compared_scopes} · ${result.policy_version}${closed}`,
      });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const capabilityReason = capability
    ? (t.capabilityReasons[capability.reason_code as keyof typeof t.capabilityReasons] ?? capability.reason)
    : "";
  const leased = activeEvents.some((event) => event.event_type === "job.leased");
  const persisted = activeEvents.some(
    (event) => event.event_type === "knowledge.extraction_persisted",
  );
  const completed = activeRun?.status === "succeeded";
  const failed = activeRun?.status === "needs_attention";
  const stageState = (index: number) => {
    if (completed || persisted) return "done";
    if (failed) return index === 0 || leased ? "error" : "pending";
    if (index === 0) return leased ? "done" : activeRun ? "active" : "pending";
    if (index < 3 && leased) return "active";
    return "pending";
  };

  if (loading) return <div className="empty-state knowledge-loading">{t.loading}</div>;

  return (
    <section className="knowledge-workspace" aria-labelledby="knowledge-title">
      <div className="knowledge-intro">
        <div>
          <p className="eyebrow">Knowledge · C3</p>
          <h2 id="knowledge-title">{t.title}</h2>
          <p>{t.subtitle}</p>
        </div>
        <button className="ghost-button" type="button" onClick={() => void loadCatalog()}>
          {t.refresh}
        </button>
      </div>

      {message && <div className={`notice notice--${message.kind}`} role="status">{message.text}</div>}

      <div className="knowledge-setup-grid">
        <section className="panel knowledge-setup-card">
          <div className="setup-label"><span>01</span><strong>{t.entity}</strong></div>
          {entities.length === 0 ? (
            <div className="knowledge-empty-compact"><p>{t.noEntity}</p></div>
          ) : (
            <>
              <select
                aria-label={t.entity}
                value={selectedEntityId}
                onChange={(event) => setSelectedEntityId(event.target.value)}
              >
                {entities.map((entity) => (
                  <option key={entity.id} value={entity.id}>
                    {entity.display_name} · r{entity.revision_number}
                  </option>
                ))}
              </select>
              {selectedEntity && (
                <div className="entity-summary">
                  <code>{selectedEntity.canonical_key}</code>
                  <p>{selectedEntity.aliases.join(" · ") || "—"}</p>
                  <div className="inline-actions">
                    <button type="button" onClick={() => setShowCorrect((current) => !current)}>
                      {t.edit}
                    </button>
                    <button type="button" disabled={busy !== null} onClick={() => void archiveEntity()}>
                      {t.archive}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
          <button className="secondary-button setup-action" type="button" onClick={() => setShowCreate((current) => !current)}>
            {t.createEntity}
          </button>
          {showCreate && (
            <form className="compact-form" onSubmit={submitEntity}>
              <label><span>{t.gameName}</span><input required maxLength={300} value={entityName} onChange={(event) => setEntityName(event.target.value)} /></label>
              <label><span>{t.aliases}</span><textarea maxLength={2000} value={entityAliases} onChange={(event) => setEntityAliases(event.target.value)} /><small>{t.aliasHint}</small></label>
              <div className="inline-actions"><button className="primary-button" disabled={busy !== null} type="submit">{busy === "create" ? t.submitting : t.create}</button><button type="button" onClick={() => setShowCreate(false)}>{t.cancel}</button></div>
            </form>
          )}
          {showCorrect && selectedEntity && (
            <form className="compact-form" onSubmit={correctEntity}>
              <label><span>{t.gameName}</span><input required maxLength={300} value={correctionName} onChange={(event) => setCorrectionName(event.target.value)} /></label>
              <label><span>{t.aliases}</span><textarea maxLength={2000} value={correctionAliases} onChange={(event) => setCorrectionAliases(event.target.value)} /></label>
              <label><span>{t.reason}</span><input required maxLength={500} placeholder={t.reasonPlaceholder} value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} /></label>
              <div className="inline-actions"><button className="primary-button" disabled={busy !== null} type="submit">{busy === "correct" ? t.submitting : t.saveCorrection}</button><button type="button" onClick={() => setShowCorrect(false)}>{t.cancel}</button></div>
            </form>
          )}
        </section>

        <section className="panel knowledge-setup-card">
          <div className="setup-label"><span>02</span><strong>{t.sourceVersion}</strong></div>
          {versions.length === 0 ? (
            <div className="knowledge-empty-compact"><p>{t.noSource}</p><button className="secondary-button" type="button" onClick={onGoSources}>{t.goSources}</button></div>
          ) : (
            <>
              <select aria-label={t.sourceVersion} value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>
                {versions.map((version) => (
                  <option key={version.id} value={version.id} disabled={!version.normalized_text_available || version.source_status !== "active"}>
                    {version.is_latest ? t.latest : t.historical} · v{version.version_number} · {version.locale} · {version.title}
                  </option>
                ))}
              </select>
              {selectedVersion && (
                <div className="version-summary"><div className="card-meta"><span>{selectedVersion.site}</span><span>{selectedVersion.locale}</span><span>{selectedVersion.region}</span><span>v{selectedVersion.version_number}</span></div><a href={selectedVersion.url} target="_blank" rel="noreferrer">{selectedVersion.url}</a><small>{formatDate(selectedVersion.fetched_at, language)} · {selectedVersion.normalized_text_sha256.slice(0, 12)}</small></div>
              )}
            </>
          )}
        </section>

        <section className="panel knowledge-setup-card capability-card">
          <div className="setup-label"><span>03</span><strong>{t.capability}</strong></div>
          {capabilityLoading ? <p>{t.checking}</p> : capability ? (
            <div className={capability.available ? "capability capability--available" : "capability capability--blocked"}>
              <strong>{capability.available ? t.available : t.unavailable}</strong>
              <p>{capabilityReason}</p>
              <code>{capability.mode} · {capability.reason_code}</code>
            </div>
          ) : <p>{t.noRun}</p>}
          <button className="primary-button" type="button" disabled={busy !== null || !capability?.available} onClick={() => void startExtraction()}>
            {busy === "extract" ? t.submitting : t.start}
          </button>
        </section>
      </div>

      <section className="panel extraction-progress" aria-live="polite">
        <div className="list-heading"><h2>{t.progress}</h2>{activeRun && <span>{activeRun.status}</span>}</div>
        {!activeRunId ? <div className="empty-state">{t.noRun}</div> : (
          <>
            <ol className="stage-list">
              {t.stages.map((stage, index) => {
                const state = stageState(index);
                return <li className={`stage stage--${state}`} key={stage} aria-current={state === "active" ? "step" : undefined}><span>{state === "done" ? "✓" : index + 1}</span><strong>{stage}</strong></li>;
              })}
            </ol>
            {activeRun?.last_error_detail && <div className="error-detail"><strong>{activeRun.last_error_code}</strong><p>{activeRun.last_error_detail}</p></div>}
            <button className="ghost-button" type="button" onClick={() => onOpenRun(activeRunId)}>{t.fullRun}</button>
          </>
        )}
      </section>

      <section className="panel conflict-browser" aria-labelledby="conflict-title">
        <div className="conflict-heading">
          <div>
            <h2 id="conflict-title">{t.conflicts}</h2>
            <p>{t.conflictsHint}</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            disabled={busy !== null || !selectedEntity || claims.length === 0}
            onClick={() => void reconcileConflicts()}
          >
            {busy === "conflicts" ? t.scanningConflicts : t.scanConflicts}
          </button>
        </div>
        {conflicts.length === 0 ? (
          <div className="empty-state">{t.noConflicts}</div>
        ) : (
          <div className="conflict-grid">
            {conflicts.map((group) => {
              const relation = group.members[0]?.relation ?? "possibly_coexisting";
              return (
                <article className={`conflict-card conflict-card--${relation}`} key={group.id}>
                  <div className="conflict-card-title">
                    <div>
                      <span className={`relation-badge relation-badge--${relation}`}>
                        {relation === "conflicting" ? t.conflicting : t.possiblyCoexisting}
                      </span>
                      <h3>{predicateNames[language][group.predicate] ?? group.predicate}</h3>
                    </div>
                    <span>{t.conflictStatuses[group.status]}</span>
                  </div>
                  <p className="conflict-counts">
                    {group.distinct_value_count} {t.values} · {group.member_count} {t.members}
                  </p>
                  <div className="conflict-values">
                    {group.members.map((member) => (
                      <button
                        type="button"
                        key={member.claim.id}
                        onClick={() => setSelectedClaimId(member.claim.id)}
                      >
                        <strong>{displayValue(member.claim.value)}</strong>
                        <span>{member.claim.evidence[0]?.source_title ?? "—"}</span>
                      </button>
                    ))}
                  </div>
                  <details>
                    <summary>{t.policyBasis} · {group.policy_version}</summary>
                    <p>{group.members[0]?.basis}</p>
                  </details>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="claim-evidence-layout">
        <section className="panel claim-browser">
          <div className="list-heading"><h2>{t.candidates}</h2><span>{claims.length}</span></div>
          <div className="candidate-warning">{t.unreviewed}</div>
          {claims.length === 0 ? <div className="empty-state">{t.noClaims}</div> : groupedClaims.map(([predicate, items]) => (
            <div className="claim-group" key={predicate}>
              <h3>{predicateNames[language][predicate] ?? predicate}</h3>
              {items.map((claim) => (
                <button className={selectedClaimId === claim.id ? "claim-card active" : "claim-card"} type="button" key={claim.id} aria-pressed={selectedClaimId === claim.id} onClick={() => setSelectedClaimId(claim.id)}>
                  <strong>{displayValue(claim.value)}</strong>
                  <span>{Math.round(claim.confidence * 100)}% · {claim.locale} · {claim.region}</span>
                  {conflictByClaim.has(claim.id) && (
                    <em className={`claim-relation claim-relation--${conflictByClaim.get(claim.id)?.relation}`}>
                      {conflictByClaim.get(claim.id)?.relation === "conflicting" ? t.conflicting : t.possiblyCoexisting}
                    </em>
                  )}
                </button>
              ))}
            </div>
          ))}
        </section>

        <aside className="panel evidence-panel" aria-labelledby="evidence-title">
          <div className="list-heading"><h2 id="evidence-title">{t.evidence}</h2>{selectedClaim && <span>{t.unreviewed}</span>}</div>
          {!selectedClaim ? <div className="empty-state">{t.selectClaim}</div> : (
            <>
              <div className="selected-claim"><span>{predicateNames[language][selectedClaim.predicate] ?? selectedClaim.predicate}</span><strong>{displayValue(selectedClaim.value)}</strong><small>{t.confidence}: {Math.round(selectedClaim.confidence * 100)}%</small></div>
              <div className="evidence-list">
                {selectedClaim.evidence.map((evidence) => (
                  <article key={`${evidence.source_version_id}-${evidence.ordinal}`}>
                    <blockquote>{evidence.quote}</blockquote>
                    <dl><div><dt>{t.source}</dt><dd><a href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.source_title}</a></dd></div><div><dt>{t.version}</dt><dd>v{evidence.source_version_number} · {evidence.locale} · {evidence.region}</dd></div><div><dt>{t.fetched}</dt><dd>{formatDate(evidence.fetched_at, language)}</dd></div><div><dt>{t.offsets}</dt><dd>{evidence.start_offset}–{evidence.end_offset}</dd></div></dl>
                  </article>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}
