import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate, idempotencyKey } from "./client";
import type { Language } from "./client";

type Task = { id: string; platform: string; duration_seconds: number; output_language: string; approved_candidate_id: string | null; created_at: string };
type Section = { start_second: number; end_second: number; purpose: string; voiceover: string; on_screen_text: string; visual_direction: string; knowledge_member_ids: string[]; trend_signal_ids: string[] };
type ScriptContent = { schema_version: string; platform: string; output_language: string; duration_seconds: number; title: string; caption: string; hashtags: string[]; sections: Section[] };
type Version = { id: string; version_number: number; origin: string; content: ScriptContent; content_sha256: string; created_at: string };
type Evaluation = { id: string; script_version_id: string; score: number; passed: boolean; dimensions: Record<string, { score: number; max: number }>; issues: string[]; rule_version: string };
type FinalReview = { id: string; script_version_id: string; decision: "approve" | "reject"; reason: string; created_at: string };
type ScriptRun = { id: string; marketing_task_id: string; revision_budget: number; revisions_used: number; score_threshold: number; generator_version: string; evaluator_version: string; versions: Version[]; evaluations: Evaluation[]; final_reviews: FinalReview[]; created_at: string };
type ExportPayload = { filename: string; media_type: string; content: string; sha256: string };

const copy = {
  "zh-CN": {
    eyebrow: "M4 · 可交付创作", title: "证据约束的 TikTok 脚本", intro: "选题批准后才能生成；规则评测、限次自动修订、人工终审和导出全程留痕。第一版不调用付费模型。", task: "已批准选题的营销任务", noTask: "尚无可创作任务。请先在“营销”中批准一个选题。", create: "创建脚本工作流", choose: "脚本工作流", generate: "生成英语脚本", version: "脚本版本", noVersion: "创建工作流后生成第一个版本。", evaluate: "运行规则评测", revise: "自动修订", budget: "修订预算", edit: "编辑结构化脚本", saveEdit: "保存为新版本", finalGate: "人工终审", approve: "批准", reject: "拒绝", reason: "终审理由", submitReview: "记录终审", exportMd: "导出 Markdown", exportJson: "导出 JSON", approved: "可导出", blocked: "待通过评测与人工批准", evidence: "知识引用", trend: "趋势引用", working: "处理中…", refresh: "刷新", score: "质量分", policy: "确定性模板 + 确定性评测 · 零模型费用", invalidJson: "脚本 JSON 格式无效", downloaded: "导出文件已生成并下载。",
  },
  en: {
    eyebrow: "M4 · Deliverable creation", title: "Evidence-bound TikTok scripts", intro: "Generation starts only after topic approval. Rule evaluation, bounded revision, final human review, and export remain traceable. No paid model is called in v1.", task: "Marketing task with approved topic", noTask: "No eligible task. Approve a topic in Marketing first.", create: "Create script workflow", choose: "Script workflow", generate: "Generate English script", version: "Script version", noVersion: "Create a workflow, then generate the first version.", evaluate: "Run rule evaluation", revise: "Auto-revise", budget: "Revision budget", edit: "Edit structured script", saveEdit: "Save as new version", finalGate: "Final human gate", approve: "Approve", reject: "Reject", reason: "Review reason", submitReview: "Record final review", exportMd: "Export Markdown", exportJson: "Export JSON", approved: "Ready to export", blocked: "Evaluation and approval required", evidence: "Knowledge refs", trend: "Trend refs", working: "Working…", refresh: "Refresh", score: "Quality score", policy: "Deterministic template + deterministic evaluation · zero model cost", invalidJson: "Script JSON is invalid", downloaded: "Export generated and downloaded.",
  },
} as const;

export function ScriptWorkspace({ projectId, language }: { projectId: string; language: Language }) {
  const t = copy[language];
  const [tasks, setTasks] = useState<Task[]>([]); const [runs, setRuns] = useState<ScriptRun[]>([]);
  const [taskId, setTaskId] = useState(""); const [runId, setRunId] = useState(""); const [versionId, setVersionId] = useState("");
  const [editor, setEditor] = useState(""); const [decision, setDecision] = useState<"approve" | "reject">("approve"); const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null); const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    const [taskPayload, runPayload] = await Promise.all([
      api<{ items: Task[] }>(`/api/projects/${projectId}/marketing-tasks`),
      api<{ items: ScriptRun[] }>(`/api/projects/${projectId}/script-runs`),
    ]);
    const eligible = taskPayload.items.filter((item) => item.approved_candidate_id);
    setTasks(eligible); setRuns(runPayload.items);
    setTaskId((current) => eligible.some((item) => item.id === current) ? current : eligible[0]?.id ?? "");
    setRunId((current) => runPayload.items.some((item) => item.id === current) ? current : runPayload.items[0]?.id ?? "");
  }, [projectId]);
  useEffect(() => { void load().catch((error: unknown) => setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) })); }, [load]);
  const run = runs.find((item) => item.id === runId) ?? null;
  const version = run?.versions.find((item) => item.id === versionId) ?? run?.versions.at(-1) ?? null;
  const evaluation = useMemo(() => run?.evaluations.filter((item) => item.script_version_id === version?.id).at(-1) ?? null, [run, version]);
  const finalReview = useMemo(() => run?.final_reviews.filter((item) => item.script_version_id === version?.id).at(-1) ?? null, [run, version]);
  useEffect(() => { if (version) { setVersionId(version.id); setEditor(JSON.stringify(version.content, null, 2)); } else { setVersionId(""); setEditor(""); } }, [version?.id]);

  const action = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name); setNotice(null);
    try { await fn(); await load(); setNotice({ kind: "ok", text: name }); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); }
    finally { setBusy(null); }
  };
  const createRun = () => action(t.create, async () => { const item = await api<ScriptRun>(`/api/projects/${projectId}/script-runs`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("script-run") }, body: JSON.stringify({ marketing_task_id: taskId, revision_budget: 2, score_threshold: 80 }) }); setRunId(item.id); });
  const generate = () => run && action(t.generate, async () => { const item = await api<Version>(`/api/projects/${projectId}/script-runs/${run.id}/versions/generate`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey("script-generate") } }); setVersionId(item.id); });
  const evaluate = () => run && version && action(t.evaluate, () => api(`/api/projects/${projectId}/script-runs/${run.id}/versions/${version.id}/evaluations`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey("script-evaluate") } }));
  const revise = () => run && action(t.revise, async () => { const item = await api<Version>(`/api/projects/${projectId}/script-runs/${run.id}/versions/revise`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey("script-revise") } }); setVersionId(item.id); });
  const saveEdit = () => run && action(t.saveEdit, async () => { let content: ScriptContent; try { content = JSON.parse(editor) as ScriptContent; } catch { throw new Error(t.invalidJson); } const item = await api<Version>(`/api/projects/${projectId}/script-runs/${run.id}/versions/edit`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("script-edit") }, body: JSON.stringify({ content }) }); setVersionId(item.id); });
  const review = (event: FormEvent) => { event.preventDefault(); if (!run || !version) return; void action(t.submitReview, async () => { await api(`/api/projects/${projectId}/script-runs/${run.id}/final-reviews`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("script-final-review") }, body: JSON.stringify({ version_id: version.id, decision, reason }) }); setReason(""); }); };
  const exportFile = (format: "markdown" | "json") => run && version && action(format === "markdown" ? t.exportMd : t.exportJson, async () => { const payload = await api<ExportPayload>(`/api/projects/${projectId}/script-runs/${run.id}/exports`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey(`script-export-${format}`) }, body: JSON.stringify({ version_id: version.id, format }) }); const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([payload.content], { type: payload.media_type })); link.download = payload.filename; link.click(); URL.revokeObjectURL(link.href); setNotice({ kind: "ok", text: `${t.downloaded} SHA-256 ${payload.sha256}` }); });

  return <div className="script-workspace">
    <section className="script-intro"><div><p className="eyebrow">{t.eyebrow}</p><h2>{t.title}</h2><p>{t.intro}</p></div><button className="ghost-button" type="button" onClick={() => void load()}>{t.refresh}</button></section>
    <div className="policy-banner"><strong>{t.policy}</strong><span>tiktok-template-v1</span></div>
    {notice && <div className={`notice notice--${notice.kind}`} role="status">{notice.text}</div>}
    <section className="script-control panel"><label><span>{t.task}</span><select value={taskId} onChange={(event) => setTaskId(event.target.value)}>{tasks.map((item) => <option value={item.id} key={item.id}>{item.platform} · {item.duration_seconds}s · {formatDate(item.created_at, language)}</option>)}</select></label><button className="primary-button" disabled={!taskId || busy !== null} type="button" onClick={() => void createRun()}>{busy ?? t.create}</button>{tasks.length === 0 && <p>{t.noTask}</p>}
      {runs.length > 0 && <label><span>{t.choose}</span><select value={runId} onChange={(event) => setRunId(event.target.value)}>{runs.map((item) => <option key={item.id} value={item.id}>{formatDate(item.created_at, language)} · {item.versions.length} {t.version}</option>)}</select></label>}
      {run && <div className="script-budget"><span>{t.budget}</span><strong>{run.revisions_used}/{run.revision_budget}</strong><span>{t.score}: {run.score_threshold}+</span></div>}
    </section>
    {!run ? <div className="empty-state">{t.noVersion}</div> : !version ? <section className="panel"><p>{t.noVersion}</p><button className="primary-button" disabled={busy !== null} type="button" onClick={() => void generate()}>{busy ?? t.generate}</button></section> : <div className="script-grid">
      <section className="script-preview panel"><div className="list-heading"><h2>{version.content.title}</h2><span>v{version.version_number} · {version.origin}</span></div><p>{version.content.caption}</p><div className="script-sections">{version.content.sections.map((section) => <article key={`${section.start_second}-${section.purpose}`}><header><strong>{section.start_second}–{section.end_second}s</strong><span>{section.purpose}</span></header><p>{section.voiceover}</p><small>{section.on_screen_text}</small><dl><div><dt>{t.evidence}</dt><dd>{section.knowledge_member_ids.length}</dd></div><div><dt>{t.trend}</dt><dd>{section.trend_signal_ids.length}</dd></div></dl></article>)}</div><p className="hashtags">{version.content.hashtags.join(" ")}</p></section>
      <aside className="script-actions"><section className="panel evaluation-card"><h3>{t.score}</h3>{evaluation ? <><strong className={evaluation.passed ? "score-pass" : "score-fail"}>{evaluation.score}/100</strong><span>{evaluation.passed ? t.approved : t.blocked}</span><dl>{Object.entries(evaluation.dimensions).map(([name, value]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{value.score}/{value.max}</dd></div>)}</dl></> : <p>{t.blocked}</p>}<button className="secondary-button" disabled={busy !== null} type="button" onClick={() => void evaluate()}>{busy ?? t.evaluate}</button>{evaluation && !evaluation.passed && <button className="secondary-button" disabled={busy !== null || run.revisions_used >= run.revision_budget} type="button" onClick={() => void revise()}>{t.revise}</button>}</section>
        <details className="panel script-editor"><summary>{t.edit}</summary><textarea aria-label={t.edit} value={editor} onChange={(event) => setEditor(event.target.value)} /><button className="secondary-button" disabled={busy !== null} type="button" onClick={() => void saveEdit()}>{t.saveEdit}</button></details>
        <form className="panel final-review" onSubmit={review}><h3>{t.finalGate}</h3><label><select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}><option value="approve">{t.approve}</option><option value="reject">{t.reject}</option></select></label><label><span>{t.reason}</span><textarea required value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="primary-button" disabled={!evaluation || busy !== null} type="submit">{t.submitReview}</button>{finalReview && <p><strong>{finalReview.decision}</strong> · {finalReview.reason}</p>}</form>
        <section className="panel export-actions"><button className="secondary-button" disabled={finalReview?.decision !== "approve" || busy !== null} type="button" onClick={() => void exportFile("markdown")}>{t.exportMd}</button><button className="secondary-button" disabled={finalReview?.decision !== "approve" || busy !== null} type="button" onClick={() => void exportFile("json")}>{t.exportJson}</button></section>
      </aside>
    </div>}
  </div>;
}
