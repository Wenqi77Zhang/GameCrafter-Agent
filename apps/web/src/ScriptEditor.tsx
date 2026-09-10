import { useState } from "react";
import type { Language } from "./client";

export type Section = {
  start_second: number;
  end_second: number;
  purpose: string;
  voiceover: string;
  on_screen_text: string;
  visual_direction: string;
  knowledge_member_ids: string[];
  trend_signal_ids: string[];
};
export type ScriptContent = {
  schema_version: string;
  platform: string;
  output_language: string;
  duration_seconds: number;
  title: string;
  caption: string;
  hashtags: string[];
  sections: Section[];
};
export type Evidence = {
  snapshot_member_id: string;
  predicate: string;
  value: unknown;
  sources: { url: string | null; quote: string; source_version_id: string }[];
};

export function StoryboardEditor({
  content,
  evidence,
  language,
  disabled,
  onSave,
}: {
  content: ScriptContent;
  evidence: Evidence[];
  language: Language;
  disabled: boolean;
  onSave: (value: ScriptContent) => void;
}) {
  const [draft, setDraft] = useState(content);
  const [hashtagText, setHashtagText] = useState(content.hashtags.join(" "));
  const savedDraft = { ...draft, hashtags: hashtagText.split(/\s+/).filter(Boolean) };
  const changed = JSON.stringify(savedDraft) !== JSON.stringify(content);
  // The parent keys this component by immutable version ID; refreshes must not erase unsaved edits.
  const zh = language === "zh-CN";
  const update = (
    index: number,
    key: keyof Section,
    value: string | string[],
  ) =>
    setDraft((current) => ({
      ...current,
      sections: current.sections.map((item, i) =>
        i === index ? { ...item, [key]: value } : item,
      ),
    }));
  return (
    <details className="panel script-editor">
      <summary>
        {zh
          ? "逐镜编辑（无需填写 JSON）"
          : "Edit storyboard (no JSON required)"}
      </summary>
      <label>
        {zh ? "标题" : "Title"}
        <input
          maxLength={200}
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </label>
      <label>
        {zh ? "发布文案" : "Caption"}
        <textarea
          maxLength={500}
          value={draft.caption}
          onChange={(e) => setDraft({ ...draft, caption: e.target.value })}
        />
      </label>
      <label>
        {zh ? "标签（空格分隔）" : "Hashtags (space separated)"}
        <input
          maxLength={360}
          value={hashtagText}
          onChange={(e) => setHashtagText(e.target.value)}
        />
      </label>
      {draft.sections.map((beat, index) => (
        <fieldset key={index}>
          <legend>
            {zh ? "分镜" : "Beat"} {index + 1} · {beat.start_second}–
            {beat.end_second}s
          </legend>
          {(["voiceover", "on_screen_text", "visual_direction"] as const).map(
            (key, k) => (
              <label key={key}>
                {
                  (zh
                    ? ["口播", "屏幕文字", "画面建议"]
                    : ["Voiceover", "On-screen text", "Visual direction"])[k]
                }
                <textarea
                  maxLength={1200}
                  value={beat[key]}
                  onChange={(e) => update(index, key, e.target.value)}
                />
              </label>
            ),
          )}
          <span>
            {zh ? "选择支撑事实（可多选）" : "Choose supporting facts"}
          </span>
          {evidence.map((fact) => (
            <label className="evidence-check" key={fact.snapshot_member_id}>
              <input
                type="checkbox"
                checked={beat.knowledge_member_ids.includes(
                  fact.snapshot_member_id,
                )}
                onChange={(e) =>
                  update(
                    index,
                    "knowledge_member_ids",
                    e.target.checked
                      ? [...beat.knowledge_member_ids, fact.snapshot_member_id]
                      : beat.knowledge_member_ids.filter(
                          (id) => id !== fact.snapshot_member_id,
                        ),
                  )
                }
              />
              {String(fact.value)}
            </label>
          ))}
        </fieldset>
      ))}
      <p role="status">
        {changed
          ? zh
            ? "有未保存修改。保存后会形成新版本，需要重新检查和终审。"
            : "Unsaved changes. Saving creates a new version requiring fresh checks and approval."
          : zh
            ? "尚未修改，不需要重复保存。"
            : "Unchanged; no need to save again."}
      </p>
      <button
        className="secondary-button"
        type="button"
        disabled={
          disabled ||
          !draft.title.trim() ||
          !draft.caption.trim() ||
          !savedDraft.hashtags.length ||
          draft.sections.some(
            (b) =>
              !b.voiceover.trim() ||
              !b.on_screen_text.trim() ||
              !b.visual_direction.trim(),
          ) ||
          !changed
        }
        onClick={() => onSave(savedDraft)}
      >
        {zh ? "保存为新版本" : "Save new version"}
      </button>
    </details>
  );
}

export function EvidenceNotes({
  ids,
  evidence,
  language,
}: {
  ids: string[];
  evidence: Evidence[];
  language: Language;
}) {
  if (!ids.length) return null;
  return (
    <details>
      <summary>
        {language === "zh-CN" ? "查看支撑事实" : "Supporting facts"} ·{" "}
        {ids.length}
      </summary>
      {ids.map((id) => {
        const fact = evidence.find((item) => item.snapshot_member_id === id);
        return (
          <div key={id}>
            <strong>{fact ? String(fact.value) : id}</strong>
            {fact?.sources.map((source, i) => (
              <div key={i}>
                <blockquote>{source.quote}</blockquote>
                {source.url && /^https?:\/\//.test(source.url) && (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {language === "zh-CN" ? "查看来源原文" : "Open source"}
                  </a>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </details>
  );
}

export const ruleNames: Record<string, string> = {
  spoken_pacing: "整体口播速度",
  beat_pacing: "逐镜口播时长",
  evidence_coverage: "证明与看点的证据引用",
  opening_and_cta: "开场与行动引导",
  on_screen_readability: "屏幕文字可读性",
};
export const ruleFixes: Record<string, string> = {
  spoken_pacing_failed:
    "口播建议保持每分钟 90–190 词；删减过长内容或补充必要解释。",
  beat_pacing_failed: "部分分镜的台词超出可读时长，请缩短这些台词。",
  evidence_coverage_failed: "为证据和看点分镜选择已审核事实。",
  opening_and_cta_failed: "第一镜应为开场，最后一镜应为行动引导。",
  on_screen_readability_failed: "每镜屏幕文字不要超过 12 个单词。",
};
