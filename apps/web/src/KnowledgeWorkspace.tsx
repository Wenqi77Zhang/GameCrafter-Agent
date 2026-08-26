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
  mode: "disabled" | "offline_replay" | "local_ollama";
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

type ReviewDecision = "approve" | "approve_with_edit" | "reject" | "defer";

type ClaimReview = {
  id: string;
  decision: ReviewDecision;
  approved_value_kind: string | null;
  approved_value: unknown | null;
  reason: string;
  reviewer_id: string;
  created_at: string;
};

type AgentClaimReview = {
  decision: "agent_approved" | "agent_rejected" | "needs_human";
  suggested_predicate: string | null;
  priority: number;
  reason_code: string;
  rationale: string;
  risk_codes: string[];
};

type AgentReviewSummary = {
  run_id: string;
  extraction_run_id: string;
  agent: { key: string; version: string; provider: string; model: string };
  counts: { reviewed: number; agent_approved: number; agent_rejected: number; needs_human: number };
  token_usage: { input: number; output: number; total: number };
  decisions: Array<AgentClaimReview & { claim_id: string }>;
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
  status:
    | "candidate_unreviewed"
    | "human_approved"
    | "human_approved_with_edit"
    | "human_rejected"
    | "human_deferred";
  created_at: string;
  evidence: Evidence[];
  reviews: ClaimReview[];
  latest_review: ClaimReview | null;
  agent_review: AgentClaimReview | null;
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
  resolution_summary: string | null;
};

type ReconcileResult = {
  policy_version: string;
  compared_scopes: number;
  created_groups: number;
  created_members: number;
  skipped_closed_groups: number;
};

type SnapshotBlocker = {
  code: string;
  message: string;
  count?: number;
};

type SnapshotReadiness = {
  publishable: boolean;
  schema_version: string;
  content_sha256: string | null;
  stats: {
    claim_count: number;
    approved_count: number;
    rejected_count: number;
    deferred_count: number;
    unreviewed_count: number;
    open_conflict_count: number;
  };
  blockers: SnapshotBlocker[];
  next_version_number: number;
  latest_snapshot_id: string | null;
};

type SnapshotMember = {
  claim_id: string;
  review_id: string;
  subject: {
    entity_id: string;
    entity_revision_id: string | null;
    revision_number: number;
    canonical_key: string;
    display_name: string;
  };
  predicate: string;
  value_kind: string;
  value: unknown;
  review: ClaimReview;
  evidence: Evidence[];
};

type KnowledgeSnapshot = {
  id: string;
  version_number: number;
  is_latest: boolean;
  schema_version: string;
  content_sha256: string;
  member_count: number;
  members: SnapshotMember[];
  published_by: string;
  notes: string | null;
  published_at: string;
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
    localAvailable: "零 API 费用的本地模型可用",
    unavailable: "当前不可提取",
    start: "开始提取",
    submitting: "正在加入本地队列…",
    queued: "知识提取已进入本地队列。",
    unreviewed: "仅显示当前提取批次；审核 Agent 拒绝的低价值项默认折叠。",
    agentReviewTitle: "AI 知识预审",
    agentReviewHint: "独立审核 Agent 会核对证据、纠正错误分类并将知识包限制在 15 条以内；它不能替你做最终批准。",
    startAgentReview: "让审核 Agent 检查",
    reviewing: "审核 Agent 正在检查…",
    confirmAgentPack: "批量确认审核建议",
    confirmingAgentPack: "正在记录人工确认…",
    reviewQueued: "知识审核已进入本地队列。",
    packConfirmed: "已确认 Agent 明确建议；有疑问的条目仍保留给你单独判断。",
    approvedByAgent: "建议保留",
    rejectedByAgent: "建议移除",
    needsHuman: "需要你判断",
    showRejected: "显示被筛除项",
    hideRejected: "隐藏被筛除项",
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
    reviewTitle: "人工审核",
    reviewHint: "先核对上方原文证据，再追加一条不可篡改的人工决定。新决定不会删除历史。",
    approve: "批准原值",
    approveWithEdit: "修改后批准",
    reject: "拒绝",
    defer: "稍后决定",
    reviewReason: "决定理由",
    reviewReasonPlaceholder: "说明你依据哪条证据作出决定",
    editedValue: "批准后的值",
    editedValueHint: "列表每行一项；布尔值填写 true 或 false。",
    submitReview: "记录人工决定",
    savingReview: "正在保存决定…",
    reviewSaved: "人工决定已追加，原候选与历史记录均未修改。",
    reviewHistory: "审核历史",
    noReview: "尚无人工决定",
    latestDecision: "当前人工状态",
    closeConflict: "关闭冲突组",
    resolveConflict: "按审核结果解决",
    dismissConflict: "忽略该组",
    closureReason: "关闭理由",
    closureReasonPlaceholder: "说明为何可以解决或忽略该冲突组",
    submitClosure: "确认关闭",
    closingConflict: "正在校验并关闭…",
    closureSaved: "冲突组已由人工关闭。",
    closureRule: "解决要求每条候选都有最终审核；单值冲突只能保留一个批准值。",
    snapshotTitle: "发布知识快照",
    snapshotHint: "把项目中全部当前批准值原子冻结为一个不可变版本，供后续营销流程使用。",
    snapshotReady: "可以发布",
    snapshotBlocked: "尚不能发布",
    nextSnapshot: "下一版本",
    approvedFacts: "批准值",
    finalReviews: "已终审",
    openConflicts: "开放冲突",
    snapshotNotes: "版本备注（可选）",
    snapshotNotesPlaceholder: "例如：《异环》官网英文资料首轮人工确认",
    publishSnapshot: "发布不可变快照",
    publishingSnapshot: "正在原子发布…",
    snapshotPublished: "知识快照已发布，后续流程将引用这个不可变版本。",
    snapshotHistory: "快照版本历史",
    synthesis: "多来源联合视图",
    synthesisHint: "只对已批准快照做确定性汇总，不生成新事实。",
    distinctSources: "独立来源",
    corroborated: "多来源相互印证",
    singleSource: "仅单一来源",
    noSnapshots: "尚未发布知识快照。",
    latestSnapshot: "最新",
    snapshotFacts: "条事实",
    snapshotBlockers: {
      no_claims: "尚无候选知识。",
      unreviewed_claims: "仍有候选尚未人工审核。",
      deferred_claims: "仍有候选被标记为稍后决定。",
      no_approved_claims: "至少需要一个当前批准值。",
      open_conflicts: "所有开放冲突都必须先解决或明确忽略。",
      approved_archived_entities: "已批准值关联了归档实体。",
      unreconciled_conflicts: "存在尚未运行冲突检查的不同值。",
      inconsistent_closed_conflict: "关闭后的单值冲突又出现多个当前批准值。",
      inconsistent_approved_values: "人工修改导致单值谓词保留了多个批准值。",
      incomplete_lineage: "批准值的证据谱系不完整。",
    },
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
      ollama_available: "已配置本地 Ollama 模型；候选仍须经过精确证据校验和人工审核。",
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
    localAvailable: "Zero-API-cost local model available",
    unavailable: "Extraction unavailable",
    start: "Start extraction",
    submitting: "Adding to the local queue…",
    queued: "Knowledge extraction was added to the local queue.",
    unreviewed: "Only the current extraction batch is shown; low-value agent rejections are collapsed.",
    agentReviewTitle: "AI knowledge pre-review",
    agentReviewHint: "An independent local reviewer verifies evidence, flags bad taxonomy, and limits the pack to 15 facts. It cannot grant final approval.",
    startAgentReview: "Run reviewer Agent",
    reviewing: "Reviewer Agent is checking…",
    confirmAgentPack: "Confirm reviewer suggestions",
    confirmingAgentPack: "Recording human confirmation…",
    reviewQueued: "Knowledge review was added to the local queue.",
    packConfirmed: "Clear Agent suggestions were confirmed; ambiguous items remain for individual review.",
    approvedByAgent: "Keep",
    rejectedByAgent: "Remove",
    needsHuman: "Needs your decision",
    showRejected: "Show filtered items",
    hideRejected: "Hide filtered items",
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
    reviewTitle: "Human review",
    reviewHint: "Verify the exact evidence above, then append an immutable human decision. New decisions never erase history.",
    approve: "Approve original",
    approveWithEdit: "Edit and approve",
    reject: "Reject",
    defer: "Decide later",
    reviewReason: "Decision reason",
    reviewReasonPlaceholder: "Explain which evidence supports this decision",
    editedValue: "Approved value",
    editedValueHint: "Use one list item per line; enter true or false for booleans.",
    submitReview: "Record human decision",
    savingReview: "Saving decision…",
    reviewSaved: "The human decision was appended without changing the candidate or prior history.",
    reviewHistory: "Review history",
    noReview: "No human decision yet",
    latestDecision: "Current human state",
    closeConflict: "Close conflict group",
    resolveConflict: "Resolve from reviews",
    dismissConflict: "Dismiss group",
    closureReason: "Closure reason",
    closureReasonPlaceholder: "Explain why this group can be resolved or dismissed",
    submitClosure: "Confirm closure",
    closingConflict: "Validating and closing…",
    closureSaved: "The conflict group was closed by a human.",
    closureRule: "Resolution requires a final review for every candidate; a single-valued conflict may retain only one approved value.",
    snapshotTitle: "Publish knowledge snapshot",
    snapshotHint: "Atomically freeze every currently approved project value into one immutable version for downstream marketing workflows.",
    snapshotReady: "Ready to publish",
    snapshotBlocked: "Not ready to publish",
    nextSnapshot: "Next version",
    approvedFacts: "Approved values",
    finalReviews: "Final reviews",
    openConflicts: "Open conflicts",
    snapshotNotes: "Version notes (optional)",
    snapshotNotesPlaceholder: "For example: first human-reviewed NTE English official-site baseline",
    publishSnapshot: "Publish immutable snapshot",
    publishingSnapshot: "Publishing atomically…",
    snapshotPublished: "The knowledge snapshot was published; downstream workflows will reference this immutable version.",
    snapshotHistory: "Snapshot version history",
    synthesis: "Multi-source synthesis",
    synthesisHint: "Deterministic summary of the approved snapshot only; it creates no new facts.",
    distinctSources: "Distinct sources",
    corroborated: "Multi-source corroborated",
    singleSource: "Single-source only",
    noSnapshots: "No knowledge snapshot has been published yet.",
    latestSnapshot: "Latest",
    snapshotFacts: "facts",
    snapshotBlockers: {
      no_claims: "No candidate knowledge exists.",
      unreviewed_claims: "Some candidates still lack a human review.",
      deferred_claims: "Some candidates are still deferred.",
      no_approved_claims: "At least one current approved value is required.",
      open_conflicts: "Resolve or explicitly dismiss every open conflict first.",
      approved_archived_entities: "An approved value belongs to an archived entity.",
      unreconciled_conflicts: "Differing values have not passed conflict reconciliation.",
      inconsistent_closed_conflict: "A closed single-valued conflict now retains multiple approved values.",
      inconsistent_approved_values: "Human edits retain multiple approved values for a single-valued predicate.",
      incomplete_lineage: "Approved evidence lineage is incomplete.",
    },
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
      ollama_available: "A local Ollama model is configured; candidates still require exact evidence validation and human review.",
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

function snapshotSynthesis(snapshot: KnowledgeSnapshot) {
  const sources = new Set<string>();
  const groups = new Map<string, Set<string>>();
  for (const member of snapshot.members) {
    const key = `${member.subject.entity_id}\u0000${member.predicate}\u0000${JSON.stringify(member.value)}`;
    const group = groups.get(key) ?? new Set<string>();
    for (const evidence of member.evidence) {
      sources.add(evidence.source_id);
      group.add(evidence.source_id);
    }
    groups.set(key, group);
  }
  return {
    sourceCount: sources.size,
    corroborated: [...groups.values()].filter((items) => items.size >= 2).length,
    singleSource: [...groups.values()].filter((items) => items.size === 1).length,
    ruleVersion: "multi-source-synthesis-v1",
  };
}

function parseEditedValue(kind: string, input: string): unknown {
  const value = input.trim();
  if (kind === "number") {
    const parsed = Number(value);
    if (!value || !Number.isFinite(parsed)) throw new Error("approved number is invalid");
    return parsed;
  }
  if (kind === "boolean") {
    if (value === "true") return true;
    if (value === "false") return false;
    throw new Error("approved boolean must be true or false");
  }
  if (kind === "string_list") {
    const items = value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
    if (items.length === 0) throw new Error("approved list must not be empty");
    return items;
  }
  if (kind === "entity_ref") {
    if (!value) throw new Error("approved entity key must not be empty");
    return { entity_key: value };
  }
  if (!value) throw new Error("approved value must not be empty");
  return value;
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
  const [extractionRunId, setExtractionRunId] = useState<string | null>(null);
  const [agentReview, setAgentReview] = useState<AgentReviewSummary | null>(null);
  const [showAgentRejected, setShowAgentRejected] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<ReviewDecision>("approve");
  const [reviewReason, setReviewReason] = useState("");
  const [reviewEditedValue, setReviewEditedValue] = useState("");
  const [closureGroupId, setClosureGroupId] = useState<string | null>(null);
  const [closureOutcome, setClosureOutcome] = useState<"resolved" | "dismissed">("resolved");
  const [closureReason, setClosureReason] = useState("");
  const [snapshotReadiness, setSnapshotReadiness] = useState<SnapshotReadiness | null>(null);
  const [snapshots, setSnapshots] = useState<KnowledgeSnapshot[]>([]);
  const [snapshotNotes, setSnapshotNotes] = useState("");

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
      const query = extractionRunId
        ? `subject_entity_id=${selectedEntityId}&extraction_run_id=${extractionRunId}`
        : `subject_entity_id=${selectedEntityId}`;
      const payload = await api<{ items: Claim[] }>(
        `/api/projects/${projectId}/knowledge-claims?${query}`,
      );
      setClaims(payload.items);
      setSelectedClaimId((current) =>
        payload.items.some((item) => item.id === current) ? current : (payload.items[0]?.id ?? ""),
      );
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    }
  }, [extractionRunId, projectId, selectedEntityId, t.failed]);

  const loadAgentReview = useCallback(async () => {
    if (!projectId || !extractionRunId) {
      setAgentReview(null);
      return;
    }
    try {
      setAgentReview(await api<AgentReviewSummary>(
        `/api/projects/${projectId}/knowledge-agent-reviews?extraction_run_id=${extractionRunId}`,
      ));
    } catch {
      setAgentReview(null);
    }
  }, [extractionRunId, projectId]);

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

  const loadPublication = useCallback(async () => {
    if (!projectId) {
      setSnapshotReadiness(null);
      setSnapshots([]);
      return;
    }
    try {
      const [readiness, history] = await Promise.all([
        api<SnapshotReadiness>(`/api/projects/${projectId}/knowledge-snapshot-readiness`),
        api<{ items: KnowledgeSnapshot[] }>(`/api/projects/${projectId}/knowledge-snapshots`),
      ]);
      setSnapshotReadiness(readiness);
      setSnapshots(history.items);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    }
  }, [projectId, t.failed]);

  useEffect(() => {
    setSelectedEntityId("");
    setSelectedVersionId("");
    setSelectedClaimId("");
    setActiveRunId(null);
    setExtractionRunId(null);
    setAgentReview(null);
    setShowCreate(false);
    setShowCorrect(false);
    setEntityName(projectName);
    setEntityAliases(projectName === "异环" ? "NTE: Neverness to Everness" : "");
    void loadCatalog();
  }, [projectId, projectName, refreshToken, loadCatalog]);

  useEffect(() => {
    const latest = [...runs].reverse().find(
      (run) => run.task_type === "knowledge.extract" && run.status === "succeeded",
    );
    if (latest && !extractionRunId) setExtractionRunId(latest.id);
  }, [extractionRunId, runs]);

  useEffect(() => {
    void loadClaims();
    void loadAgentReview();
    void loadConflicts();
    void loadPublication();
  }, [loadAgentReview, loadClaims, loadConflicts, loadPublication]);

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
      if (activeRun.task_type === "knowledge.extract") setExtractionRunId(activeRun.id);
      void loadClaims();
      void loadAgentReview();
      void loadConflicts();
      void loadPublication();
    }
  }, [activeRun, loadAgentReview, loadClaims, loadConflicts, loadPublication]);

  useEffect(() => {
    if (!selectedEntity || showCorrect) return;
    setCorrectionName(selectedEntity.display_name);
    setCorrectionAliases(selectedEntity.aliases.join("\n"));
    setCorrectionReason("");
  }, [selectedEntity, showCorrect]);

  useEffect(() => {
    setReviewDecision("approve");
    setReviewReason("");
    setReviewEditedValue(selectedClaim ? displayValue(selectedClaim.value) : "");
  }, [selectedClaimId]);

  const groupedClaims = useMemo(() => {
    const groups = new Map<string, Claim[]>();
    for (const claim of claims) {
      if (!showAgentRejected && claim.agent_review?.decision === "agent_rejected") continue;
      groups.set(claim.predicate, [...(groups.get(claim.predicate) ?? []), claim]);
    }
    return [...groups.entries()];
  }, [claims, showAgentRejected]);

  const conflictByClaim = useMemo(() => {
    const index = new Map<string, ConflictMember>();
    for (const group of conflicts) {
      for (const member of group.members) index.set(member.claim.id, member);
    }
    return index;
  }, [conflicts]);

  const reviewLabel = (decision: ReviewDecision | null): string => {
    if (!decision) return t.noReview;
    return {
      approve: t.approve,
      approve_with_edit: t.approveWithEdit,
      reject: t.reject,
      defer: t.defer,
    }[decision];
  };

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
      setExtractionRunId(run.id);
      setAgentReview(null);
      onRunQueued(run);
      setMessage({ kind: "ok", text: t.queued });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const startAgentReview = async () => {
    if (!extractionRunId || claims.length === 0) return;
    setBusy("agent-review");
    setMessage(null);
    try {
      const run = await api<WorkspaceRun>(
        `/api/projects/${projectId}/knowledge-agent-reviews`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("knowledge-agent-review"),
          },
          body: JSON.stringify({ extraction_run_id: extractionRunId }),
        },
      );
      setActiveRunId(run.id);
      onRunQueued(run);
      setMessage({ kind: "ok", text: t.reviewQueued });
      if (run.status === "succeeded") await loadAgentReview();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const confirmAgentPack = async () => {
    if (!extractionRunId || !agentReview) return;
    setBusy("agent-confirm");
    setMessage(null);
    try {
      await api(`/api/projects/${projectId}/knowledge-agent-reviews/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("confirm-agent-pack"),
        },
        body: JSON.stringify({ extraction_run_id: extractionRunId }),
      });
      await Promise.all([loadClaims(), loadConflicts(), loadPublication()]);
      setMessage({ kind: "ok", text: t.packConfirmed });
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
      await Promise.all([loadConflicts(), loadPublication()]);
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

  const submitReview = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedClaim) return;
    setBusy("review");
    setMessage(null);
    try {
      const approvedValue = reviewDecision === "approve_with_edit"
        ? parseEditedValue(selectedClaim.value_kind, reviewEditedValue)
        : null;
      await api(`/api/projects/${projectId}/knowledge-claims/${selectedClaim.id}/reviews`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("claim-review"),
        },
        body: JSON.stringify({
          decision: reviewDecision,
          approved_value: approvedValue,
          reason: reviewReason,
        }),
      });
      await Promise.all([loadClaims(), loadConflicts(), loadPublication()]);
      setReviewReason("");
      setMessage({ kind: "ok", text: t.reviewSaved });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const closeConflict = async (event: FormEvent) => {
    event.preventDefault();
    if (!closureGroupId) return;
    setBusy("closure");
    setMessage(null);
    try {
      await api(
        `/api/projects/${projectId}/knowledge-conflicts/${closureGroupId}/closure`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("conflict-closure"),
          },
          body: JSON.stringify({ outcome: closureOutcome, reason: closureReason }),
        },
      );
      await Promise.all([loadConflicts(), loadPublication()]);
      setClosureGroupId(null);
      setClosureReason("");
      setMessage({ kind: "ok", text: t.closureSaved });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const publishSnapshot = async (event: FormEvent) => {
    event.preventDefault();
    if (!snapshotReadiness?.publishable) return;
    setBusy("snapshot");
    setMessage(null);
    try {
      await api(`/api/projects/${projectId}/knowledge-snapshots`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("knowledge-snapshot"),
        },
        body: JSON.stringify({ notes: snapshotNotes.trim() || null }),
      });
      await loadPublication();
      setSnapshotNotes("");
      setMessage({ kind: "ok", text: t.snapshotPublished });
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
          <p className="eyebrow">Knowledge · C5</p>
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
              <strong>{capability.available ? (capability.mode === "local_ollama" ? t.localAvailable : t.available) : t.unavailable}</strong>
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

      <section className="panel agent-review-panel" aria-labelledby="agent-review-title">
        <div className="conflict-heading">
          <div>
            <h2 id="agent-review-title">{t.agentReviewTitle}</h2>
            <p>{t.agentReviewHint}</p>
          </div>
          {!agentReview ? (
            <button
              className="primary-button"
              type="button"
              disabled={busy !== null || claims.length === 0 || !extractionRunId}
              onClick={() => void startAgentReview()}
            >
              {busy === "agent-review" ? t.reviewing : t.startAgentReview}
            </button>
          ) : (
            <button
              className="primary-button"
              type="button"
              disabled={busy !== null}
              onClick={() => void confirmAgentPack()}
            >
              {busy === "agent-confirm" ? t.confirmingAgentPack : t.confirmAgentPack}
            </button>
          )}
        </div>
        {agentReview && (
          <>
            <div className="snapshot-metrics">
              <div><span>{t.approvedByAgent}</span><strong>{agentReview.counts.agent_approved}</strong></div>
              <div><span>{t.rejectedByAgent}</span><strong>{agentReview.counts.agent_rejected}</strong></div>
              <div><span>{t.needsHuman}</span><strong>{agentReview.counts.needs_human}</strong></div>
              <div><span>Agent</span><strong>{agentReview.agent.version}</strong></div>
            </div>
            <code>{agentReview.agent.model} · {agentReview.token_usage.total} local tokens</code>
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
                        <em className={`review-state review-state--${member.claim.latest_review?.decision ?? "unreviewed"}`}>
                          {reviewLabel(member.claim.latest_review?.decision ?? null)}
                        </em>
                      </button>
                    ))}
                  </div>
                  <details>
                    <summary>{t.policyBasis} · {group.policy_version}</summary>
                    <p>{group.members[0]?.basis}</p>
                  </details>
                  {group.status === "open" ? (
                    <>
                      <button
                        className="ghost-button conflict-close-toggle"
                        type="button"
                        onClick={() => {
                          setClosureGroupId((current) => current === group.id ? null : group.id);
                          setClosureReason("");
                        }}
                      >
                        {t.closeConflict}
                      </button>
                      {closureGroupId === group.id && (
                        <form className="conflict-closure-form" onSubmit={closeConflict}>
                          <p>{t.closureRule}</p>
                          <label>
                            <span>{t.closeConflict}</span>
                            <select
                              value={closureOutcome}
                              onChange={(event) => setClosureOutcome(event.target.value as "resolved" | "dismissed")}
                            >
                              <option value="resolved">{t.resolveConflict}</option>
                              <option value="dismissed">{t.dismissConflict}</option>
                            </select>
                          </label>
                          <label>
                            <span>{t.closureReason}</span>
                            <textarea
                              required
                              maxLength={1000}
                              placeholder={t.closureReasonPlaceholder}
                              value={closureReason}
                              onChange={(event) => setClosureReason(event.target.value)}
                            />
                          </label>
                          <button className="primary-button" disabled={busy !== null} type="submit">
                            {busy === "closure" ? t.closingConflict : t.submitClosure}
                          </button>
                        </form>
                      )}
                    </>
                  ) : group.resolution_summary ? (
                    <p className="resolution-summary">{group.resolution_summary}</p>
                  ) : null}
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
          {agentReview && (
            <button className="ghost-button" type="button" onClick={() => setShowAgentRejected((current) => !current)}>
              {showAgentRejected ? t.hideRejected : t.showRejected} ({agentReview.counts.agent_rejected})
            </button>
          )}
          {claims.length === 0 ? <div className="empty-state">{t.noClaims}</div> : groupedClaims.map(([predicate, items]) => (
            <div className="claim-group" key={predicate}>
              <h3>{predicateNames[language][predicate] ?? predicate}</h3>
              {items.map((claim) => (
                <button className={selectedClaimId === claim.id ? "claim-card active" : "claim-card"} type="button" key={claim.id} aria-pressed={selectedClaimId === claim.id} onClick={() => setSelectedClaimId(claim.id)}>
                  <strong>{displayValue(claim.value)}</strong>
                  <span>{Math.round(claim.confidence * 100)}% · {claim.locale} · {claim.region}</span>
                  {claim.agent_review && (
                    <em className={`review-state review-state--${claim.agent_review.decision}`}>
                      {claim.agent_review.decision === "agent_approved"
                        ? t.approvedByAgent
                        : claim.agent_review.decision === "agent_rejected"
                          ? t.rejectedByAgent
                          : t.needsHuman}
                      {` · ${claim.agent_review.priority}`}
                    </em>
                  )}
                  {conflictByClaim.has(claim.id) && (
                    <em className={`claim-relation claim-relation--${conflictByClaim.get(claim.id)?.relation}`}>
                      {conflictByClaim.get(claim.id)?.relation === "conflicting" ? t.conflicting : t.possiblyCoexisting}
                    </em>
                  )}
                  <em className={`review-state review-state--${claim.latest_review?.decision ?? "unreviewed"}`}>
                    {reviewLabel(claim.latest_review?.decision ?? null)}
                  </em>
                </button>
              ))}
            </div>
          ))}
        </section>

        <aside className="panel evidence-panel" aria-labelledby="evidence-title">
          <div className="list-heading"><h2 id="evidence-title">{t.evidence}</h2>{selectedClaim && <span>{reviewLabel(selectedClaim.latest_review?.decision ?? null)}</span>}</div>
          {!selectedClaim ? <div className="empty-state">{t.selectClaim}</div> : (
            <>
              <div className="selected-claim"><span>{predicateNames[language][selectedClaim.predicate] ?? selectedClaim.predicate}</span><strong>{displayValue(selectedClaim.value)}</strong><small>{t.confidence}: {Math.round(selectedClaim.confidence * 100)}%</small></div>
              {selectedClaim.agent_review && (
                <div className="candidate-warning">
                  <strong>{selectedClaim.agent_review.decision === "agent_approved" ? t.approvedByAgent : selectedClaim.agent_review.decision === "agent_rejected" ? t.rejectedByAgent : t.needsHuman}</strong>
                  <p>{selectedClaim.agent_review.rationale}</p>
                  {selectedClaim.agent_review.suggested_predicate && <code>{selectedClaim.agent_review.suggested_predicate}</code>}
                </div>
              )}
              <div className="evidence-list">
                {selectedClaim.evidence.map((evidence) => (
                  <article key={`${evidence.source_version_id}-${evidence.ordinal}`}>
                    <blockquote>{evidence.quote}</blockquote>
                    <dl><div><dt>{t.source}</dt><dd><a href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.source_title}</a></dd></div><div><dt>{t.version}</dt><dd>v{evidence.source_version_number} · {evidence.locale} · {evidence.region}</dd></div><div><dt>{t.fetched}</dt><dd>{formatDate(evidence.fetched_at, language)}</dd></div><div><dt>{t.offsets}</dt><dd>{evidence.start_offset}–{evidence.end_offset}</dd></div></dl>
                  </article>
                ))}
              </div>
              <section className="claim-review" aria-labelledby="claim-review-title">
                <div>
                  <h3 id="claim-review-title">{t.reviewTitle}</h3>
                  <p>{t.reviewHint}</p>
                </div>
                <form className="claim-review-form" onSubmit={submitReview}>
                  <label>
                    <span>{t.latestDecision}</span>
                    <select
                      value={reviewDecision}
                      onChange={(event) => setReviewDecision(event.target.value as ReviewDecision)}
                    >
                      <option value="approve">{t.approve}</option>
                      <option value="approve_with_edit">{t.approveWithEdit}</option>
                      <option value="reject">{t.reject}</option>
                      <option value="defer">{t.defer}</option>
                    </select>
                  </label>
                  {reviewDecision === "approve_with_edit" && (
                    <label>
                      <span>{t.editedValue}</span>
                      <textarea
                        required
                        maxLength={4000}
                        value={reviewEditedValue}
                        onChange={(event) => setReviewEditedValue(event.target.value)}
                      />
                      <small>{t.editedValueHint}</small>
                    </label>
                  )}
                  <label>
                    <span>{t.reviewReason}</span>
                    <textarea
                      required
                      maxLength={1000}
                      placeholder={t.reviewReasonPlaceholder}
                      value={reviewReason}
                      onChange={(event) => setReviewReason(event.target.value)}
                    />
                  </label>
                  <button className="primary-button" disabled={busy !== null} type="submit">
                    {busy === "review" ? t.savingReview : t.submitReview}
                  </button>
                </form>
                <div className="review-history">
                  <strong>{t.reviewHistory}</strong>
                  {(selectedClaim.reviews ?? []).length === 0 ? <p>{t.noReview}</p> : (
                    <ol>
                      {[...(selectedClaim.reviews ?? [])].reverse().map((review) => (
                        <li key={review.id}>
                          <div>
                            <span className={`review-state review-state--${review.decision}`}>
                              {reviewLabel(review.decision)}
                            </span>
                            <time>{formatDate(review.created_at, language)}</time>
                          </div>
                          {review.approved_value !== null && review.decision === "approve_with_edit" && (
                            <strong>{displayValue(review.approved_value)}</strong>
                          )}
                          <p>{review.reason}</p>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              </section>
            </>
          )}
        </aside>
      </div>

      <section className="panel snapshot-workspace" aria-labelledby="snapshot-title">
        <div className="snapshot-heading">
          <div>
            <h2 id="snapshot-title">{t.snapshotTitle}</h2>
            <p>{t.snapshotHint}</p>
          </div>
          {snapshotReadiness && (
            <span className={snapshotReadiness.publishable ? "snapshot-state snapshot-state--ready" : "snapshot-state snapshot-state--blocked"}>
              {snapshotReadiness.publishable ? t.snapshotReady : t.snapshotBlocked}
            </span>
          )}
        </div>
        {snapshotReadiness && (
          <>
            <div className="snapshot-metrics">
              <div><span>{t.nextSnapshot}</span><strong>v{snapshotReadiness.next_version_number}</strong></div>
              <div><span>{t.approvedFacts}</span><strong>{snapshotReadiness.stats.approved_count}</strong></div>
              <div><span>{t.finalReviews}</span><strong>{snapshotReadiness.stats.approved_count + snapshotReadiness.stats.rejected_count}/{snapshotReadiness.stats.claim_count}</strong></div>
              <div><span>{t.openConflicts}</span><strong>{snapshotReadiness.stats.open_conflict_count}</strong></div>
            </div>
            {snapshotReadiness.blockers.length > 0 && (
              <ul className="snapshot-blockers">
                {snapshotReadiness.blockers.map((blocker, index) => (
                  <li key={`${blocker.code}-${index}`}>
                    <strong>{t.snapshotBlockers[blocker.code as keyof typeof t.snapshotBlockers] ?? blocker.message}</strong>
                    {blocker.count !== undefined && <span>{blocker.count}</span>}
                  </li>
                ))}
              </ul>
            )}
            <form className="snapshot-publish-form" onSubmit={publishSnapshot}>
              <label>
                <span>{t.snapshotNotes}</span>
                <textarea
                  maxLength={2000}
                  placeholder={t.snapshotNotesPlaceholder}
                  value={snapshotNotes}
                  onChange={(event) => setSnapshotNotes(event.target.value)}
                />
              </label>
              <button className="primary-button" disabled={busy !== null || !snapshotReadiness.publishable} type="submit">
                {busy === "snapshot" ? t.publishingSnapshot : t.publishSnapshot}
              </button>
              {snapshotReadiness.content_sha256 && <code>{snapshotReadiness.schema_version} · {snapshotReadiness.content_sha256.slice(0, 16)}</code>}
            </form>
          </>
        )}
        <div className="snapshot-history">
          <h3>{t.snapshotHistory}</h3>
          {snapshots.length === 0 ? <p>{t.noSnapshots}</p> : (
            <div className="snapshot-list">
              {snapshots.map((snapshot) => (
                <details key={snapshot.id} open={snapshot.is_latest}>
                  <summary>
                    <span>v{snapshot.version_number} {snapshot.is_latest && <em>{t.latestSnapshot}</em>}</span>
                    <strong>{snapshot.member_count} {t.snapshotFacts}</strong>
                    <time>{formatDate(snapshot.published_at, language)}</time>
                  </summary>
                  <div className="snapshot-detail">
                    <code>{snapshot.schema_version} · {snapshot.content_sha256}</code>
                    {snapshot.notes && <p>{snapshot.notes}</p>}
                    {(() => {
                      const synthesis = snapshotSynthesis(snapshot);
                      return <div className="snapshot-metrics" aria-label={t.synthesis}>
                        <div><span>{t.distinctSources}</span><strong>{synthesis.sourceCount}</strong></div>
                        <div><span>{t.corroborated}</span><strong>{synthesis.corroborated}</strong></div>
                        <div><span>{t.singleSource}</span><strong>{synthesis.singleSource}</strong></div>
                        <div><span>{t.synthesisHint}</span><code>{synthesis.ruleVersion}</code></div>
                      </div>;
                    })()}
                    <div className="snapshot-members">
                      {snapshot.members.map((member) => (
                        <article key={`${snapshot.id}-${member.review_id}`}>
                          <span>{predicateNames[language][member.predicate] ?? member.predicate}</span>
                          <strong>{displayValue(member.value)}</strong>
                          <small>{member.subject.display_name} · {reviewLabel(member.review.decision)}</small>
                          {member.evidence[0] && (
                            <a href={member.evidence[0].source_url} target="_blank" rel="noreferrer">
                              {member.evidence[0].source_title} · v{member.evidence[0].source_version_number}
                            </a>
                          )}
                        </article>
                      ))}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </section>
    </section>
  );
}
