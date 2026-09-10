import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate, idempotencyKey } from "./client";
import type { Language } from "./client";
import {
  CreativeProgress,
  ReasonChoices,
  useCreativeAssistant,
} from "./CreativeAssistant";
import {
  StoryboardEditor,
  EvidenceNotes,
  ruleNames,
  ruleFixes,
  type Evidence,
  type ScriptContent,
} from "./ScriptEditor";

type Task = {
  id: string;
  platform: string;
  duration_seconds: number;
  output_language: string;
  approved_candidate_id: string | null;
  created_at: string;
};
type Version = {
  parent_version_id?: string;
  generation_metadata?: { mode?: string; requires_semantic_review?: boolean };
  id: string;
  version_number: number;
  origin: string;
  content: ScriptContent;
  content_sha256: string;
  created_at: string;
};
type Evaluation = {
  semantic_report?: {
    mode: string;
    summary?: string;
    word_count?: number;
    words_per_minute?: number;
    issues?: {
      draft_quote?: string;
      section_index: number | null;
      severity: string;
      message: string;
      fix: string;
    }[];
  };
  id: string;
  script_version_id: string;
  score: number;
  passed: boolean;
  dimensions: Record<string, { score: number; max: number }>;
  issues: string[];
  rule_version: string;
};
type FinalReview = {
  evaluation_id?: string;
  id: string;
  script_version_id: string;
  decision: "approve" | "reject";
  reason: string;
  created_at: string;
};
type ScriptRun = {
  evidence?: Evidence[];
  id: string;
  marketing_task_id: string;
  revision_budget: number;
  revisions_used: number;
  score_threshold: number;
  generator_version: string;
  evaluator_version: string;
  current_rule_version?: string;
  versions: Version[];
  evaluations: Evaluation[];
  final_reviews: FinalReview[];
  created_at: string;
};
type ExportPayload = {
  filename: string;
  media_type: string;
  content: string;
  sha256: string;
};

const copy = {
  "zh-CN": {
    eyebrow: "M4 · 可交付创作",
    title: "证据约束的 TikTok 脚本",
    intro:
      "选题确认后，得到可拍摄的英语分镜稿；本地模型独立评审、限次修订、人工终审和导出全程留痕。",
    task: "已批准选题的营销任务",
    noTask: "尚无可创作任务。请先在“营销”中批准一个选题。",
    create: "创建脚本工作流",
    choose: "脚本工作流",
    generate: "生成英语脚本并评审",
    version: "脚本版本",
    noVersion: "下一步：生成初稿。后台依次写作和评审，你可以离开此步骤。",
    evaluate: "独立内容评审",
    revise: "按问题修订并重新评审",
    budget: "修订预算",
    edit: "编辑结构化脚本",
    saveEdit: "保存为新版本",
    finalGate: "人工终审",
    approve: "批准",
    reject: "拒绝",
    reason: "终审理由",
    submitReview: "记录终审",
    exportMd: "导出 Markdown",
    exportJson: "导出 JSON",
    approved: "可导出",
    blocked: "待通过评测与人工批准",
    evidence: "知识引用",
    trend: "趋势引用",
    working: "处理中…",
    refresh: "刷新",
    score: "规则完成度（非效果预测）",
    policy: "本地模型创作 + 独立评审 · 无付费 API",
    invalidJson: "脚本 JSON 格式无效",
    downloaded: "导出文件已生成并下载。",
  },
  en: {
    eyebrow: "M4 · Deliverable creation",
    title: "Evidence-bound TikTok scripts",
    intro:
      "Generation starts only after topic approval. Local model writing, independent review, bounded revision, final human approval, and export remain traceable. No paid API is used.",
    task: "Marketing task with approved topic",
    noTask: "No eligible task. Approve a topic in Marketing first.",
    create: "Create script workflow",
    choose: "Script workflow",
    generate: "Write and review English script",
    version: "Script version",
    noVersion: "Create a workflow, then generate the first version.",
    evaluate: "Independent content review",
    revise: "Revise findings and re-review",
    budget: "Revision budget",
    edit: "Edit structured script",
    saveEdit: "Save as new version",
    finalGate: "Final human gate",
    approve: "Approve",
    reject: "Reject",
    reason: "Review reason",
    submitReview: "Record final review",
    exportMd: "Export Markdown",
    exportJson: "Export JSON",
    approved: "Ready to export",
    blocked: "Evaluation and approval required",
    evidence: "Knowledge refs",
    trend: "Trend refs",
    working: "Working…",
    refresh: "Refresh",
    score: "Rule readiness (not predicted performance)",
    policy: "Local writing + independent review · no paid API",
    invalidJson: "Script JSON is invalid",
    downloaded: "Export generated and downloaded.",
  },
} as const;

export function ScriptWorkspace({
  projectId,
  language,
}: {
  projectId: string;
  language: Language;
}) {
  const t = copy[language];
  const zh = language === "zh-CN";
  const [changeReview, setChangeReview] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<ScriptRun[]>([]);
  const [taskId, setTaskId] = useState("");
  const [runId, setRunId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    kind: "ok" | "error";
    text: string;
  } | null>(null);

  const load = useCallback(async () => {
    const [taskPayload, runPayload] = await Promise.all([
      api<{ items: Task[] }>(`/api/projects/${projectId}/marketing-tasks`),
      api<{ items: ScriptRun[] }>(`/api/projects/${projectId}/script-runs`),
    ]);
    const eligible = taskPayload.items.filter(
      (item) => item.approved_candidate_id,
    );
    setTasks(eligible);
    setRuns(runPayload.items);
    setTaskId((current) =>
      eligible.some((item) => item.id === current)
        ? current
        : (eligible[0]?.id ?? ""),
    );
    setRunId((current) =>
      runPayload.items.some((item) => item.id === current)
        ? current
        : (runPayload.items[0]?.id ?? ""),
    );
  }, [projectId]);
  useEffect(() => {
    void load().catch((error: unknown) =>
      setNotice({
        kind: "error",
        text: error instanceof Error ? error.message : String(error),
      }),
    );
  }, [load]);
  const run = runs.find((item) => item.id === runId) ?? null;
  const version =
    run?.versions.find((item) => item.id === versionId) ??
    run?.versions.at(-1) ??
    null;
  const evaluation = useMemo(
    () =>
      run?.evaluations
        .filter((item) => item.script_version_id === version?.id)
        .at(-1) ?? null,
    [run, version],
  );
  const finalReview = useMemo(
    () =>
      run?.final_reviews
        .filter((item) => item.script_version_id === version?.id)
        .at(-1) ?? null,
    [run, version],
  );
  useEffect(() => {
    setVersionId(version?.id ?? "");
    setReason("");
    setChangeReview(false);
  }, [version?.id]);
  const assistant = useCreativeAssistant(projectId, runId, (item) => {
    if (item.result.version_id) setVersionId(item.result.version_id);
    void load().catch((e: Error) =>
      setNotice({ kind: "error", text: e.message }),
    );
  });
  const locked = busy !== null || assistant.busy;
  const currentEvaluation = !!run?.current_rule_version && evaluation?.rule_version === run.current_rule_version;
  const exportReady =
    currentEvaluation &&
    evaluation?.passed &&
    finalReview?.decision === "approve" &&
    finalReview.evaluation_id === evaluation.id;
  const needsSemantic =
    version?.generation_metadata?.mode === "local_model" ||
    version?.generation_metadata?.requires_semantic_review;
  const parent = run?.versions.find((v) => v.id === version?.parent_version_id);

  const action = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name);
    setNotice(null);
    try {
      await fn();
      await load();
      setNotice({ kind: "ok", text: name });
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusy(null);
    }
  };
  const createRun = () =>
    action(t.create, async () => {
      const item = await api<ScriptRun>(
        `/api/projects/${projectId}/script-runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("script-run"),
          },
          body: JSON.stringify({
            marketing_task_id: taskId,
            revision_budget: 2,
            score_threshold: 80,
          }),
        },
      );
      setRunId(item.id);
    });
  const generate = () => assistant.submit("write");
  const scaffold = () =>
    run &&
    action(
      zh
        ? "已创建手动草稿框架，请编辑后检查。"
        : "Manual scaffold created; edit and check it.",
      async () => {
        const item = await api<Version>(
          `/api/projects/${projectId}/script-runs/${run.id}/versions/generate`,
          {
            method: "POST",
            headers: { "Idempotency-Key": idempotencyKey("script-manual") },
          },
        );
        setVersionId(item.id);
      },
    );
  const evaluate = () => assistant.submit("critique");
  const evaluateRules = () =>
    run &&
    version &&
    action(t.evaluate, () =>
      api(
        `/api/projects/${projectId}/script-runs/${run.id}/versions/${version.id}/evaluations`,
        {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey("script-evaluate") },
        },
      ),
    );
  const revise = () => assistant.submit("revise");
  const saveEdit = (content: ScriptContent) =>
    run &&
    action(t.saveEdit, async () => {
      const item = await api<Version>(
        `/api/projects/${projectId}/script-runs/${run.id}/versions/edit`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("script-edit"),
          },
          body: JSON.stringify({ content }),
        },
      );
      setVersionId(item.id);
    });
  const review = (event: FormEvent) => {
    event.preventDefault();
    if (!run || !version) return;
    void action(t.submitReview, async () => {
      await api(
        `/api/projects/${projectId}/script-runs/${run.id}/final-reviews`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("script-final-review"),
          },
          body: JSON.stringify({ version_id: version.id, decision, reason }),
        },
      );
      setReason("");
      setChangeReview(false);
    });
  };
  const exportFile = (format: "markdown" | "json") =>
    run &&
    version &&
    action(format === "markdown" ? t.exportMd : t.exportJson, async () => {
      const payload = await api<ExportPayload>(
        `/api/projects/${projectId}/script-runs/${run.id}/exports`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey(`script-export-${format}`),
          },
          body: JSON.stringify({ version_id: version.id, format }),
        },
      );
      const link = document.createElement("a");
      link.href = URL.createObjectURL(
        new Blob([payload.content], { type: payload.media_type }),
      );
      link.download = payload.filename;
      link.click();
      URL.revokeObjectURL(link.href);
      setNotice({
        kind: "ok",
        text: `${t.downloaded} SHA-256 ${payload.sha256}`,
      });
    });

  return (
    <div className="script-workspace">
      <section className="script-intro">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h2>{t.title}</h2>
          <p>{t.intro}</p>
        </div>
        <button
          className="ghost-button"
          type="button"
          onClick={() => void load()}
        >
          {t.refresh}
        </button>
      </section>
      <div className="policy-banner">
        <strong>{t.policy}</strong>
        <span>
          {assistant.capability?.model ??
            (zh ? "检查模型中" : "Checking model")}
        </span>
      </div>
      {notice && (
        <div className={`notice notice--${notice.kind}`} role="status">
          {notice.text}
        </div>
      )}
      <CreativeProgress assistant={assistant} language={language} />
      <details className="script-control panel" open={!run}>
        <summary>
          {zh
            ? "脚本工作流设置（已有版本无需重复创建）"
            : "Workflow settings (existing drafts do not need a new workflow)"}
        </summary>
        <label>
          <span>{t.task}</span>
          <select
            value={taskId}
            onChange={(event) => setTaskId(event.target.value)}
          >
            {tasks.map((item) => (
              <option value={item.id} key={item.id}>
                {item.platform} · {item.duration_seconds}s ·{" "}
                {formatDate(item.created_at, language)}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          disabled={!taskId || locked}
          type="button"
          onClick={() => void createRun()}
        >
          {busy ?? t.create}
        </button>
        {tasks.length === 0 && <p>{t.noTask}</p>}
        {runs.length > 0 && (
          <label>
            <span>{t.choose}</span>
            <select
              value={runId}
              onChange={(event) => {
                setRunId(event.target.value);
                setVersionId("");
              }}
            >
              {runs.map((item) => (
                <option key={item.id} value={item.id}>
                  {formatDate(item.created_at, language)} ·{" "}
                  {item.versions.length} {t.version}
                </option>
              ))}
            </select>
          </label>
        )}
        {run && (
          <div className="script-budget">
            <span>{t.budget}</span>
            <strong>
              {run.revisions_used}/{run.revision_budget}
            </strong>
            <span>
              {language === "zh-CN"
                ? "全部规则通过 + 无阻断评审意见，才能终审批准"
                : "All rules must pass with no blocking review findings before approval"}
            </span>
          </div>
        )}
      </details>
      {!run ? (
        <div className="empty-state">{t.noVersion}</div>
      ) : !version ? (
        <section className="panel">
          <p>{t.noVersion}</p>
          <button
            className="primary-button"
            disabled={
              locked ||
              !assistant.capability?.available ||
              assistant.readiness?.ready === false
            }
            type="button"
            onClick={() => void generate()}
          >
            {assistant.busy ? t.working : t.generate}
          </button>
          {!assistant.capability?.available && (
            <p>
              {zh
                ? "本地模型未就绪。请启动 Ollama，或明确选择下方手动起稿。"
                : "Start Ollama or explicitly choose a manual scaffold below."}
            </p>
          )}
          <details>
            <summary>
              {zh ? "不用模型：手动起稿" : "Without a model: manual draft"}
            </summary>
            <button
              className="ghost-button"
              disabled={locked}
              onClick={() => void scaffold()}
            >
              {zh ? "创建手动草稿框架" : "Create manual scaffold"}
            </button>
          </details>
        </section>
      ) : (
        <div className="script-grid">
          <section className="script-preview panel">
            <label>
              <span>{t.version}</span>
              <select
                aria-label={t.version}
                value={version.id}
                onChange={(e) => setVersionId(e.target.value)}
              >
                {run.versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} ·{" "}
                    {v.generation_metadata?.mode ??
                      (zh ? "历史模板" : "legacy template")}
                  </option>
                ))}
              </select>
            </label>
            <div className="list-heading">
              <h2>{version.content.title}</h2>
              <span>
                v{version.version_number} · {version.origin}
              </span>
            </div>
            <p>{version.content.caption}</p>
            <div className="script-sections">
              {version.content.sections.map((section) => (
                <article key={`${section.start_second}-${section.purpose}`}>
                  <header>
                    <strong>
                      {section.start_second}–{section.end_second}s
                    </strong>
                    <span>{section.purpose}</span>
                  </header>
                  <p>{section.voiceover}</p>
                  <small>{section.on_screen_text}</small>
                  <p className="section-hint">{section.visual_direction}</p>
                  <EvidenceNotes
                    ids={section.knowledge_member_ids}
                    evidence={run.evidence ?? []}
                    language={language}
                  />
                  <dl>
                    <div>
                      <dt>{t.evidence}</dt>
                      <dd>{section.knowledge_member_ids.length}</dd>
                    </div>
                    <div>
                      <dt>{t.trend}</dt>
                      <dd>{section.trend_signal_ids.length}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
            <p className="hashtags">{version.content.hashtags.join(" ")}</p>
            {parent && (
              <details className="script-diff">
                <summary>
                  {zh
                    ? "与上一版本相比改了什么"
                    : "Changes from previous version"}
                </summary>
                {(["title", "caption", "hashtags"] as const).map((key, index) =>
                  JSON.stringify(version.content[key]) !== JSON.stringify(parent.content[key]) && (
                    <div key={key}>
                      <strong>{(zh ? ["标题", "发布文案", "标签"] : ["Title", "Caption", "Hashtags"])[index]}</strong>
                      <p><del>{Array.isArray(parent.content[key]) ? parent.content[key].join(" ") : parent.content[key]}</del></p>
                      <p><ins>{Array.isArray(version.content[key]) ? version.content[key].join(" ") : version.content[key]}</ins></p>
                    </div>
                  )
                )}
                {version.content.sections.map(
                  (beat, i) =>
                    JSON.stringify(beat) !==
                      JSON.stringify(parent.content.sections[i]) && (
                      <div key={i}>
                        <strong>
                          {zh ? "分镜" : "Beat"} {i + 1}
                        </strong>
                        <p>
                          <del>{parent.content.sections[i]?.voiceover}</del>
                        </p>
                        <p>
                          <ins>{beat.voiceover}</ins>
                        </p>
                        {beat.voiceover ===
                          parent.content.sections[i]?.voiceover && (
                          <p>
                            {zh
                              ? "画面、字幕或引用已更新。"
                              : "Visuals, screen text or citations updated."}
                          </p>
                        )}
                      </div>
                    ),
                )}
              </details>
            )}
          </section>
          <aside className="script-actions">
            <section className="panel evaluation-card">
              <h3>{t.score}</h3>
              {evaluation ? (
                <>
                  <strong
                    className={
                      evaluation.passed && currentEvaluation
                        ? "score-pass"
                        : "score-fail"
                    }
                  >
                    {evaluation.score}/100
                  </strong>
                  <p>
                    {!currentEvaluation
                      ? zh
                        ? "旧版检查已过期，请重新检查。"
                        : "Legacy result: recheck this version."
                      : evaluation.passed
                        ? zh
                          ? "检查通过，下一步提交人工终审。"
                          : "Checks passed. Submit your final review next."
                        : zh
                          ? "请修复下方问题后重新评审。"
                          : "Resolve the findings below and re-review."}
                  </p>
                  <p>
                    {evaluation.semantic_report?.summary ??
                      (zh
                        ? "未进行模型内容评审。"
                        : "No semantic model review.")}
                  </p>
                  {evaluation.semantic_report?.mode === "local_model" && (
                    <p className="muted">
                      {zh
                        ? "下方是模型判断，不是新的游戏事实。请对照原句与证据核实；怀疑误判时重新评审，不要直接照改游戏名称或设定。"
                        : "These are model findings, not new game facts. Check the quoted draft and evidence. If a finding looks wrong, re-review instead of blindly changing names or lore."}
                    </p>
                  )}
                  {evaluation.semantic_report?.word_count !== undefined && (
                    <p>
                      {evaluation.semantic_report.word_count} words ·{" "}
                      {evaluation.semantic_report.words_per_minute} WPM
                    </p>
                  )}
                  <dl>
                    {Object.entries(evaluation.dimensions).map(
                      ([name, value]) => (
                        <div key={name}>
                          <dt>
                            {zh
                              ? (ruleNames[name] ?? name)
                              : name.replaceAll("_", " ")}
                          </dt>
                          <dd>
                            {value.score}/{value.max}
                          </dd>
                        </div>
                      ),
                    )}
                  </dl>
                  <ul>
                    {evaluation.issues
                      .filter((i) => i.endsWith("_failed"))
                      .map((issue) => (
                        <li key={issue}>
                          {zh
                            ? (ruleFixes[issue] ?? issue)
                            : issue.replaceAll("_", " ")}
                        </li>
                      ))}
                  </ul>
                  {evaluation.semantic_report?.issues?.map((issue, i) => (
                    <div className="critic-issue" key={i}>
                      <strong>
                        {issue.severity === "blocking"
                          ? zh
                            ? "模型发现风险"
                            : "Model-flagged risk"
                          : zh
                            ? "建议"
                            : "Suggestion"}
                        {issue.section_index !== null &&
                          " · " + (issue.section_index + 1)}
                      </strong>
                      {issue.draft_quote && <blockquote>{issue.draft_quote}</blockquote>}
                      <p>{issue.message}</p>
                      <p>
                        {zh ? "修改建议：" : "Suggested fix: "}
                        {issue.fix}
                      </p>
                    </div>
                  ))}
                </>
              ) : (
                <p>{t.blocked}</p>
              )}
              <button
                className="secondary-button"
                disabled={
                  locked ||
                  !assistant.capability?.available ||
                  version.id !== run.versions.at(-1)?.id
                }
                type="button"
                onClick={() => void evaluate()}
              >
                {assistant.busy ? t.working : t.evaluate}
              </button>
              {!needsSemantic && (
                <button
                  className="ghost-button"
                  disabled={locked}
                  onClick={() => void evaluateRules()}
                >
                  {zh
                    ? "仅检查手动稿的格式与时长"
                    : "Check manual draft structure and timing only"}
                </button>
              )}
              {evaluation && !evaluation.passed && (
                <button
                  className="primary-button"
                  disabled={
                    locked ||
                    !assistant.capability?.available ||
                    run.revisions_used >= run.revision_budget ||
                    version.id !== run.versions.at(-1)?.id
                  }
                  type="button"
                  onClick={() => void revise()}
                >
                  {t.revise}
                </button>
              )}
              {evaluation &&
                !evaluation.passed &&
                run.revisions_used >= run.revision_budget && (
                  <p className="notice">
                    {zh
                      ? "自动修订次数已用完。请展开下方逐镜编辑，保存新版本后重新评审。"
                      : "Revision budget exhausted. Edit the storyboard below, save a new version, then review again."}
                  </p>
                )}
            </section>
            <StoryboardEditor
              key={version.id}
              content={version.content}
              evidence={run.evidence ?? []}
              language={language}
              disabled={locked}
              onSave={(content) => void saveEdit(content)}
            />
            <section className="panel final-review">
              <h3>{t.finalGate}</h3>
              {finalReview &&
              !changeReview &&
              finalReview.evaluation_id === evaluation?.id ? (
                <div className="review-complete">
                  <strong>
                    {finalReview.decision === "approve"
                      ? zh
                        ? "已批准，无需重复提交"
                        : "Approved; no duplicate submission needed"
                      : zh
                        ? "已记录拒绝，请修改后重新评审"
                        : "Rejection saved; edit and re-review"}
                  </strong>
                  <p>{finalReview.reason}</p>
                  <button
                    className="ghost-button"
                    onClick={() => setChangeReview(true)}
                  >
                    {zh ? "更改决定" : "Change decision"}
                  </button>
                </div>
              ) : (
                <form onSubmit={review}>
                  <p>
                    {zh
                      ? "请核实事实、表达和素材权利。模型评审不代替交付确认。"
                      : "Confirm facts, wording and footage rights before delivery."}
                  </p>
                  <div className="reason-choices__options">
                    {(["approve", "reject"] as const).map((d) => (
                      <button
                        key={d}
                        type="button"
                        aria-pressed={decision === d}
                        onClick={() => {
                          setDecision(d);
                          setReason("");
                        }}
                      >
                        {d === "approve" ? t.approve : t.reject}
                      </button>
                    ))}
                  </div>
                  <ReasonChoices
                    key={`${version.id}-${decision}`}
                    label={t.reason}
                    language={language}
                    value={reason}
                    onChange={setReason}
                    choices={
                      decision === "approve"
                        ? zh
                          ? [
                              "内容与证据一致，口播和素材权利已核验",
                              "已逐镜检查，批准用于制作",
                            ]
                          : [
                              "Evidence, pacing and footage rights checked",
                              "Every beat reviewed; ready for production",
                            ]
                        : zh
                          ? [
                              "包含证据不支持的内容",
                              "节奏或表达需要调整",
                              "素材使用权尚未确认",
                            ]
                          : [
                              "Unsupported claims",
                              "Pacing or wording needs work",
                              "Footage rights unconfirmed",
                            ]
                    }
                  />
                  <button
                    className="primary-button"
                    disabled={
                      locked ||
                      !reason.trim() ||
                      !evaluation ||
                      (decision === "approve" &&
                        (!evaluation.passed || !currentEvaluation))
                    }
                    type="submit"
                  >
                    {t.submitReview}
                  </button>
                </form>
              )}
            </section>
            <section className="panel export-actions">
              <button
                className="secondary-button"
                disabled={!exportReady || locked}
                type="button"
                onClick={() => void exportFile("markdown")}
              >
                {t.exportMd}
              </button>
              <button
                className="secondary-button"
                disabled={!exportReady || locked}
                type="button"
                onClick={() => void exportFile("json")}
              >
                {t.exportJson}
              </button>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
