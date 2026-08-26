import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate, idempotencyKey } from "./client";
import type { Language } from "./client";

type Snapshot = { id: string; version_number: number; member_count: number; published_at: string };
type Task = { id: string; knowledge_snapshot_id: string; knowledge_snapshot_version: number; platform: string; markets: string[]; audience: string; goal: string; output_language: string; duration_seconds: number; candidate_count: number; approved_candidate_id: string | null; created_at: string };
type SignalProcessing = { version: string; normalized_title: string; content_fingerprint_sha256: string; duplicate_of_signal_id: string | null; cluster_key: string; cluster_size: number; freshness: "fresh" | "aging" | "stale" };
type Signal = { id: string; source_name: string; source_url: string; observed_at: string; region: string; signal_type: string; title: string; keywords: string[]; metric_name: string | null; metric_value: number | null; notes: string | null; processing?: SignalProcessing };
type Connector = { key: "gdelt-doc" | "google-news-rss" | "youtube-data" | "tiktok-manual"; name: string; mode: string; available: boolean; requires_secret: boolean; cost: string };
type TopicReview = { id: string; decision: "approve" | "reject" | "defer"; reason: string; reviewer_id: string; created_at: string };
type Candidate = { id: string; trend_signal: Signal; score: number; dimensions: Record<string, { score: number; max: number }>; matched_snapshot_member_ids: string[]; angle: string; hook: string; rationale: string; risks: string[]; rule_version: string; status: "unreviewed" | "approve" | "reject" | "defer"; review_history: TopicReview[] };

const copy = {
  "zh-CN": {
    eyebrow: "MARKETING · M2/M3", title: "用可追溯趋势完成选题，而不是让模型猜热点。", intro: "可从正规公开 API 获取近期候选，也可人工核对 TikTok Creative Center；每条记录都保留真实来源和时间。",
    task: "营销任务", taskHint: "任务冻结知识快照、平台、市场、受众、目标、语言与时长。", snapshot: "知识快照", createTask: "创建营销任务", noSnapshot: "还没有可用知识快照。请先在“知识”中完成审核并发布。",
    signal: "趋势观察", signalHint: "请先在浏览器中人工核对公开趋势页，再如实记录来源、时间、地区与指标。", sourceUrl: "公开来源 URL", observed: "观察时间", region: "地区", type: "类型", trendTitle: "趋势标题 / 标签", keywords: "关键词（逗号分隔）", metricName: "指标名（可选）", metricValue: "指标值（可选）", notes: "核对说明（可选）", addSignal: "记录趋势观察",
    analyze: "运行零成本匹配", candidates: "选题候选", noSignals: "尚未记录趋势观察。", noCandidates: "记录趋势并运行匹配后，这里会显示候选。", deterministic: "确定性规则 · 无模型调用", evidence: "来源证据", dimensions: "评分明细", risks: "风险提示", matched: "匹配知识", noMatch: "未发现词面知识匹配",
    humanGate: "人工选题门", decision: "决定", reason: "决定理由", approve: "批准", reject: "拒绝", defer: "暂缓", record: "记录人工决定", history: "决定历史", selected: "已批准选题", working: "处理中…", chooseTask: "选择任务", refresh: "刷新",
    processing: "确定性清洗", cluster: "同事件", duplicate: "精确重复", freshness: { fresh: "近期", aging: "较旧", stale: "过期" },
    connector: "自动热点来源", connectorHint: "GDELT 无需密钥；YouTube 使用你本机配置的免费 API 配额。系统不会抓取 TikTok。", connectorSource: "来源", query: "检索主题", lookback: "回溯小时", limit: "最多返回", sync: "获取近期热点", unavailableConnector: "未配置", syncResult: "热点同步完成",
  },
  en: {
    eyebrow: "MARKETING · M2/M3", title: "Choose a topic from traceable trends, not model guesses.", intro: "Fetch recent candidates from documented public APIs or manually verify TikTok Creative Center. Every record keeps its real source and time.",
    task: "Marketing task", taskHint: "A task freezes the knowledge snapshot, platform, markets, audience, goal, language, and duration.", snapshot: "Knowledge snapshot", createTask: "Create marketing task", noSnapshot: "No knowledge snapshot is available. Review and publish one in Knowledge first.",
    signal: "Trend observation", signalHint: "Verify a public trend page in your browser, then record its source, time, region, and metric honestly.", sourceUrl: "Public source URL", observed: "Observed at", region: "Region", type: "Type", trendTitle: "Trend title / hashtag", keywords: "Keywords (comma-separated)", metricName: "Metric name (optional)", metricValue: "Metric value (optional)", notes: "Verification note (optional)", addSignal: "Record trend observation",
    analyze: "Run zero-cost fit", candidates: "Topic candidates", noSignals: "No trend observations yet.", noCandidates: "Record trends and run fit analysis to create candidates.", deterministic: "Deterministic rules · no model call", evidence: "Source evidence", dimensions: "Score dimensions", risks: "Risk notes", matched: "Knowledge matches", noMatch: "No lexical knowledge match",
    humanGate: "Human topic gate", decision: "Decision", reason: "Decision reason", approve: "Approve", reject: "Reject", defer: "Defer", record: "Record human decision", history: "Decision history", selected: "Approved topic", working: "Working…", chooseTask: "Choose task", refresh: "Refresh",
    processing: "Deterministic processing", cluster: "Same event", duplicate: "Exact duplicate", freshness: { fresh: "Fresh", aging: "Aging", stale: "Stale" },
    connector: "Automated trend sources", connectorHint: "GDELT needs no key. YouTube uses free API quota configured locally. GameCrafter never scrapes TikTok.", connectorSource: "Source", query: "Search topic", lookback: "Lookback hours", limit: "Maximum results", sync: "Fetch recent trends", unavailableConnector: "Not configured", syncResult: "Trend sync completed",
  },
} as const;

const initialObserved = () => { const date = new Date(); date.setMinutes(date.getMinutes() - date.getTimezoneOffset()); return date.toISOString().slice(0, 16); };
const signalProcessing = (item: Signal): SignalProcessing => item.processing ?? { version: "legacy", normalized_title: item.title.toLocaleLowerCase(), content_fingerprint_sha256: "", duplicate_of_signal_id: null, cluster_key: "legacy", cluster_size: 1, freshness: "fresh" };

export function MarketingWorkspace({ projectId, language }: { projectId: string; language: Language }) {
  const t = copy[language];
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]); const [tasks, setTasks] = useState<Task[]>([]); const [signals, setSignals] = useState<Signal[]>([]); const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]); const [connectorKey, setConnectorKey] = useState<"gdelt-doc" | "google-news-rss" | "youtube-data">("google-news-rss"); const [connectorQuery, setConnectorQuery] = useState("open world games anime RPG"); const [connectorRegion, setConnectorRegion] = useState("US"); const [lookbackHours, setLookbackHours] = useState("24"); const [connectorLimit, setConnectorLimit] = useState("10");
  const [taskId, setTaskId] = useState(""); const [snapshotId, setSnapshotId] = useState(""); const [busy, setBusy] = useState<string | null>(null); const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [sourceUrl, setSourceUrl] = useState(""); const [observedAt, setObservedAt] = useState(initialObserved); const [region, setRegion] = useState("US"); const [signalType, setSignalType] = useState("hashtag"); const [trendTitle, setTrendTitle] = useState(""); const [keywords, setKeywords] = useState(""); const [metricName, setMetricName] = useState(""); const [metricValue, setMetricValue] = useState(""); const [signalNotes, setSignalNotes] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState(""); const [decision, setDecision] = useState<"approve" | "reject" | "defer">("approve"); const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    const [snapshotPayload, taskPayload, signalPayload, connectorPayload] = await Promise.all([
      api<{ items: Snapshot[] }>(`/api/projects/${projectId}/knowledge-snapshots`), api<{ items: Task[] }>(`/api/projects/${projectId}/marketing-tasks`), api<{ items: Signal[] }>(`/api/projects/${projectId}/trend-signals`), api<{ items: Connector[] }>("/api/trend-connectors"),
    ]);
    setSnapshots(snapshotPayload.items); setTasks(taskPayload.items); setSignals(signalPayload.items); setConnectors(connectorPayload.items);
    setSnapshotId((current) => current || snapshotPayload.items[0]?.id || ""); setTaskId((current) => current || taskPayload.items[0]?.id || "");
  }, [projectId]);

  const loadCandidates = useCallback(async () => {
    if (!taskId) { setCandidates([]); return; }
    const payload = await api<{ items: Candidate[] }>(`/api/projects/${projectId}/marketing-tasks/${taskId}/topic-candidates`);
    setCandidates(payload.items); setSelectedCandidateId((current) => payload.items.some((item) => item.id === current) ? current : payload.items[0]?.id || "");
  }, [projectId, taskId]);

  useEffect(() => { void load().catch((error: unknown) => setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) })); }, [load]);
  useEffect(() => { void loadCandidates().catch((error: unknown) => setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) })); }, [loadCandidates]);
  const task = tasks.find((item) => item.id === taskId) ?? null; const selectedCandidate = candidates.find((item) => item.id === selectedCandidateId) ?? null;
  const dimensionEntries = useMemo(() => selectedCandidate ? Object.entries(selectedCandidate.dimensions) : [], [selectedCandidate]);

  const createTask = async () => {
    if (!snapshotId) return; setBusy("task");
    try {
      const item = await api<Task>(`/api/projects/${projectId}/marketing-tasks`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("marketing-task") }, body: JSON.stringify({ knowledge_snapshot_id: snapshotId, platform: "TikTok", markets: ["US", "UK", "CA", "AU", "NZ"], audience: "Potential new players in English-speaking markets", goal: "Build qualified awareness and interest in the game", output_language: "en", duration_seconds: 30 }) });
      await load(); setTaskId(item.id); setNotice({ kind: "ok", text: t.createTask });
    } catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };

  const addSignal = async (event: FormEvent) => {
    event.preventDefault(); setBusy("signal");
    try {
      await api(`/api/projects/${projectId}/trend-signals`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("trend-signal") }, body: JSON.stringify({ source_name: "TikTok Creative Center", source_url: sourceUrl, observed_at: new Date(observedAt).toISOString(), region, signal_type: signalType, title: trendTitle, keywords: keywords.split(",").map((item) => item.trim()).filter(Boolean), metric_name: metricName.trim() || null, metric_value: metricValue.trim() ? Number(metricValue) : null, notes: signalNotes.trim() || null }) });
      setTrendTitle(""); setKeywords(""); await load(); setNotice({ kind: "ok", text: t.addSignal });
    } catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };

  const syncConnector = async (event: FormEvent) => {
    event.preventDefault(); setBusy("connector");
    try {
      const result = await api<{ fetched: number; inserted: number }>(`/api/projects/${projectId}/trend-connectors/${connectorKey}/sync`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("trend-connector") }, body: JSON.stringify({ query: connectorQuery, region: connectorRegion, lookback_hours: Number(lookbackHours), max_results: Number(connectorLimit) }) });
      await load(); setNotice({ kind: "ok", text: `${t.syncResult}: ${result.inserted}/${result.fetched}` });
    } catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };

  const analyze = async () => {
    if (!taskId) return; setBusy("analysis");
    try { const payload = await api<{ items: Candidate[] }>(`/api/projects/${projectId}/marketing-tasks/${taskId}/topic-analysis`, { method: "POST" }); setCandidates(payload.items); setSelectedCandidateId(payload.items[0]?.id || ""); await load(); setNotice({ kind: "ok", text: t.analyze }); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };

  const review = async (event: FormEvent) => {
    event.preventDefault(); if (!taskId || !selectedCandidateId) return; setBusy("review");
    try { await api(`/api/projects/${projectId}/marketing-tasks/${taskId}/topic-candidates/${selectedCandidateId}/reviews`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("topic-review") }, body: JSON.stringify({ decision, reason }) }); setReason(""); await Promise.all([load(), loadCandidates()]); setNotice({ kind: "ok", text: t.record }); }
    catch (error) { setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }); } finally { setBusy(null); }
  };

  return <div className="marketing-workspace">
    <section className="marketing-intro"><div><p className="eyebrow">{t.eyebrow}</p><h2>{t.title}</h2><p>{t.intro}</p></div><button className="ghost-button" type="button" onClick={() => void load()}>{t.refresh}</button></section>
    {notice && <div className={`notice notice--${notice.kind}`} role="status">{notice.text}</div>}
    <div className="marketing-setup-grid">
      <section className="panel"><div className="panel-heading"><span>01</span><div><h2>{t.task}</h2><p>{t.taskHint}</p></div></div>
        {snapshots.length === 0 ? <div className="empty-state">{t.noSnapshot}</div> : <><label><span>{t.snapshot}</span><select value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)}>{snapshots.map((item) => <option key={item.id} value={item.id}>v{item.version_number} · {item.member_count} facts</option>)}</select></label><button className="primary-button" type="button" disabled={busy !== null} onClick={() => void createTask()}>{busy === "task" ? t.working : t.createTask}</button></>}
        {tasks.length > 0 && <label><span>{t.chooseTask}</span><select value={taskId} onChange={(event) => setTaskId(event.target.value)}>{tasks.map((item) => <option key={item.id} value={item.id}>TikTok · v{item.knowledge_snapshot_version} · {formatDate(item.created_at, language)}</option>)}</select></label>}
        {task && <dl className="task-summary"><div><dt>Markets</dt><dd>{task.markets.join(" · ")}</dd></div><div><dt>Output</dt><dd>{task.duration_seconds}s · {task.output_language}</dd></div><div><dt>Status</dt><dd>{task.approved_candidate_id ? t.selected : `${task.candidate_count} candidates`}</dd></div></dl>}
      </section>
      <form className="panel" onSubmit={syncConnector}><div className="panel-heading"><span>02</span><div><h2>{t.connector}</h2><p>{t.connectorHint}</p></div></div><div className="form-grid marketing-form-grid">
        <label><span>{t.connectorSource}</span><select value={connectorKey} onChange={(event) => setConnectorKey(event.target.value as typeof connectorKey)}>{connectors.filter((item) => item.key !== "tiktok-manual").map((item) => <option key={item.key} value={item.key} disabled={!item.available}>{item.name}{item.available ? "" : ` · ${t.unavailableConnector}`}</option>)}</select></label><label><span>{t.query}</span><input required minLength={2} maxLength={160} value={connectorQuery} onChange={(event) => setConnectorQuery(event.target.value)} /></label><label><span>{t.region}</span><input required pattern="[A-Za-z]{2}" maxLength={2} value={connectorRegion} onChange={(event) => setConnectorRegion(event.target.value.toUpperCase())} /></label><label><span>{t.lookback}</span><input required type="number" min="1" max="168" value={lookbackHours} onChange={(event) => setLookbackHours(event.target.value)} /></label><label><span>{t.limit}</span><input required type="number" min="1" max="50" value={connectorLimit} onChange={(event) => setConnectorLimit(event.target.value)} /></label>
      </div><button className="primary-button" type="submit" disabled={busy !== null || !connectors.find((item) => item.key === connectorKey)?.available}>{busy === "connector" ? t.working : t.sync}</button></form>
      <form className="panel" onSubmit={addSignal}><div className="panel-heading"><span>03</span><div><h2>{t.signal}</h2><p>{t.signalHint}</p></div></div><div className="form-grid marketing-form-grid">
        <label className="span-two"><span>{t.sourceUrl}</span><input required type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://ads.tiktok.com/business/creativecenter/…" /></label><label><span>{t.observed}</span><input required type="datetime-local" value={observedAt} onChange={(event) => setObservedAt(event.target.value)} /></label><label><span>{t.region}</span><input required maxLength={80} value={region} onChange={(event) => setRegion(event.target.value)} /></label><label><span>{t.type}</span><select value={signalType} onChange={(event) => setSignalType(event.target.value)}><option value="hashtag">Hashtag</option><option value="sound">Sound</option><option value="topic">Topic</option><option value="search">Search</option></select></label><label><span>{t.trendTitle}</span><input required maxLength={300} value={trendTitle} onChange={(event) => setTrendTitle(event.target.value)} /></label><label className="span-two"><span>{t.keywords}</span><input value={keywords} onChange={(event) => setKeywords(event.target.value)} /></label><label><span>{t.metricName}</span><input value={metricName} onChange={(event) => setMetricName(event.target.value)} /></label><label><span>{t.metricValue}</span><input min="0" type="number" value={metricValue} onChange={(event) => setMetricValue(event.target.value)} /></label><label className="span-two"><span>{t.notes}</span><textarea value={signalNotes} onChange={(event) => setSignalNotes(event.target.value)} /></label>
      </div><button className="primary-button" type="submit" disabled={busy !== null}>{busy === "signal" ? t.working : t.addSignal}</button></form>
    </div>
    <section className="trend-ledger"><div className="list-heading"><h2>{t.signal}</h2><span>{signals.length}</span></div>{signals.length === 0 ? <div className="empty-state">{t.noSignals}</div> : <div className="signal-grid">{signals.map((item) => { const processing = signalProcessing(item); return <article className={`signal-card signal-card--${processing.freshness}`} key={item.id}><div className="card-meta"><span>{item.region}</span><span>{item.signal_type}</span><span>{t.freshness[processing.freshness]}</span>{processing.cluster_size > 1 && <span>{t.cluster} × {processing.cluster_size}</span>}{processing.duplicate_of_signal_id && <span>{t.duplicate}</span>}</div><h3>{item.title}</h3><a href={item.source_url} target="_blank" rel="noreferrer">{item.source_name}</a><p>{item.metric_name ? `${item.metric_name}: ${item.metric_value}` : "Metric not recorded"}</p><details><summary>{t.processing} · {processing.version}</summary><code>{processing.normalized_title} · {processing.cluster_key}</code></details></article>; })}</div>}<button className="secondary-button" type="button" disabled={!taskId || !signals.length || busy !== null} onClick={() => void analyze()}>{busy === "analysis" ? t.working : t.analyze}</button></section>
    <section className="topic-workbench"><div className="list-heading"><h2>{t.candidates}</h2><span>{candidates.length}</span></div>{candidates.length === 0 ? <div className="empty-state">{t.noCandidates}</div> : <div className="topic-grid"><div className="topic-list">{candidates.map((item) => <button type="button" key={item.id} className={selectedCandidateId === item.id ? "topic-card active" : "topic-card"} onClick={() => setSelectedCandidateId(item.id)}><span className="topic-score">{item.score}</span><div><strong>{item.trend_signal.title}</strong><p>{item.angle}</p><small>{item.status} · {item.rule_version}</small></div></button>)}</div>
      {selectedCandidate && <article className="topic-detail"><div className="policy-banner"><strong>{t.deterministic}</strong><span>{selectedCandidate.rule_version}</span></div><h3>{selectedCandidate.hook}</h3><p>{selectedCandidate.rationale}</p><a href={selectedCandidate.trend_signal.source_url} target="_blank" rel="noreferrer">{t.evidence}: {selectedCandidate.trend_signal.source_name}</a><h4>{t.dimensions}</h4><dl className="score-grid">{dimensionEntries.map(([name, value]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{value.score}/{value.max}</dd></div>)}</dl><h4>{t.matched}</h4><p>{selectedCandidate.matched_snapshot_member_ids.length ? `${selectedCandidate.matched_snapshot_member_ids.length} snapshot members` : t.noMatch}</p><h4>{t.risks}</h4><ul>{selectedCandidate.risks.map((risk) => <li key={risk}>{risk.replaceAll("_", " ")}</li>)}</ul>
        <form className="topic-review-form" onSubmit={review}><h4>{t.humanGate}</h4><label><span>{t.decision}</span><select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}><option value="approve">{t.approve}</option><option value="reject">{t.reject}</option><option value="defer">{t.defer}</option></select></label><label><span>{t.reason}</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="primary-button" type="submit" disabled={busy !== null}>{busy === "review" ? t.working : t.record}</button></form>
        {selectedCandidate.review_history.length > 0 && <div className="topic-history"><h4>{t.history}</h4>{[...selectedCandidate.review_history].reverse().map((item) => <div key={item.id}><strong>{item.decision}</strong><span>{formatDate(item.created_at, language)}</span><p>{item.reason}</p></div>)}</div>}
      </article>}
    </div>}</section>
  </div>;
}
