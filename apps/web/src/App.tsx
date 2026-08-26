import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AccountWorkspace } from "./AccountWorkspace";
import type { AuthStatus } from "./AccountWorkspace";
import { api, formatDate, idempotencyKey } from "./client";
import type { Language } from "./client";
import { KnowledgeWorkspace } from "./KnowledgeWorkspace";
import { GddWorkspace } from "./GddWorkspace";
import { MarketingWorkspace } from "./MarketingWorkspace";
import { ProjectJourney } from "./ProjectJourney";
import { ScriptWorkspace } from "./ScriptWorkspace";
import type { WorkspaceAuditEvent, WorkspaceRun } from "./KnowledgeWorkspace";

type Tab = "sources" | "knowledge" | "gdd" | "marketing" | "scripts" | "runs" | "account";
type Project = { id: string; slug: string; name: string; default_locale: Language };
type Candidate = {
  id: string;
  title: string;
  url: string;
  site: string;
  locale: string;
  region: string;
  source_type: string;
  published_at: string | null;
  classification_basis: string;
  status: "discovered" | "selected" | "imported" | "skipped";
};
type Source = {
  id: string;
  url: string;
  site: string;
  locale: string;
  region: string;
  source_type: string;
  status: string;
  version_count: number;
  asset_count: number;
  latest_version: number | null;
  updated_at: string;
};
type Run = WorkspaceRun;
type AuditEvent = WorkspaceAuditEvent;

const copy = {
  "zh-CN": {
    sources: "来源",
    knowledge: "知识",
    gdd: "GDD",
    marketing: "营销",
    scripts: "创作",
    runs: "运行记录",
    account: "账户与团队",
    createNte: "创建《异环》项目",
    emptyProject: "先创建本地《异环》验证项目，再开始采集官方公开资料。",
    evidenceNotice: "公开官网资料是可追溯证据，不等同于游戏公司的内部 GDD。",
    quick: "快速发现",
    quickHint: "首次使用只需点击“异环国际服 · 英文（推荐）”。成功后在右侧确认候选，再导入来源。不会递归抓取整站。",
    advanced: "高级方式",
    targeted: "定向发现",
    direct: "直接导入官方页面",
    local: "导入本地资料",
    localHint: "文本、Markdown、字幕转录稿或你拥有的 GDD 只保存在本机，不会发送到外部模型。",
    localKind: "资料类型",
    localTitle: "资料标题",
    localKey: "稳定标识",
    localFile: "选择文件",
    localContent: "文本内容",
    localPrivate: "本地私有资料",
    localImported: "本地资料已保存为不可变证据版本。",
    import: "导入",
    extract: "知识提取",
    discover: "开始发现",
    candidates: "待选候选",
    captured: "已保存来源",
    selectImport: "选择并导入",
    noCandidates: "暂无待选候选。先运行一次来源发现。",
    noSources: "尚未保存来源。候选必须经你确认后才会采集。",
    noRuns: "暂无运行记录。",
    timeline: "审计时间线",
    selectRun: "选择一条运行记录查看可恢复的实时进度。",
    refresh: "刷新",
    language: "English",
    loadingProject: "正在连接本地项目与数据库…",
    apiDown: "本地 API 暂不可用",
    retry: "重试连接",
    retryRun: "问题修复后重新运行",
    working: "正在提交…",
    queued: "任务已进入本地队列",
    failed: "操作失败",
    project: "当前项目",
    profile: "官方站点",
    category: "栏目",
    pages: "列表页数量",
    limit: "候选上限",
    dateFrom: "起始日期",
    dateTo: "结束日期",
    url: "官方页面 URL",
    allTypes: "全部内容类型",
    versions: "证据版本",
    assets: "素材",
    latest: "最新版本",
    status: "状态",
    checkpoint: "检查点",
    error: "需要人工关注",
    privacy: "本地私有存储 · 零付费 API",
  },
  en: {
    sources: "Sources",
    knowledge: "Knowledge",
    gdd: "GDD",
    marketing: "Marketing",
    scripts: "Create",
    runs: "Runs",
    account: "Account & teams",
    createNte: "Create NTE project",
    emptyProject: "Create the local NTE validation project before collecting public official sources.",
    evidenceNotice: "Public official material is traceable evidence, not the studio's internal GDD.",
    quick: "Quick discovery",
    quickHint: "For the first run, click “NTE Global · English (recommended)”. Review the candidates on the right, then import one. The site is never crawled recursively.",
    advanced: "Advanced",
    targeted: "Targeted discovery",
    direct: "Import an official page",
    local: "Import local material",
    localHint: "Text, Markdown, transcript, or your own GDD stays on this machine and is never sent to an external model.",
    localKind: "Material type",
    localTitle: "Title",
    localKey: "Stable key",
    localFile: "Choose file",
    localContent: "Text content",
    localPrivate: "Private local material",
    localImported: "Local material was saved as an immutable evidence version.",
    import: "Import",
    extract: "Knowledge extraction",
    discover: "Discover",
    candidates: "Candidates for review",
    captured: "Saved sources",
    selectImport: "Select and import",
    noCandidates: "No candidates yet. Run source discovery first.",
    noSources: "No saved sources. Capture starts only after your approval.",
    noRuns: "No runs yet.",
    timeline: "Audit timeline",
    selectRun: "Select a run to view its resumable live progress.",
    refresh: "Refresh",
    language: "简体中文",
    loadingProject: "Connecting to the local project and database…",
    apiDown: "Local API is unavailable",
    retry: "Retry",
    retryRun: "Run again after fixing",
    working: "Submitting…",
    queued: "Task added to the local queue",
    failed: "Action failed",
    project: "Project",
    profile: "Official site",
    category: "Category",
    pages: "Listing pages",
    limit: "Candidate limit",
    dateFrom: "From",
    dateTo: "To",
    url: "Official page URL",
    allTypes: "All content types",
    versions: "Evidence versions",
    assets: "Assets",
    latest: "Latest",
    status: "Status",
    checkpoint: "Checkpoint",
    error: "Needs attention",
    privacy: "Private local storage · zero paid APIs",
  },
} as const;

const quickProfiles = [
  {
    id: "global-en",
    labelZh: "异环国际服 · 英文（推荐）",
    labelEn: "NTE Global · English (recommended)",
    url: "https://nte.perfectworld.com/en/article/news/index.html",
  },
  {
    id: "global-cn",
    labelZh: "异环国际服 · 中文",
    labelEn: "NTE Global · Chinese",
    url: "https://nte.perfectworld.com/cn/article/news/index.html",
  },
  {
    id: "global-jp",
    labelZh: "异环国际服 · 日文",
    labelEn: "NTE Global · Japanese",
    url: "https://nte.perfectworld.com/jp/article/news/index.html",
  },
  {
    id: "mainland-cn",
    labelZh: "异环中国大陆服 · 中文",
    labelEn: "NTE Mainland China · Chinese",
    url: "https://yh.wanmei.com/news/index.html",
  },
] as const;

function targetUrls(site: string, category: string, pages: number): string[] {
  const urls: string[] = [];
  for (let page = 1; page <= pages; page += 1) {
    const suffix = page === 1 ? "index.html" : `index${page}.html`;
    if (site === "mainland-cn") {
      urls.push(`https://yh.wanmei.com/news/${category}/${suffix}`);
    } else {
      urls.push(`https://nte.perfectworld.com/${site}/article/news/${category}/${suffix}`);
    }
  }
  return urls;
}

export function App() {
  const [language, setLanguage] = useState<Language>(() => {
    const saved = localStorage.getItem("gamecrafter-language");
    return saved === "en" ? "en" : "zh-CN";
  });
  const [tab, setTab] = useState<Tab>("sources");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [directUrl, setDirectUrl] = useState("");
  const [localKind, setLocalKind] = useState<"document" | "transcript" | "gdd">("document");
  const [localTitle, setLocalTitle] = useState("");
  const [localKey, setLocalKey] = useState("");
  const [localFilename, setLocalFilename] = useState("notes.txt");
  const [localContent, setLocalContent] = useState("");
  const [localMediaType, setLocalMediaType] = useState<"text/plain" | "text/markdown" | "text/vtt" | "application/json">("text/plain");
  const [targetSite, setTargetSite] = useState("en");
  const [targetCategory, setTargetCategory] = useState("gamenews");
  const [targetPages, setTargetPages] = useState(1);
  const [targetLimit, setTargetLimit] = useState(50);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [knowledgeRefreshToken, setKnowledgeRefreshToken] = useState(0);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const t = copy[language];

  const loadProjects = useCallback(async () => {
    try {
      await api("/api/health");
      const payload = await api<{ items: Project[] }>("/api/projects");
      setProjects(payload.items);
      setProjectId((current) =>
        payload.items.some((project) => project.id === current)
          ? current
          : (payload.items[0]?.id ?? ""),
      );
      setConnected(true);
    } catch {
      setAuthStatus({ enabled: false, bootstrap_required: false, user: null, zero_cost: true });
      setConnected(false);
    }
  }, []);

  const refreshAuth = useCallback(async () => {
    try {
      const value = await api<AuthStatus>("/api/auth/status");
      setAuthStatus(value);
      if (!value.enabled || value.user) await loadProjects();
    } catch {
      setAuthStatus({ enabled: false, bootstrap_required: false, user: null, zero_cost: true });
      setConnected(false);
    }
  }, [loadProjects]);

  const refreshWorkspace = useCallback(async () => {
    if (!projectId) return;
    try {
      const [candidatePayload, sourcePayload, runPayload] = await Promise.all([
        api<{ items: Candidate[] }>(`/api/projects/${projectId}/candidates`),
        api<{ items: Source[] }>(`/api/projects/${projectId}/sources`),
        api<{ items: Run[] }>(`/api/projects/${projectId}/runs`),
      ]);
      setCandidates(candidatePayload.items);
      setSources(sourcePayload.items);
      setRuns(runPayload.items);
      setConnected(true);
    } catch (error) {
      setMessage({
        kind: "error",
        text: error instanceof Error ? error.message : t.failed,
      });
    }
  }, [projectId, t.failed]);

  useEffect(() => {
    void refreshAuth();
  }, [refreshAuth]);

  useEffect(() => {
    void refreshWorkspace();
  }, [refreshWorkspace]);

  useEffect(() => {
    const hasActiveRun = runs.some((run) =>
      ["queued", "running", "retry_wait"].includes(run.status),
    );
    if (!hasActiveRun) return;
    const timer = globalThis.setInterval(() => {
      void refreshWorkspace();
    }, 2000);
    return () => globalThis.clearInterval(timer);
  }, [runs, refreshWorkspace]);

  useEffect(() => {
    if (!selectedRun) {
      setEvents([]);
      return;
    }
    setEvents([]);
    const stream = new EventSource(`/api/runs/${selectedRun}/events`);
    stream.addEventListener("audit", (raw) => {
      const event = raw as MessageEvent<string>;
      try {
        const parsed = JSON.parse(event.data) as AuditEvent;
        setEvents((current) =>
          current.some((item) => item.id === parsed.id) ? current : [...current, parsed],
        );
        void refreshWorkspace();
      } catch {
        setMessage({ kind: "error", text: "Invalid run event payload" });
      }
    });
    stream.onerror = () => {
      stream.close();
      void refreshWorkspace();
    };
    return () => stream.close();
  }, [selectedRun, refreshWorkspace]);

  const selectedRunRecord = useMemo(
    () => runs.find((run) => run.id === selectedRun) ?? null,
    [runs, selectedRun],
  );
  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId) ?? null,
    [projects, projectId],
  );

  const toggleLanguage = () => {
    const next = language === "zh-CN" ? "en" : "zh-CN";
    localStorage.setItem("gamecrafter-language", next);
    setLanguage(next);
  };

  const createProject = async () => {
    setBusy("project");
    setMessage(null);
    try {
      const project = await api<Project>("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: "nte", name: "异环", default_locale: "zh-CN" }),
      });
      await loadProjects();
      setProjectId(project.id);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const submitRun = async (path: string, body: object, key: string) => {
    if (!projectId) {
      setConnected(false);
      return;
    }
    setBusy(key);
    setMessage(null);
    try {
      const run = await api<Run>(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey(key),
        },
        body: JSON.stringify(body),
      });
      setMessage({ kind: "ok", text: t.queued });
      setSelectedRun(run.id);
      setTab("runs");
      await refreshWorkspace();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : t.failed });
    } finally {
      setBusy(null);
    }
  };

  const quickDiscover = (profile: (typeof quickProfiles)[number]) =>
    submitRun(
      `/api/projects/${projectId}/source-discoveries`,
      { mode: "quick", listing_urls: [profile.url], candidate_limit: 30, source_types: [] },
      `quick-${profile.id}`,
    );

  const targetedDiscover = (event: FormEvent) => {
    event.preventDefault();
    const body: Record<string, unknown> = {
      mode: "targeted",
      listing_urls: targetUrls(targetSite, targetCategory, targetPages),
      candidate_limit: targetLimit,
      source_types: [],
    };
    if (dateFrom) body.published_from = `${dateFrom}T00:00:00Z`;
    if (dateTo) body.published_to = `${dateTo}T23:59:59Z`;
    void submitRun(`/api/projects/${projectId}/source-discoveries`, body, "targeted");
  };

  const importDirect = (event: FormEvent) => {
    event.preventDefault();
    void submitRun(`/api/projects/${projectId}/source-imports`, { url: directUrl }, "direct");
  };

  const chooseLocalFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    const mediaType = extension === "md" ? "text/markdown" : extension === "vtt" ? "text/vtt" : extension === "json" ? "application/json" : "text/plain";
    setLocalFilename(file.name);
    setLocalTitle((current) => current || file.name.replace(/\.[^.]+$/, ""));
    setLocalKey(
      (current) =>
        current ||
        file.name
          .toLowerCase()
          .replace(/\.[^.]+$/, "")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "") ||
        `local-${Date.now()}`,
    );
    setLocalMediaType(mediaType);
    if (extension === "vtt") setLocalKind("transcript");
    setLocalContent(await file.text());
  };

  const importLocal = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("local");
    setMessage(null);
    try {
      await api(`/api/projects/${projectId}/local-sources`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("local-source"),
        },
        body: JSON.stringify({
          document_key: localKey,
          kind: localKind,
          title: localTitle,
          filename: localFilename,
          content: localContent,
          media_type: localMediaType,
          locale: "en",
          region: "private",
        }),
      });
      setLocalContent("");
      await refreshWorkspace();
      setKnowledgeRefreshToken((current) => current + 1);
      setMessage({ kind: "ok", text: t.localImported });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  };

  const importCandidate = (candidate: Candidate) =>
    submitRun(
      `/api/projects/${projectId}/source-imports`,
      { candidate_id: candidate.id },
      `candidate-${candidate.id}`,
    );

  const acceptKnowledgeRun = (run: Run) => {
    setSelectedRun(run.id);
    setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
    void refreshWorkspace();
  };

  const refreshAll = () => {
    setKnowledgeRefreshToken((current) => current + 1);
    void refreshWorkspace();
  };

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">G</span>
          <div><strong>GameCrafter</strong><small>Knowledge + Marketing Studio</small></div>
        </div>
        <div className="top-actions">
          <span className="privacy-note">{t.privacy}</span>
          <button className="ghost-button" type="button" onClick={toggleLanguage}>
            {t.language}
          </button>
        </div>
      </header>

      {authStatus === null ? (
        <section className="center-state" aria-live="polite">
          <span className="status-dot" />
          <h1>{t.loadingProject}</h1>
        </section>
      ) : authStatus.enabled && !authStatus.user ? (
        <AccountWorkspace status={authStatus} language={language} gate onChanged={refreshAuth} />
      ) : connected === null ? (
        <section className="center-state" aria-live="polite">
          <span className="status-dot" />
          <h1>{t.loadingProject}</h1>
        </section>
      ) : connected === false ? (
        <section className="center-state" aria-live="polite">
          <span className="status-dot status-dot--error" />
          <h1>{t.apiDown}</h1>
          <button className="primary-button" type="button" onClick={() => void loadProjects()}>
            {t.retry}
          </button>
        </section>
      ) : (
        <>
          <section className="workspace-heading">
            <div>
              <p className="eyebrow">Game Knowledge Hub</p>
              <h1>{language === "zh-CN" ? "把公开资料变成可复核的游戏知识。" : "Turn public material into reviewable game knowledge."}</h1>
              <p>{t.evidenceNotice}</p>
            </div>
            {projects.length > 0 && (
              <label className="project-picker">
                <span>{t.project}</span>
                <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
                  {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                </select>
              </label>
            )}
          </section>

          {projects.length === 0 && connected ? (
            <section className="empty-project">
              <h2>{t.emptyProject}</h2>
              <button className="primary-button" type="button" disabled={busy !== null} onClick={() => void createProject()}>
                {busy === "project" ? t.working : t.createNte}
              </button>
            </section>
          ) : (
            <>
              <ProjectJourney
                projectId={projectId}
                language={language}
                refreshToken={knowledgeRefreshToken}
                onNavigate={setTab}
              />
              <nav className="tabs" aria-label="Workspace">
                <button className={tab === "sources" ? "active" : ""} type="button" onClick={() => setTab("sources")}>
                  {t.sources}<span>{sources.length}</span>
                </button>
                <button className={tab === "knowledge" ? "active" : ""} type="button" onClick={() => setTab("knowledge")}>
                  {t.knowledge}
                </button>
                <button className={tab === "gdd" ? "active" : ""} type="button" onClick={() => setTab("gdd")}>
                  {t.gdd}
                </button>
                <button className={tab === "marketing" ? "active" : ""} type="button" onClick={() => setTab("marketing")}>
                  {t.marketing}
                </button>
                <button className={tab === "scripts" ? "active" : ""} type="button" onClick={() => setTab("scripts")}>
                  {t.scripts}
                </button>
                <button className={tab === "runs" ? "active" : ""} type="button" onClick={() => setTab("runs")}>
                  {t.runs}<span>{runs.length}</span>
                </button>
                <button className={tab === "account" ? "active" : ""} type="button" onClick={() => setTab("account")}>
                  {t.account}
                </button>
                <button className="refresh-button" type="button" onClick={refreshAll}>{t.refresh}</button>
              </nav>

              {message && <div className={`notice notice--${message.kind}`} role="status">{message.text}</div>}

              {tab === "sources" ? (
                <div className="source-layout">
                  <aside className="control-stack">
                    <section className="panel">
                      <div className="panel-heading"><span>01</span><div><h2>{t.quick}</h2><p>{t.quickHint}</p></div></div>
                      <div className="profile-grid">
                        {quickProfiles.map((profile) => (
                          <button key={profile.id} type="button" disabled={busy !== null} onClick={() => void quickDiscover(profile)}>
                            <span>{language === "zh-CN" ? profile.labelZh : profile.labelEn}</span><small>{busy === `quick-${profile.id}` ? t.working : t.discover}</small>
                          </button>
                        ))}
                      </div>
                    </section>

                    <details className="panel advanced-panel">
                      <summary><span>02</span><strong>{t.targeted}</strong><small>{t.advanced}</small></summary>
                      <form className="advanced-form" onSubmit={targetedDiscover}>
                        <div className="form-grid">
                        <label><span>{t.profile}</span><select value={targetSite} onChange={(e) => setTargetSite(e.target.value)}>
                          <option value="en">Global · EN</option><option value="cn">Global · 中文</option>
                          <option value="jp">Global · 日本語</option><option value="mainland-cn">中国大陆 · 中文</option>
                        </select></label>
                        <label><span>{t.category}</span><select value={targetCategory} onChange={(e) => setTargetCategory(e.target.value)}>
                          <option value="gamenews">News</option><option value="gamebroad">Announcements</option><option value="gameevent">Events</option>
                        </select></label>
                        <label><span>{t.pages}</span><input type="number" min="1" max="10" value={targetPages} onChange={(e) => setTargetPages(Number(e.target.value))} /></label>
                        <label><span>{t.limit}</span><input type="number" min="1" max="100" value={targetLimit} onChange={(e) => setTargetLimit(Number(e.target.value))} /></label>
                        <label><span>{t.dateFrom}</span><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
                        <label><span>{t.dateTo}</span><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
                        </div>
                        <button className="primary-button" type="submit" disabled={busy !== null}>{busy === "targeted" ? t.working : t.discover}</button>
                      </form>
                    </details>

                    <details className="panel advanced-panel">
                      <summary><span>03</span><strong>{t.direct}</strong><small>{t.advanced}</small></summary>
                      <form className="advanced-form" onSubmit={importDirect}>
                        <label className="url-field"><span>{t.url}</span><input required type="url" placeholder="https://nte.perfectworld.com/…" value={directUrl} onChange={(e) => setDirectUrl(e.target.value)} /></label>
                        <button className="primary-button" type="submit" disabled={busy !== null}>{busy === "direct" ? t.working : t.import}</button>
                      </form>
                    </details>
                    <details className="panel advanced-panel">
                      <summary><span>04</span><strong>{t.local}</strong><small>{t.advanced}</small></summary>
                      <form className="advanced-form" onSubmit={importLocal}>
                        <p>{t.localHint}</p>
                        <div className="form-grid">
                          <label><span>{t.localKind}</span><select value={localKind} onChange={(event) => setLocalKind(event.target.value as typeof localKind)}><option value="document">Document</option><option value="transcript">Transcript</option><option value="gdd">GDD</option></select></label>
                          <label><span>{t.localFile}</span><input type="file" accept=".txt,.md,.vtt,.json,text/plain,text/markdown,text/vtt,application/json" onChange={(event) => void chooseLocalFile(event)} /></label>
                          <label><span>{t.localTitle}</span><input required maxLength={500} value={localTitle} onChange={(event) => setLocalTitle(event.target.value)} /></label>
                          <label><span>{t.localKey}</span><input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" maxLength={100} value={localKey} onChange={(event) => setLocalKey(event.target.value.toLowerCase())} /></label>
                          <label className="span-two"><span>{t.localContent}</span><textarea required maxLength={2000000} value={localContent} onChange={(event) => setLocalContent(event.target.value)} /></label>
                        </div>
                        <button className="primary-button" type="submit" disabled={busy !== null}>{busy === "local" ? t.working : t.import}</button>
                      </form>
                    </details>
                  </aside>

                  <div className="evidence-stack">
                    <section className="list-section">
                      <div className="list-heading"><h2>{t.candidates}</h2><span>{candidates.filter((item) => item.status === "discovered").length}</span></div>
                      {candidates.length === 0 ? <div className="empty-state">{t.noCandidates}</div> : candidates.map((candidate) => (
                        <article className="candidate-card" key={candidate.id}>
                          <div className="card-meta"><span>{candidate.site}</span><span>{candidate.locale}</span><span>{candidate.source_type}</span><span>{formatDate(candidate.published_at, language)}</span></div>
                          <h3>{candidate.title}</h3><a href={candidate.url} target="_blank" rel="noreferrer">{candidate.url}</a>
                          <p>{candidate.classification_basis}</p>
                          <button className="secondary-button" type="button" disabled={busy !== null || candidate.status !== "discovered"} onClick={() => void importCandidate(candidate)}>
                            {candidate.status === "discovered" ? t.selectImport : candidate.status}
                          </button>
                        </article>
                      ))}
                    </section>
                    <section className="list-section">
                      <div className="list-heading"><h2>{t.captured}</h2><span>{sources.length}</span></div>
                      {sources.length === 0 ? <div className="empty-state">{t.noSources}</div> : sources.map((source) => (
                        <article className="source-card" key={source.id}>
                          <div><div className="card-meta"><span>{source.site === "local-private" ? t.localPrivate : source.site}</span><span>{source.locale}</span><span>{source.source_type}</span></div>{source.url.startsWith("local://") ? <span>{t.localPrivate}</span> : <a href={source.url} target="_blank" rel="noreferrer">{source.url}</a>}</div>
                          <dl><div><dt>{t.versions}</dt><dd>{source.version_count}</dd></div><div><dt>{t.assets}</dt><dd>{source.asset_count}</dd></div><div><dt>{t.latest}</dt><dd>{source.latest_version ?? "—"}</dd></div></dl>
                        </article>
                      ))}
                    </section>
                  </div>
                </div>
              ) : tab === "knowledge" && selectedProject ? (
                <KnowledgeWorkspace
                  projectId={projectId}
                  projectName={selectedProject.name}
                  language={language}
                  runs={runs}
                  selectedRunId={selectedRun}
                  events={events}
                  refreshToken={knowledgeRefreshToken}
                  onRunQueued={acceptKnowledgeRun}
                  onOpenRun={(runId) => {
                    setSelectedRun(runId);
                    setTab("runs");
                  }}
                  onGoSources={() => setTab("sources")}
                />
              ) : tab === "gdd" && selectedProject ? (
                <GddWorkspace projectId={projectId} language={language} />
              ) : tab === "marketing" && selectedProject ? (
                <MarketingWorkspace projectId={projectId} language={language} />
              ) : tab === "scripts" && selectedProject ? (
                <ScriptWorkspace projectId={projectId} language={language} />
              ) : tab === "account" ? (
                <AccountWorkspace
                  status={authStatus}
                  language={language}
                  onChanged={refreshAuth}
                  project={selectedProject}
                />
              ) : (
                <div className="runs-layout">
                  <section className="run-list">
                    {runs.length === 0 ? <div className="empty-state">{t.noRuns}</div> : runs.map((run) => (
                      <button className={selectedRun === run.id ? "run-card active" : "run-card"} key={run.id} type="button" onClick={() => setSelectedRun(run.id)}>
                        <div><strong>{run.task_type === "source.discover" ? t.quick : run.task_type === "source.capture" ? t.import : run.task_type === "knowledge.extract" ? t.extract : run.task_type}</strong><small>{formatDate(run.created_at, language)}</small></div>
                        <span className={`run-status run-status--${run.status}`}>{run.status}</span>
                        <p>{t.checkpoint}: {run.checkpoint}</p>
                        {run.last_error_code && <p className="run-error">{t.error}: {run.last_error_code}</p>}
                      </button>
                    ))}
                  </section>
                  <section className="timeline-panel">
                    <div className="list-heading"><h2>{t.timeline}</h2>{selectedRunRecord && <span>{selectedRunRecord.status}</span>}</div>
                    {!selectedRun ? <div className="empty-state">{t.selectRun}</div> : (
                      <>
                        {selectedRunRecord?.last_error_detail && <div className="error-detail"><strong>{selectedRunRecord.last_error_code}</strong><p>{selectedRunRecord.last_error_detail}</p></div>}
                        {selectedRunRecord?.status === "needs_attention" && (
                          <button
                            className="primary-button run-retry"
                            type="button"
                            disabled={busy !== null}
                            onClick={() => void submitRun(`/api/runs/${selectedRunRecord.id}/retry`, {}, `retry-${selectedRunRecord.id}`)}
                          >
                            {busy === `retry-${selectedRunRecord.id}` ? t.working : t.retryRun}
                          </button>
                        )}
                        <ol className="timeline">
                          {events.map((event) => <li key={event.id}><span /><div><strong>{event.event_type}</strong><small>{event.actor_type} · {formatDate(event.occurred_at, language)}</small></div></li>)}
                        </ol>
                      </>
                    )}
                  </section>
                </div>
              )}
            </>
          )}
        </>
      )}
      <footer><span>GameCrafter v2</span><span>Facts · Evidence · Human control</span></footer>
    </main>
  );
}
