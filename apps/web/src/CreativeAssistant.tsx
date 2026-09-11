import { useCallback, useEffect, useRef, useState } from "react";
import { api, idempotencyKey, type Language } from "./client";
import { EvidenceReview, type FactCheck } from "./EvidenceReview";

export type CreativeOperation = {
  id: string;
  run_id: string;
  target_id: string;
  operation: string;
  status: string;
  checkpoint: string;
  error: string | null;
  model: string;
  candidate_id?: string;
  review_current?: boolean;
  result: {
    version_id?: string;
    passed?: boolean;
    strategy?: ModelStrategy;
    review?: {
      fact_checks?: FactCheck[];
      summary: string;
      issues: { severity: string; message: string; fix: string }[];
    };
    provenance?: {
      model: string;
      input_tokens: number;
      output_tokens: number;
    }[];
  };
};
type ModelStrategy = {
  marketing_direction: string;
  recommended_topic: string;
  why_it_fits: string;
  target_audience: string;
  english_hooks: string[];
  execution_steps: string[];
  risks: string[];
  measurement_plan: string;
  knowledge_member_ids: string[];
};
const activeStatuses = ["queued", "running", "retry_wait"];
type Readiness = {
  ready: boolean;
  fact_count: number;
  story_fact_count: number;
  message: string;
};

export function useCreativeAssistant(
  projectId: string,
  targetId: string,
  onComplete?: (item: CreativeOperation) => void,
) {
  const [capability, setCapability] = useState<{
    available: boolean;
    model: string;
  } | null>(null);
  const [operations, setOperations] = useState<CreativeOperation[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const callback = useRef(onComplete);
  callback.current = onComplete;
  const seen = useRef(new Set<string>());
  const currentTarget = useRef(`${projectId}/${targetId}`);
  currentTarget.current = `${projectId}/${targetId}`;
  const refresh = useCallback(async () => {
    if (!targetId) return;
    const payload = await api<{
      items: CreativeOperation[];
      readiness?: Readiness;
    }>(
      `/api/projects/${projectId}/creative-operations?target_id=${encodeURIComponent(targetId)}`,
    );
    if (currentTarget.current !== `${projectId}/${targetId}`) return;
    setOperations(payload.items);
    setReadiness(payload.readiness ?? null);
    setError("");
    // The newest saved operation wins. Replaying every historical callback selected old versions.
    const newest = payload.items.find((item) => item.status === "succeeded");
    if (newest && !seen.current.has(newest.id)) callback.current?.(newest);
    payload.items
      .filter((item) => item.status === "succeeded")
      .forEach((item) => seen.current.add(item.id));
  }, [projectId, targetId]);
  useEffect(() => {
    let ignore = false;
    api<{ available: boolean; model: string }>("/api/creative-capability")
      .then((value) => {
        if (!ignore) setCapability(value);
      })
      .catch(() => {
        if (!ignore) setCapability(null);
      });
    return () => {
      ignore = true;
    };
  }, [projectId]);
  useEffect(() => {
    setOperations([]);
    setReadiness(null);
    setError("");
    seen.current.clear();
    void refresh().catch((e: Error) => setError(e.message));
  }, [refresh]);
  const pending = operations.find((item) =>
    activeStatuses.includes(item.status),
  );
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      void refresh().catch((e: Error) => setError(e.message));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pending, refresh]);
  const reconnect = async () => {
    try {
      setCapability(
        await api<{ available: boolean; model: string }>(
          "/api/creative-capability",
        ),
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const submit = async (operation: string) => {
    if (submitting || pending || !targetId) return;
    setSubmitting(true);
    setError("");
    try {
      const item = await api<CreativeOperation>(
        `/api/projects/${projectId}/creative-operations`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey(`creative-${operation}`),
          },
          body: JSON.stringify({ target_id: targetId, operation }),
        },
      );
      if (currentTarget.current === `${projectId}/${targetId}`)
        setOperations((items) => [
          item,
          ...items.filter((i) => i.id !== item.id),
        ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };
  const cancel = async () => {
    if (!pending) return;
    try {
      await api(
        `/api/projects/${projectId}/creative-operations/${pending.id}/cancel`,
        { method: "POST" },
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const retry = async () => {
    const item = operations[0];
    if (!item) return;
    try {
      await api(`/api/runs/${item.run_id}/retry`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("creative-retry") },
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return {
    capability,
    readiness,
    operations,
    pending,
    error,
    busy: submitting || !!pending,
    submit,
    refresh,
    reconnect,
    cancel,
    retry,
  };
}

export function CreativeProgress({
  assistant,
  language,
}: {
  assistant: ReturnType<typeof useCreativeAssistant>;
  language: Language;
}) {
  const zh = language === "zh-CN";
  const item = assistant.operations[0];
  const stages: Record<string, string> = zh
    ? {
        created: "等待后台处理",
        "creative.assist": "准备创作材料",
        "creative.strategy": "推敲营销方向",
        "creative.strategy_review": "独立核查营销建议",
        "creative.write": "撰写英语脚本",
        "creative.critique": "独立检查内容与证据",
        "creative.saved": "保存结果",
        completed: "结果已保存",
      }
    : {
        created: "Queued",
        "creative.assist": "Preparing evidence",
        "creative.strategy": "Developing strategy",
        "creative.strategy_review": "Reviewing strategy against evidence",
        "creative.write": "Writing script",
        "creative.critique": "Independent evidence review",
        "creative.saved": "Saving",
        completed: "Saved",
      };
  return (
    <>
      {assistant.error && (
        <div className="notice notice--error" role="alert">
          {assistant.error}
          <button
            type="button"
            className="ghost-button"
            onClick={() => void assistant.reconnect()}
          >
            {zh ? "重新连接" : "Reconnect"}
          </button>
        </div>
      )}
      {assistant.readiness?.ready === false && (
        <p className="notice notice--error" role="alert">
          {zh
            ? assistant.readiness.message
            : "Name and genre alone are not enough. Add reviewed gameplay, world, character content, or update facts in Knowledge; publish a new snapshot and create a new marketing task."}
        </p>
      )}
      {item && (
        <div
          className={`creative-progress ${item.status === "needs_attention" ? "notice--error" : ""}`}
          role="status"
        >
          <strong>
            {item.status === "needs_attention"
              ? zh
                ? "任务未完成"
                : "Task needs attention"
              : item.status === "cancelled"
                ? zh
                  ? "已取消，不会保存迟到结果"
                  : "Cancelled; late results are discarded"
                : item.result.passed === false
                  ? zh
                    ? "草稿已保存，评审未通过"
                    : "Draft saved; review did not pass"
                  : (stages[item.checkpoint] ?? item.checkpoint)}
          </strong>
          <span>
            {item.model} ·{" "}
            {zh ? "本地运行，无付费 API" : "Local inference, no paid API"}
          </span>
          {assistant.pending && (
            <>
              <p>
                {zh
                  ? "可以离开此步骤，任务进度已保存。模型速度取决于你的电脑。"
                  : "You can leave this step; progress is persisted. Speed depends on your hardware."}
              </p>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void assistant.cancel()}
              >
                {zh ? "取消任务" : "Cancel task"}
              </button>
            </>
          )}
          {item.status === "needs_attention" && (
            <>
              <p>{item.error}</p>
              <button
                type="button"
                className="secondary-button"
                disabled={item.review_current === false}
                onClick={() => void assistant.retry()}
              >
                {item.review_current === false
                  ? zh
                    ? "提示版本已更新，请重新发起操作"
                    : "Prompt changed; start a new operation"
                  : zh
                    ? "重试未完成步骤"
                    : "Retry unfinished steps"}
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}

export function StrategyAssistant({
  projectId,
  taskId,
  candidateId,
  language,
  topicApproved = false,
}: {
  projectId: string;
  taskId: string;
  candidateId: string;
  language: Language;
  topicApproved?: boolean;
}) {
  const assistant = useCreativeAssistant(projectId, taskId);
  const zh = language === "zh-CN";
  const latest = assistant.operations.find(
    (item) => item.candidate_id === candidateId && item.result.strategy,
  );
  const strategy = latest?.result.strategy;
  const reviewPassed =
    latest?.result.passed === true && latest?.review_current !== false;
  return (
    <section
      className="panel model-strategy"
      aria-label={zh ? "模型营销建议" : "Model marketing recommendation"}
    >
      <div className="list-heading">
        <h2>
          {zh
            ? "把证据变成可执行的营销建议"
            : "Turn evidence into an actionable campaign"}
        </h2>
        <span>{zh ? "本地模型" : "Local model"}</span>
      </div>
      <p>
        {zh
          ? "以当前推荐或已批准的话题为边界，给出具体角度、英语开场和验证方法。建议不会自动替你批准选题。"
          : "Develop the recommended or approved topic into an angle, English hooks, and a measurement plan. Suggestions never approve a topic for you."}
      </p>
      <button
        type="button"
        className={reviewPassed ? "ghost-button" : "primary-button"}
        disabled={
          assistant.busy ||
          !assistant.capability?.available ||
          assistant.readiness?.ready === false
        }
        onClick={() => void assistant.submit("strategy")}
      >
        {assistant.busy
          ? zh
            ? "正在生成并评审建议…"
            : "Developing and reviewing recommendation…"
          : reviewPassed
            ? zh
              ? "重新生成建议（保留历史）"
              : "Regenerate recommendation (keep history)"
            : zh
              ? "生成具体营销建议"
              : "Develop marketing recommendation"}
      </button>
      {!assistant.capability?.available && (
        <p>
          {zh
            ? "本地模型未就绪；下方仍可查看规则匹配依据，不会用模板冒充模型结论。"
            : "Local model unavailable. Rule-based evidence remains available below; no template is presented as model output."}
          <button
            type="button"
            className="ghost-button"
            onClick={() => void assistant.reconnect()}
          >
            {zh ? "重新检测模型" : "Check model again"}
          </button>
        </p>
      )}
      <CreativeProgress assistant={assistant} language={language} />
      {strategy && (
        <div className="model-strategy__result">
          <div
            className={`notice ${reviewPassed ? "notice--ok" : "notice--error"}`}
            role="status"
          >
            <strong>
              {latest?.review_current === false
                ? zh
                  ? "旧建议需要重新生成并评审，不会直接交给脚本写作"
                  : "Regenerate and re-review this legacy recommendation before writing"
                : reviewPassed
                  ? zh
                    ? topicApproved
                      ? "模型初审通过 · 选题已确认，无需重复提交"
                      : "模型初审通过 · 仍需你确认选题"
                    : topicApproved
                      ? "Model review passed · topic already approved, no repeat submission needed"
                      : "Model review passed · your topic approval is still required"
                  : zh
                    ? "建议未通过初审 · 不会用于脚本生成"
                    : "Review blocked · this suggestion will not be used by the writer"}
            </strong>
            <p>{latest?.result.review?.summary}</p>
            {!latest?.result.review?.fact_checks?.length &&
              latest?.result.review?.issues.map((issue, index) => (
                <p key={index}>
                  {issue.message} → {issue.fix}
                </p>
              ))}
          </div>
          {!!latest?.result.review?.fact_checks?.length && (
            <EvidenceReview
              key={latest.id}
              checks={latest.result.review.fact_checks}
              language={language}
            />
          )}
          <details open={reviewPassed}>
            <summary>
              {reviewPassed
                ? zh
                  ? "阅读完整建议"
                  : "Read recommendation"
                : zh
                  ? "查看未通过的草稿（仅供修改）"
                  : "Inspect blocked draft for correction"}
            </summary>
            <h3>{strategy.marketing_direction}</h3>
            <p className="lead">{strategy.recommended_topic}</p>
            <p>{strategy.why_it_fits}</p>
            <p>
              <strong>{zh ? "受众：" : "Audience: "}</strong>
              {strategy.target_audience}
            </p>
            <h4>{zh ? "英语开场 A/B" : "English hooks A/B"}</h4>
            {strategy.english_hooks.map((hook) => (
              <blockquote key={hook}>{hook}</blockquote>
            ))}
            <h4>{zh ? "怎么拍" : "Execution"}</h4>
            <ol>
              {strategy.execution_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <h4>{zh ? "如何验证效果" : "Measure performance"}</h4>
            <p>{strategy.measurement_plan}</p>
            <h4>{zh ? "边界与风险" : "Limits and risks"}</h4>
            <ul>
              {strategy.risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
            <small>
              {zh
                ? "这是创作建议，不是已验证的市场结论。支撑事实见下方证据卡。"
                : "This is a creative proposal, not validated market performance. Supporting facts appear below."}
            </small>
          </details>
        </div>
      )}
    </section>
  );
}

export function ReasonChoices({
  value,
  onChange,
  language,
  choices,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  language: Language;
  choices: string[];
  label: string;
}) {
  const [other, setOther] = useState(false);
  return (
    <fieldset className="reason-choices">
      <legend>{label}</legend>
      <div className="reason-choices__options">
        {choices.map((choice) => (
          <button
            key={choice}
            type="button"
            aria-pressed={!other && value === choice}
            onClick={() => {
              setOther(false);
              onChange(choice);
            }}
          >
            {choice}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={other}
          onClick={() => {
            setOther(true);
            onChange("");
          }}
        >
          {language === "zh-CN" ? "其他原因" : "Other reason"}
        </button>
      </div>
      {other && (
        <textarea
          aria-label={label}
          required
          maxLength={1000}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </fieldset>
  );
}
