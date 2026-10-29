import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ScriptWorkspace } from "./ScriptWorkspace";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("restoring an older completed model task never replaces the latest human edit", async () => {
  const content = {
    schema_version: "1",
    platform: "TikTok",
    output_language: "en",
    duration_seconds: 30,
    title: "Older model draft",
    caption: "A fixture caption",
    hashtags: ["#Example"],
    sections: [
      {
        start_second: 0,
        end_second: 30,
        purpose: "proof",
        voiceover: "A fixture voiceover",
        on_screen_text: "Fixture",
        visual_direction: "Original text card",
        knowledge_member_ids: [],
        trend_signal_ids: [],
      },
    ],
  };
  const version = {
    id: "v1",
    version_number: 1,
    origin: "generated",
    content,
    content_sha256: "a".repeat(64),
    created_at: "2026-09-11T00:00:00Z",
    generation_metadata: { mode: "local_model" },
  };
  const task = {
    id: "task-1",
    platform: "TikTok",
    duration_seconds: 30,
    output_language: "en",
    approved_candidate_id: "candidate-1",
    created_at: "2026-09-11T00:00:00Z",
  };
  const run = {
    id: "run-1",
    marketing_task_id: task.id,
    revision_budget: 2,
    revisions_used: 0,
    score_threshold: 80,
    generator_version: "test",
    evaluator_version: "test",
    created_at: task.created_at,
    versions: [
      version,
      {
        ...version,
        id: "v2",
        version_number: 2,
        origin: "human_edit",
        parent_version_id: "v1",
        content: { ...content, title: "Human corrected latest" },
        generation_metadata: { requires_semantic_review: true },
      },
    ],
    evaluations: [],
    final_reviews: [],
    evidence: [],
  };
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const path = String(input);
      const payload = path.includes("creative-capability")
        ? { available: false, model: "test" }
        : path.includes("creative-operations")
          ? {
              items: [
                {
                  id: "op-1",
                  run_id: "workflow-1",
                  target_id: "run-1",
                  operation: "write",
                  status: "succeeded",
                  checkpoint: "completed",
                  error: null,
                  model: "test",
                  result: { version_id: "v1" },
                },
              ],
            }
          : path.endsWith("script-runs")
            ? { items: [run] }
            : { items: [task] };
      return new Response(JSON.stringify(payload), {
        headers: { "Content-Type": "application/json" },
      });
    });
  await act(async () => {
    render(<ScriptWorkspace projectId="project-1" language="zh-CN" />);
  });
  expect(
    fetcher.mock.calls.some(([url]) =>
      String(url).includes("creative-operations"),
    ),
  ).toBe(true);
  expect(
    screen.getByRole("heading", { name: "Human corrected latest" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("脚本版本")).toHaveValue("v2");
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeDisabled();
});
