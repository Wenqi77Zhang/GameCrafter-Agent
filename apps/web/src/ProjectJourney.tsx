import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./client";
import type { Language } from "./client";

export type JourneyTab = "sources" | "knowledge" | "marketing" | "scripts" | "runs";

type StageKey = "sources" | "knowledge" | "marketing" | "creation" | "delivery";
type StageStatus = "not_started" | "in_progress" | "complete";
type Overview = {
  project_id: string;
  release: string;
  next_action: StageKey | "complete";
  stages: Array<{ key: StageKey; status: StageStatus }>;
  metrics: {
    evidence_versions: number;
    candidate_claims: number;
    published_snapshots: number;
    verified_trend_signals: number;
    approved_topics: number;
    script_versions: number;
    exports: number;
    successful_runs: number;
    attention_runs: number;
    active_runs: number;
    api_cost_usd: number;
  };
};

const stageTabs: Record<StageKey, JourneyTab> = {
  sources: "sources",
  knowledge: "knowledge",
  marketing: "marketing",
  creation: "scripts",
  delivery: "scripts",
};

const stageLabels: Record<Language, Record<StageKey, string>> = {
  "zh-CN": { sources: "来源", knowledge: "知识", marketing: "营销", creation: "创作", delivery: "交付" },
  en: { sources: "Sources", knowledge: "Knowledge", marketing: "Marketing", creation: "Create", delivery: "Delivery" },
};

const text = {
  "zh-CN": {
    route: "你的制作路线",
    routeHint: "系统会自动打开当前任务；已完成步骤仍可回看。",
    stages: {
      sources: { title: "添加可信资料", purpose: "保存官网或本地证据", result: "得到可追溯来源" },
      knowledge: { title: "整理游戏知识", purpose: "提取并审核可用事实", result: "发布知识快照" },
      marketing: { title: "选择营销角度", purpose: "匹配 TikTok 趋势与受众", result: "确认一个选题" },
      creation: { title: "生成并评价脚本", purpose: "创作英文短视频脚本", result: "获得质量评分" },
      delivery: { title: "确认并导出", purpose: "完成最终人工把关", result: "导出可交付文件" },
    },
    statuses: { not_started: "等待前一步", in_progress: "现在做这里", complete: "已完成" },
    open: "打开",
    current: "当前任务",
    currentHint: "不必自己判断下一步，点击下方按钮即可继续。",
    resume: "继续当前任务",
    done: "首条营销链路已完成",
    doneHint: "可以回看任一步骤，或从创作页继续生成新版本。",
    progress: "总体进度",
    stepCount: (current: number) => `第 ${current} / 5 步`,
    diagnostics: "专业数据与运行状态",
    evidence: "证据版本",
    claims: "候选知识",
    signals: "趋势信号",
    versions: "脚本版本",
    runs: "成功运行",
    attention: "需处理",
    cost: "API 费用",
    unavailable: "暂时无法读取制作进度。你仍可打开运行记录查看服务状态。",
  },
  en: {
    route: "Your production route",
    routeHint: "The current task opens automatically; completed steps remain available.",
    stages: {
      sources: { title: "Add trusted material", purpose: "Save official or private evidence", result: "Traceable sources" },
      knowledge: { title: "Build game knowledge", purpose: "Extract and review usable facts", result: "Published snapshot" },
      marketing: { title: "Choose an angle", purpose: "Match TikTok trends and audience", result: "Approved topic" },
      creation: { title: "Create and evaluate", purpose: "Write an English short-video script", result: "Quality score" },
      delivery: { title: "Approve and export", purpose: "Complete the final human gate", result: "Deliverable files" },
    },
    statuses: { not_started: "Waiting", in_progress: "Do this now", complete: "Complete" },
    open: "Open",
    current: "Current task",
    currentHint: "You do not need to work out the next step. Use the button below.",
    resume: "Continue current task",
    done: "First marketing journey complete",
    doneHint: "Review any step, or create another script version.",
    progress: "Overall progress",
    stepCount: (current: number) => `Step ${current} of 5`,
    diagnostics: "Technical data and run status",
    evidence: "Evidence versions",
    claims: "Candidate facts",
    signals: "Trend signals",
    versions: "Script versions",
    runs: "Successful runs",
    attention: "Needs attention",
    cost: "API cost",
    unavailable: "Production progress is temporarily unavailable. Runs remain available for diagnosis.",
  },
} as const;

export function ProjectJourney({
  projectId,
  language,
  refreshToken,
  activeTab,
  onNavigate,
}: {
  projectId: string;
  language: Language;
  refreshToken: number;
  activeTab: string;
  onNavigate: (tab: JourneyTab) => void;
}) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
  const previousNextStage = useRef<StageKey | "complete" | null>(null);
  const t = text[language];

  const load = useCallback(async () => {
    try {
      setOverview(await api<Overview>(`/api/projects/${projectId}/overview`));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [projectId]);

  useEffect(() => {
    previousNextStage.current = null;
  }, [projectId]);

  useEffect(() => {
    void load();
    const timer = globalThis.setInterval(() => void load(), 4000);
    return () => globalThis.clearInterval(timer);
  }, [load, refreshToken]);

  useEffect(() => {
    if (!overview) return;
    const next = overview.next_action;
    const previous = previousNextStage.current;
    previousNextStage.current = next;
    if (next === "complete") return;
    const nextTab = stageTabs[next];
    const previousTab = previous && previous !== "complete" ? stageTabs[previous] : null;
    const firstGuidedOpen = previous === null && activeTab === "sources";
    const stageAdvanced = previousTab !== null && previous !== next && activeTab === previousTab;
    if ((firstGuidedOpen || stageAdvanced) && activeTab !== nextTab) onNavigate(nextTab);
  }, [activeTab, onNavigate, overview]);

  if (failed) {
    return (
      <aside className="journey-rail journey-rail--error">
        <strong>{t.route}</strong>
        <p>{t.unavailable}</p>
        <button type="button" onClick={() => onNavigate("runs")}>{t.diagnostics}</button>
      </aside>
    );
  }
  if (!overview) return <aside className="journey-rail journey-rail--loading" aria-label={t.route} />;

  const nextStage = overview.next_action === "complete" ? null : overview.next_action;
  const metrics = overview.metrics;
  const completedStages = overview.stages.filter((stage) => stage.status === "complete").length;
  const currentStep = nextStage
    ? overview.stages.findIndex((stage) => stage.key === nextStage) + 1
    : overview.stages.length;
  const progress = nextStage ? (completedStages / overview.stages.length) * 100 : 100;

  return (
    <aside className="journey-rail" aria-labelledby="journey-title">
      <header className="journey-rail__header">
        <p className="eyebrow">{t.progress}</p>
        <h2 id="journey-title">{t.route}</h2>
        <p>{t.routeHint}</p>
        <div className="journey-progress" aria-label={t.progress}>
          <span><i style={{ width: `${progress}%` }} /></span>
          <small>{t.stepCount(currentStep)}</small>
        </div>
      </header>

      <ol className="journey-route">
        {overview.stages.map((stage, index) => {
          const stageCopy = t.stages[stage.key];
          const targetTab = stageTabs[stage.key];
          const isCurrent = stage.key === nextStage;
          const isOpen = activeTab === targetTab && (stage.key !== "delivery" || nextStage === "delivery");
          return (
            <li key={stage.key} className={`journey-route__step journey-route__step--${stage.status}${isCurrent ? " journey-route__step--current" : ""}${isOpen ? " journey-route__step--open" : ""}`}>
              <button
                type="button"
                aria-label={stageLabels[language][stage.key]}
                aria-current={isOpen ? "step" : undefined}
                className={isOpen ? "active" : undefined}
                onClick={() => onNavigate(targetTab)}
              >
                <span className="journey-route__number">{stage.status === "complete" ? "✓" : index + 1}</span>
                <span className="journey-route__copy">
                  <strong>{stageCopy.title}</strong>
                  <small>{stageCopy.purpose}</small>
                  <em>{stage.status === "complete" ? stageCopy.result : isCurrent ? t.statuses.in_progress : t.statuses[stage.status]}</em>
                </span>
                <span className="journey-route__open">{isCurrent ? "→" : t.open}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <section className="journey-now" aria-label={t.current}>
        <p className="eyebrow">{nextStage ? t.current : t.done}</p>
        <strong>{nextStage ? t.stages[nextStage].title : t.done}</strong>
        <p>{nextStage ? t.currentHint : t.doneHint}</p>
        <button className="primary-button" type="button" onClick={() => onNavigate(nextStage ? stageTabs[nextStage] : "scripts")}>
          {nextStage ? `${t.resume} · ${t.stages[nextStage].title}` : t.stages.creation.title}
        </button>
      </section>

      <details className="journey-diagnostics">
        <summary>{t.diagnostics}</summary>
        <div className="journey-metrics">
          <span><strong>{metrics.evidence_versions}</strong>{t.evidence}</span>
          <span><strong>{metrics.candidate_claims}</strong>{t.claims}</span>
          <span><strong>{metrics.verified_trend_signals}</strong>{t.signals}</span>
          <span><strong>{metrics.script_versions}</strong>{t.versions}</span>
          <span><strong>{metrics.successful_runs}</strong>{t.runs}</span>
          <button type="button" className={metrics.attention_runs > 0 ? "metric-alert" : ""} onClick={() => onNavigate("runs")}>
            <strong>{metrics.attention_runs + metrics.active_runs}</strong>{t.attention}
          </button>
          <span><strong>${metrics.api_cost_usd.toFixed(2)}</strong>{t.cost}</span>
        </div>
      </details>
    </aside>
  );
}
