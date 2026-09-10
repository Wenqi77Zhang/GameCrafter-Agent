import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import {
  CreativeProgress,
  ReasonChoices,
  StrategyAssistant,
  useCreativeAssistant,
} from "./CreativeAssistant";

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("persists and resumes a queued operation, then presents a concrete strategy", async () => {
  let submitted = false;
  let finished = false;
  const operation = {
    id: "op-1",
    run_id: "wf-1",
    target_id: "task-1",
    candidate_id: "candidate-1",
    operation: "strategy",
    status: "queued",
    checkpoint: "created",
    error: null,
    model: "fixture-only",
    result: {},
  };
  const strategy = {
    marketing_direction: "从城市探索切入",
    recommended_topic: "用玩家好奇心解释游戏看点",
    why_it_fits: "来自已审核的游戏资料，不承诺热点表现",
    target_audience: "新玩家",
    english_hooks: ["A city with a secret?", "Would you explore this?"],
    execution_steps: ["展示城市", "展示已核实的细节", "提出问题"],
    risks: ["素材权利需核验"],
    measurement_plan: "比较两个开场的留存和评论。",
    knowledge_member_ids: ["fact-1"],
  };
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_path, init) => {
      if (String(_path).includes("capability"))
        return json({ available: true, model: "fixture-only" });
      if (init?.method === "POST") {
        submitted = true;
        return json(operation);
      }
      return json({
        items: submitted
          ? [
              {
                ...operation,
                status: finished ? "succeeded" : "queued",
                checkpoint: finished ? "completed" : "created",
                result: finished
                  ? {
                      strategy,
                      passed: true,
                      review: { summary: "测试评审通过", issues: [] },
                    }
                  : {},
              },
            ]
          : [],
      });
    });
  const view = render(
    <StrategyAssistant
      projectId="project-1"
      taskId="task-1"
      candidateId="candidate-1"
      language="zh-CN"
    />,
  );
  const button = await screen.findByRole("button", {
    name: "生成具体营销建议",
  });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  expect(await screen.findByText("等待后台处理")).toBeInTheDocument();
  expect(
    fetcher.mock.calls.filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(1);
  view.unmount();
  finished = true;
  render(
    <StrategyAssistant
      projectId="project-1"
      taskId="task-1"
      candidateId="candidate-1"
      language="zh-CN"
    />,
  );
  expect(await screen.findByText("从城市探索切入")).toBeInTheDocument();
  expect(screen.getByText("A city with a secret?")).toBeInTheDocument();
  expect(screen.getByText("比较两个开场的留存和评论。")).toBeInTheDocument();
});

test("failure remains visible and cannot pretend to be a completed script", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (path) =>
    json(
      String(path).includes("capability")
        ? { available: true, model: "fixture" }
        : {
            items: [
              {
                id: "failed",
                run_id: "wf",
                target_id: "task",
                operation: "write",
                status: "needs_attention",
                checkpoint: "creative.write",
                model: "fixture",
                error: "模型输出未通过结构校验",
                result: {},
              },
            ],
          },
    ),
  );
  function Probe() {
    const a = useCreativeAssistant("project", "task");
    return <CreativeProgress assistant={a} language="zh-CN" />;
  }
  render(<Probe />);
  expect(await screen.findByText("模型输出未通过结构校验")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试未完成步骤" })).toBeEnabled();
  expect(screen.queryByText("结果已保存")).not.toBeInTheDocument();
});

test("preset reasons require an explicit choice; free text is only requested for other", async () => {
  const changed = vi.fn();
  render(
    <ReasonChoices
      value=""
      onChange={changed}
      language="zh-CN"
      label="审核原因"
      choices={["内容已核验"]}
    />,
  );
  expect(changed).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "内容已核验" }));
  expect(changed).toHaveBeenCalledWith("内容已核验");
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "其他原因" })),
  );
  expect(screen.getByRole("textbox", { name: "审核原因" })).toBeRequired();
});
