import { useState } from "react";
import type { Language } from "./client";
import { EvidenceNotes, type Evidence } from "./ScriptEditor";

export type FactCheck = {
  text_id: string;
  field: string;
  section_index: number | null;
  text: string;
  verdict: "SUPPORTED" | "UNSUPPORTED" | "NOT_A_FACT";
  reason: string;
  knowledge_member_ids: string[];
  evidence_quotes?: string[];
};

const fields: Record<string, [string, string]> = {
  title: ["标题", "Title"],
  caption: ["发布文案", "Caption"],
  hashtags: ["标签", "Hashtag"],
  voiceover: ["口播", "Voiceover"],
  on_screen_text: ["屏幕文字", "On-screen text"],
  visual_direction: ["画面建议", "Visual direction"],
  marketing_direction: ["营销方向", "Marketing direction"],
  recommended_topic: ["推荐话题", "Topic"],
  why_it_fits: ["推荐理由", "Rationale"],
  target_audience: ["目标受众", "Audience"],
  english_hooks: ["英语开场", "English hook"],
  execution_steps: ["制作步骤", "Production step"],
  measurement_plan: ["验证计划", "Measurement plan"],
  risks: ["风险说明", "Risk"],
};

export function EvidenceReview({
  checks,
  evidence = [],
  language,
  onEdit,
}: {
  checks: FactCheck[];
  evidence?: Evidence[];
  language: Language;
  onEdit?: (check: FactCheck) => void;
}) {
  const zh = language === "zh-CN";
  const unsupported = checks.filter((c) => c.verdict === "UNSUPPORTED").length;
  const [onlyRisks, setOnlyRisks] = useState(unsupported > 0);
  if (!checks.length) return null; // Legacy results have no per-text coverage; do not invent it.
  const visible = onlyRisks
    ? checks.filter((c) => c.verdict === "UNSUPPORTED")
    : checks;
  const supported = checks.filter((c) => c.verdict === "SUPPORTED").length;
  return (
    <section
      className="evidence-review"
      aria-label={zh ? "逐段证据核查" : "Per-text evidence review"}
    >
      <h3>{zh ? "逐段证据核查" : "Per-text evidence review"}</h3>
      <p>
        {zh
          ? `已覆盖 ${checks.length} 段 · 模型认为有支持 ${supported} · 需核对 ${unsupported} · 非事实断言 ${checks.length - supported - unsupported}`
          : `${checks.length} texts covered · ${supported} model-supported · ${unsupported} to check · ${checks.length - supported - unsupported} non-claims`}
      </p>
      <p className="muted">
        {zh
          ? "覆盖数不是准确率。模型可能误判；请核对原句、事实和适用范围，素材授权仍需负责人确认。"
          : "Coverage is not accuracy. Check the draft, facts and scope; the model can be wrong. Asset rights still require human confirmation."}
      </p>
      <div
        className="evidence-review__filters"
        role="group"
        aria-label={zh ? "核查筛选" : "Review filters"}
      >
        <button
          type="button"
          aria-pressed={onlyRisks}
          onClick={() => setOnlyRisks(true)}
        >
          {zh ? `需核对 ${unsupported}` : `To check ${unsupported}`}
        </button>
        <button
          type="button"
          aria-pressed={!onlyRisks}
          onClick={() => setOnlyRisks(false)}
        >
          {zh ? `全部 ${checks.length}` : `All ${checks.length}`}
        </button>
      </div>
      {!visible.length && (
        <p>
          {zh
            ? "模型未标出需要核对的句子；不代表内容已获人工批准。"
            : "No model-flagged texts; this is not human approval."}
        </p>
      )}
      <div className="evidence-review__items">
        {visible.map((check) => {
          const key = check.field.startsWith("sections.")
            ? check.field.split(".")[2]
            : check.field.split(".")[0];
          const label = fields[key]?.[zh ? 0 : 1] ?? check.field;
          const fieldLabel =
            check.section_index !== null
              ? `${zh ? "分镜" : "Beat"} ${check.section_index + 1} · ${label}`
              : label;
          return (
            <article
              className={`evidence-review__item evidence-review__item--${check.verdict.toLowerCase()}`}
              key={check.text_id}
            >
              <div className="list-heading">
                <strong>{fieldLabel}</strong>
                <span>
                  {check.verdict === "UNSUPPORTED"
                    ? zh
                      ? "模型提示：需核对"
                      : "Model: check required"
                    : check.verdict === "SUPPORTED"
                      ? zh
                        ? "模型认为有支持"
                        : "Model-supported"
                      : zh
                        ? "模型认为非事实断言"
                        : "Model: non-claim"}
                </span>
              </div>
              <blockquote>{check.text}</blockquote>
              <p>{check.reason}</p>
              {!!check.evidence_quotes?.length && (
                <details>
                  <summary>
                    {zh
                      ? "核对模型引用的已审核事实原句"
                      : "Inspect the cited approved fact text"}
                  </summary>
                  {check.evidence_quotes.map((quote, i) => (
                    <blockquote key={i}>{quote}</blockquote>
                  ))}
                </details>
              )}
              {evidence.length > 0 && (
                <EvidenceNotes
                  ids={check.knowledge_member_ids}
                  evidence={evidence}
                  language={language}
                />
              )}
              {onEdit && (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => onEdit(check)}
                  aria-label={
                    zh
                      ? `定位并编辑：${fieldLabel}`
                      : `Locate and edit: ${fieldLabel}`
                  }
                >
                  {zh ? "定位并编辑这句话" : "Locate and edit this text"}
                </button>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
