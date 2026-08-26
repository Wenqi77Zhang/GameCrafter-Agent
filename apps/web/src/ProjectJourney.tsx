import { useCallback, useEffect, useState } from "react";

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

const text = {
  "zh-CN": {
    title: "从资料到可交付脚本",
    subtitle: "按顺序完成五步；系统会保存证据、版本和人工决定。",
    stages: { sources: "添加来源", knowledge: "确认知识", marketing: "选择选题", creation: "生成并评价", delivery: "确认并导出" },
    statuses: { not_started: "未开始", in_progress: "进行中", complete: "已完成" },
    next: "继续下一步",
    done: "首条营销链路已完成",
    diagnostics: "运行概况",
    evidence: "证据版本",
    claims: "候选知识",
    signals: "趋势信号",
    versions: "脚本版本",
    runs: "成功运行",
    attention: "需处理",
    cost: "API 费用",
    unavailable: "暂时无法读取项目进度，可在运行记录中查看服务状态。",
  },
  en: {
    title: "From evidence to a deliverable script",
    subtitle: "Complete five guided steps; evidence, versions, and human decisions stay traceable.",
    stages: { sources: "Add sources", knowledge: "Confirm knowledge", marketing: "Choose topic", creation: "Create and evaluate", delivery: "Approve and export" },
    statuses: { not_started: "Not started", in_progress: "In progress", complete: "Complete" },
    next: "Continue",
    done: "First marketing journey complete",
    diagnostics: "Run overview",
    evidence: "Evidence versions",
    claims: "Candidate facts",
    signals: "Trend signals",
    versions: "Script versions",
    runs: "Successful runs",
    attention: "Needs attention",
    cost: "API cost",
    unavailable: "Project progress is temporarily unavailable. Check Runs for service status.",
  },
} as const;

export function ProjectJourney({
  projectId,
  language,
  refreshToken,
  onNavigate,
}: {
  projectId: string;
  language: Language;
  refreshToken: number;
  onNavigate: (tab: JourneyTab) => void;
}) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
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
    void load();
  }, [load, refreshToken]);

  if (failed) return <section className="journey journey--error">{t.unavailable}</section>;
  if (!overview) return <section className="journey journey--loading" aria-label={t.title} />;

  const nextStage = overview.next_action === "complete" ? null : overview.next_action;
  const metrics = overview.metrics;
  return (
    <section className="journey" aria-labelledby="journey-title">
      <div className="journey-heading">
        <div><p className="eyebrow">Guided workflow · {overview.release}</p><h2 id="journey-title">{t.title}</h2><p>{t.subtitle}</p></div>
        <button
          className="primary-button"
          type="button"
          disabled={!nextStage}
          onClick={() => nextStage && onNavigate(stageTabs[nextStage])}
        >
          {nextStage ? `${t.next} · ${t.stages[nextStage]}` : t.done}
        </button>
      </div>
      <ol className="journey-steps">
        {overview.stages.map((stage, index) => (
          <li key={stage.key} className={`journey-step journey-step--${stage.status}`}>
            <button type="button" onClick={() => onNavigate(stageTabs[stage.key])}>
              <span>{stage.status === "complete" ? "✓" : index + 1}</span>
              <strong>{t.stages[stage.key]}</strong>
              <small>{t.statuses[stage.status]}</small>
            </button>
          </li>
        ))}
      </ol>
      <div className="journey-metrics" aria-label={t.diagnostics}>
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
    </section>
  );
}
