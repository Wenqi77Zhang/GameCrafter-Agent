import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { EvidenceReview, type FactCheck } from "./EvidenceReview";

afterEach(cleanup);
const checks: FactCheck[] = [
  {
    text_id: "t0",
    field: "sections.2.voiceover",
    section_index: 2,
    text: "Every shop sells flying cars.",
    verdict: "UNSUPPORTED",
    reason: "只有商店证据，没有商品证据。",
    knowledge_member_ids: ["f0"],
    evidence_quotes: ["A street of shops."],
  },
  {
    text_id: "t1",
    field: "caption",
    section_index: null,
    text: "What do you enjoy?",
    verdict: "NOT_A_FACT",
    reason: "观众偏好问题。",
    knowledge_member_ids: [],
  },
];

test("shows risks first, explains coverage, and locates the exact field without approving", () => {
  const edit = vi.fn();
  render(<EvidenceReview checks={checks} language="zh-CN" onEdit={edit} />);
  expect(screen.getByText(/已覆盖 2 段/)).toHaveTextContent("需核对 1");
  expect(screen.getByText(/覆盖数不是准确率/)).toBeInTheDocument();
  expect(screen.queryByText("What do you enjoy?")).not.toBeInTheDocument();
  expect(screen.getByText("分镜 3 · 口播")).toBeInTheDocument();
  fireEvent.click(screen.getByText("核对模型引用的已审核事实原句"));
  expect(screen.getByText("A street of shops.")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "定位并编辑：分镜 3 · 口播" }),
  );
  expect(edit).toHaveBeenCalledWith(checks[0]);
  fireEvent.click(screen.getByRole("button", { name: "全部 2" }));
  expect(screen.getByText("What do you enjoy?")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "批准" }),
  ).not.toBeInTheDocument();
});

test("does not fabricate coverage for legacy reviews and provides readable English", () => {
  const view = render(<EvidenceReview checks={[]} language="en" />);
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
  view.rerender(<EvidenceReview checks={[checks[1]]} language="en" />);
  expect(screen.getByText("Caption")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "To check 0" }));
  expect(screen.getByText(/this is not human approval/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Locate and edit/ }),
  ).not.toBeInTheDocument();
});
