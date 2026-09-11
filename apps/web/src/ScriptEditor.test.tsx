import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import {
  EvidenceNotes,
  StoryboardEditor,
  type ScriptContent,
} from "./ScriptEditor";

afterEach(cleanup);
const content: ScriptContent = {
  schema_version: "1",
  platform: "TikTok",
  output_language: "en",
  duration_seconds: 30,
  title: "NTE introduction",
  caption: "Which genre do you enjoy?",
  hashtags: ["#NTE"],
  sections: [
    {
      start_second: 0,
      end_second: 30,
      purpose: "proof",
      voiceover: "A supernatural urban open world.",
      on_screen_text: "Meet NTE",
      visual_direction: "Create an original title card.",
      knowledge_member_ids: ["fact-1"],
      trend_signal_ids: ["trend-1"],
    },
  ],
};

test("preserves unsaved edits across server refresh and spaces while entering multiple hashtags", () => {
  const save = vi.fn();
  const props = {
    content,
    evidence: [],
    language: "zh-CN" as const,
    disabled: false,
    onSave: save,
  };
  const view = render(<StoryboardEditor {...props} />);
  fireEvent.click(screen.getByText("逐镜编辑（无需填写 JSON）"));
  expect(screen.getByRole("button", { name: "保存为新版本" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("标题"), {
    target: { value: "My revised title" },
  });
  view.rerender(
    <StoryboardEditor {...props} content={structuredClone(content)} />,
  );
  expect(screen.getByLabelText("标题")).toHaveValue("My revised title");
  const tags = screen.getByLabelText("标签（空格分隔）");
  fireEvent.change(tags, { target: { value: "#NTE " } });
  expect(tags).toHaveValue("#NTE ");
  fireEvent.change(tags, { target: { value: "#NTE #OpenWorld" } });
  expect(screen.getByRole("status")).toHaveTextContent("有未保存修改");
  fireEvent.click(screen.getByRole("button", { name: "保存为新版本" }));
  expect(save).toHaveBeenCalledWith({
    ...content,
    title: "My revised title",
    hashtags: ["#NTE", "#OpenWorld"],
  });
  fireEvent.change(screen.getByLabelText("口播"), { target: { value: " " } });
  expect(screen.getByRole("button", { name: "保存为新版本" })).toBeDisabled();
});

test("renders actual evidence without making unsafe source URLs clickable", () => {
  render(
    <EvidenceNotes
      ids={["fact-1"]}
      language="zh-CN"
      evidence={[
        {
          snapshot_member_id: "fact-1",
          predicate: "game.genre",
          value: "Supernatural Urban Open World",
          sources: [
            {
              url: "javascript:alert(1)",
              quote: "Official quote",
              source_version_id: "version-1",
            },
          ],
        },
      ]}
    />,
  );
  fireEvent.click(screen.getByText(/查看支撑事实/));
  expect(screen.getByText("Official quote")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("locates a reviewed fragment, opens the editor and preserves unsaved changes", () => {
  const props = {
    content,
    evidence: [],
    language: "zh-CN" as const,
    disabled: false,
    onSave: vi.fn(),
  };
  const view = render(<StoryboardEditor {...props} />);
  fireEvent.change(screen.getByLabelText("标题"), {
    target: { value: "My unsaved title" },
  });
  view.rerender(
    <StoryboardEditor
      {...props}
      focusTarget={{ field: "sections.0.voiceover", text: "urban", request: 1 }}
    />,
  );
  const voice = screen.getByLabelText("口播") as HTMLTextAreaElement;
  expect(voice).toHaveFocus();
  expect(voice.value.slice(voice.selectionStart, voice.selectionEnd)).toBe(
    "urban",
  );
  expect(voice.closest("details")).toHaveAttribute("open");
  expect(screen.getByLabelText("标题")).toHaveValue("My unsaved title");
});

test("renders structured facts with their subject and scope instead of object placeholders", () => {
  render(
    <EvidenceNotes
      ids={["f0"]}
      language="zh-CN"
      evidence={[
        {
          snapshot_member_id: "f0",
          predicate: "character.ability",
          value: { text: "A protective shield" },
          subject: {
            display_name: "Nera",
            entity_type: "character",
            aliases: [],
          },
          region: "JP",
          game_version: "1.0",
          sources: [],
        },
      ]}
    />,
  );
  expect(screen.getByText("A protective shield")).toBeInTheDocument();
  expect(screen.getByText("Nera")).toBeInTheDocument();
  expect(screen.getByText("JP · 1.0")).toBeInTheDocument();
  expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
});
