import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate, idempotencyKey } from "./client";
import type { Language } from "./client";

type SourceVersion = { id: string; title: string; source_type: string; version_number: number; fetched_at: string };
type Chapter = { id: string; parent_chapter_id: string | null; ordinal: number; heading_level: number; title: string; start_offset: number; end_offset: number; content: string; content_sha256: string };
type Assumption = { id: string; chapter_id: string | null; statement: string; rationale: string; status: "proposed" | "approved" | "rejected"; decision_reason: string | null; created_at: string };
type Revision = { id: string; revision_number: number; content_sha256: string; notes: string | null; approved_by: string; created_at: string };
type DocumentSummary = { id: string; source_version_id: string; title: string; status: "draft" | "approved"; parser_version: string; chapter_count: number; assumption_count: number; revision_count: number; updated_at: string };
type DocumentDetail = DocumentSummary & { chapters: Chapter[]; assumptions: Assumption[]; revisions: Revision[] };

const copy = {
  "zh-CN": {
    title: "GDD 工作台", hint: "把你拥有的私有 GDD 拆成可追溯章节。事实、设计假设与审核版本严格分开。",
    source: "私有 GDD 证据版本", structure: "建立章节结构", noSource: "请先在“来源”中导入类型为 GDD 的 Markdown 或文本。",
    documents: "GDD 文档", noDocument: "尚未建立结构化 GDD。", chapters: "原文章节", assumptions: "设计假设", history: "审核版本",
    exact: "原文位置", statement: "假设内容", rationale: "为什么提出这项假设", chapter: "关联章节（可选）", propose: "提出假设",
    approve: "认可为设计假设", reject: "驳回", reason: "审核理由", revisionNotes: "版本说明", publish: "批准新版本",
    unresolved: "仍有待审核假设，全部决定后才能批准版本。", private: "仅保存在本机；设计假设不会进入事实知识库。", working: "处理中…",
  },
  en: {
    title: "GDD Studio", hint: "Structure a GDD you own into traceable chapters. Sourced text, design assumptions, and reviewed revisions remain separate.",
    source: "Private GDD evidence version", structure: "Structure chapters", noSource: "Import a Markdown or text source with type GDD in Sources first.",
    documents: "GDD documents", noDocument: "No structured GDD yet.", chapters: "Source chapters", assumptions: "Design assumptions", history: "Reviewed revisions",
    exact: "Source offsets", statement: "Assumption", rationale: "Why this assumption is useful", chapter: "Related chapter (optional)", propose: "Propose assumption",
    approve: "Approve as assumption", reject: "Reject", reason: "Decision reason", revisionNotes: "Revision notes", publish: "Approve new revision",
    unresolved: "Decide every proposed assumption before approving a revision.", private: "Stored locally only; assumptions never enter the factual knowledge base.", working: "Working…",
  },
} as const;

export function GddWorkspace({ projectId, language }: { projectId: string; language: Language }) {
  const t = copy[language];
  const [versions, setVersions] = useState<SourceVersion[]>([]); const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [sourceVersionId, setSourceVersionId] = useState(""); const [documentId, setDocumentId] = useState(""); const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [chapterId, setChapterId] = useState(""); const [statement, setStatement] = useState(""); const [rationale, setRationale] = useState(""); const [decisionReasons, setDecisionReasons] = useState<Record<string, string>>({}); const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<string | null>(null); const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const gddVersions = useMemo(() => versions.filter((item) => item.source_type === "gdd"), [versions]);

  const load = useCallback(async () => {
    const [sourcePayload, documentPayload] = await Promise.all([
      api<{ items: SourceVersion[] }>(`/api/projects/${projectId}/source-versions`),
      api<{ items: DocumentSummary[] }>(`/api/projects/${projectId}/gdd/documents`),
    ]);
    setVersions(sourcePayload.items); setDocuments(documentPayload.items);
    setSourceVersionId((current) => current || sourcePayload.items.find((item) => item.source_type === "gdd")?.id || "");
    setDocumentId((current) => current || documentPayload.items[0]?.id || "");
  }, [projectId]);
  const loadDocument = useCallback(async () => {
    if (!documentId) { setDocument(null); return; }
    setDocument(await api<DocumentDetail>(`/api/projects/${projectId}/gdd/documents/${documentId}`));
  }, [documentId, projectId]);
  useEffect(() => { void load().catch((error) => setNotice({ kind: "error", text: String(error) })); }, [load]);
  useEffect(() => { void loadDocument().catch((error) => setNotice({ kind: "error", text: String(error) })); }, [loadDocument]);

  const structure = async () => {
    if (!sourceVersionId) return; setBusy("structure");
    try { const created = await api<DocumentDetail>(`/api/projects/${projectId}/gdd/documents`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_version_id: sourceVersionId }) }); await load(); setDocumentId(created.id); setDocument(created); setNotice({ kind: "ok", text: `${t.chapters}: ${created.chapter_count}` }); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };
  const propose = async (event: FormEvent) => {
    event.preventDefault(); if (!documentId) return; setBusy("assumption");
    try { await api(`/api/projects/${projectId}/gdd/documents/${documentId}/assumptions`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("gdd-assumption") }, body: JSON.stringify({ chapter_id: chapterId || null, statement, rationale }) }); setStatement(""); setRationale(""); await loadDocument(); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };
  const decide = async (assumptionId: string, decision: "approved" | "rejected") => {
    const reason = decisionReasons[assumptionId]?.trim(); if (!reason) return; setBusy(assumptionId);
    try { await api(`/api/projects/${projectId}/gdd/documents/${documentId}/assumptions/${assumptionId}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, reason }) }); setDecisionReasons((current) => { const next = { ...current }; delete next[assumptionId]; return next; }); await loadDocument(); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };
  const publish = async () => {
    if (!documentId) return; setBusy("revision");
    try { await api(`/api/projects/${projectId}/gdd/documents/${documentId}/revisions`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("gdd-revision") }, body: JSON.stringify({ notes: notes || null }) }); setNotes(""); await Promise.all([load(), loadDocument()]); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };
  const unresolved = document?.assumptions.some((item) => item.status === "proposed") ?? false;

  return <div className="knowledge-workspace gdd-workspace">
    {notice && <div className={`notice notice--${notice.kind}`}>{notice.text}</div>}
    <section className="panel"><div className="panel-heading"><span>01</span><div><h2>{t.title}</h2><p>{t.hint}</p></div></div><p>{t.private}</p>
      {gddVersions.length === 0 ? <div className="empty-state">{t.noSource}</div> : <div className="form-grid"><label><span>{t.source}</span><select value={sourceVersionId} onChange={(event) => setSourceVersionId(event.target.value)}>{gddVersions.map((item) => <option key={item.id} value={item.id}>{item.title} · v{item.version_number}</option>)}</select></label><button className="primary-button" type="button" disabled={busy !== null} onClick={() => void structure()}>{busy === "structure" ? t.working : t.structure}</button></div>}
    </section>
    <section className="panel"><div className="list-heading"><h2>{t.documents}</h2><span>{documents.length}</span></div>{documents.length === 0 ? <div className="empty-state">{t.noDocument}</div> : <select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>{documents.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.status} · r{item.revision_count}</option>)}</select>}</section>
    {document && <><section className="list-section"><div className="list-heading"><h2>{t.chapters}</h2><span>{document.chapters.length}</span></div>{document.chapters.map((item) => <article className="source-card" key={item.id}><div><h3 style={{ paddingLeft: `${(item.heading_level - 1) * 16}px` }}>{item.title}</h3><small>{t.exact}: {item.start_offset}–{item.end_offset} · {item.content_sha256.slice(0, 12)}</small><p>{item.content}</p></div></article>)}</section>
      <form className="panel" onSubmit={propose}><div className="list-heading"><h2>{t.assumptions}</h2><span>{document.assumptions.length}</span></div><div className="form-grid"><label><span>{t.chapter}</span><select value={chapterId} onChange={(event) => setChapterId(event.target.value)}><option value="">—</option>{document.chapters.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label><span>{t.statement}</span><textarea required value={statement} onChange={(event) => setStatement(event.target.value)} /></label><label><span>{t.rationale}</span><textarea required value={rationale} onChange={(event) => setRationale(event.target.value)} /></label><button className="primary-button" disabled={busy !== null} type="submit">{busy === "assumption" ? t.working : t.propose}</button></div>
        {document.assumptions.map((item) => { const itemReason = decisionReasons[item.id] ?? ""; return <article className="candidate-card" key={item.id}><div className="card-meta"><span>{item.status}</span><span>{formatDate(item.created_at, language)}</span></div><h3>{item.statement}</h3><p>{item.rationale}</p>{item.status === "proposed" && <><label><span>{t.reason}</span><input value={itemReason} onChange={(event) => setDecisionReasons((current) => ({ ...current, [item.id]: event.target.value }))} /></label><div className="review-actions"><button type="button" disabled={!itemReason.trim() || busy !== null} onClick={() => void decide(item.id, "approved")}>{t.approve}</button><button type="button" disabled={!itemReason.trim() || busy !== null} onClick={() => void decide(item.id, "rejected")}>{t.reject}</button></div></>}</article>; })}
      </form>
      <section className="panel"><div className="list-heading"><h2>{t.history}</h2><span>{document.revisions.length}</span></div>{unresolved && <div className="notice notice--error">{t.unresolved}</div>}<label><span>{t.revisionNotes}</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label><button className="primary-button" type="button" disabled={busy !== null || unresolved || document.chapters.length === 0} onClick={() => void publish()}>{busy === "revision" ? t.working : t.publish}</button>{document.revisions.map((item) => <article className="source-card" key={item.id}><strong>r{item.revision_number}</strong><small>{formatDate(item.created_at, language)} · {item.content_sha256}</small><p>{item.notes || "—"}</p></article>)}</section></>}
  </div>;
}
