import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const project = { id: "project-1", slug: "nte", name: "异环", default_locale: "zh-CN" };
const entity = {
  id: "entity-1",
  project_id: "project-1",
  entity_type: "game",
  canonical_key: "game:nte",
  display_name: "异环",
  aliases: ["NTE: Neverness to Everness"],
  status: "active",
  revision_number: 1,
  created_at: "2026-08-15T00:00:00Z",
  revised_at: "2026-08-15T00:00:00Z",
};
const sourceVersion = {
  id: "version-1",
  source_id: "source-1",
  version_number: 1,
  is_latest: true,
  title: "NTE official homepage",
  url: "https://nte.perfectworld.com/en/",
  site: "nte-global",
  locale: "en",
  region: "global",
  source_type: "overview",
  source_status: "active",
  fetched_at: "2026-08-15T00:00:00Z",
  normalized_text_sha256: "a".repeat(64),
  normalized_text_available: true,
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener() {}
  close() {}
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function workspaceFetch(options?: {
  projects?: typeof project[];
  candidates?: unknown[];
  entities?: Array<Record<string, unknown>>;
  versions?: Array<Record<string, unknown>>;
  claims?: Array<Record<string, unknown>>;
  conflicts?: Array<Record<string, unknown>>;
  capability?: Record<string, unknown>;
}) {
  const projects = options?.projects ?? [project];
  const candidates = options?.candidates ?? [];
  const entities = [...(options?.entities ?? [])];
  const versions = [...(options?.versions ?? [])];
  const claims = [...(options?.claims ?? [])];
  const conflicts = [...(options?.conflicts ?? [])];
  const runs: Array<Record<string, unknown>> = [];
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok" });
    if (path === "/api/projects" && init?.method === "POST") return json(project, 201);
    if (path === "/api/projects") return json({ items: projects });
    if (path.endsWith("/candidates")) return json({ items: candidates });
    if (path.endsWith("/sources")) return json({ items: [] });
    if (path.endsWith("/runs")) return json({ items: runs });
    if (path.endsWith("/knowledge-entities") && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { display_name: string; aliases: string[] };
      const created = { ...entity, display_name: payload.display_name, aliases: payload.aliases };
      entities.splice(0, entities.length, created);
      return json(created, 201);
    }
    if (path.endsWith("/knowledge-entities")) return json({ items: entities });
    if (path.includes("/knowledge-entities/entity-1") && init?.method === "PUT") {
      const payload = JSON.parse(String(init.body)) as { display_name: string; aliases: string[] };
      const corrected = {
        ...entity,
        display_name: payload.display_name,
        aliases: payload.aliases,
        revision_number: 2,
      };
      entities.splice(0, entities.length, corrected);
      return json(corrected);
    }
    if (path.endsWith("/source-versions")) return json({ items: versions });
    if (path.includes("/knowledge-extraction-capability")) {
      return json(
        options?.capability ?? {
          available: false,
          mode: "disabled",
          reason_code: "provider_disabled",
          reason: "disabled",
        },
      );
    }
    if (path.includes("/knowledge-claims")) return json({ items: claims });
    if (path.endsWith("/knowledge-conflicts/reconcile") && init?.method === "POST") {
      return json({
        policy_version: "claim-conflict-v1",
        compared_scopes: conflicts.length,
        created_groups: 0,
        created_members: 0,
        skipped_closed_groups: 0,
      });
    }
    if (path.includes("/knowledge-conflicts")) return json({ items: conflicts });
    if (path.endsWith("/knowledge-extractions") && init?.method === "POST") {
      const run = {
        id: "knowledge-run-1",
        workflow_kind: "knowledge.extract",
        task_type: "knowledge.extract",
        status: "queued",
        checkpoint: "created",
        last_error_code: null,
        last_error_detail: null,
        created_at: "2026-08-15T00:00:00Z",
        finished_at: null,
      };
      runs.splice(0, runs.length, run);
      return json(run, 202);
    }
    if (path.endsWith("/source-imports")) {
      return json(
        {
          id: "run-1",
          workflow_kind: "source.capture",
          task_type: "source.capture",
          status: "queued",
          checkpoint: "created",
          last_error_code: null,
          last_error_detail: null,
          created_at: "2026-07-29T00:00:00Z",
          finished_at: null,
        },
        202,
      );
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

beforeEach(() => {
  localStorage.clear();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("crypto", { randomUUID: () => "request-uuid" });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("defaults to Simplified Chinese and loads the NTE source workspace", async () => {
  workspaceFetch();
  render(<App />);

  await screen.findByRole("heading", { name: "把公开资料变成可复核的游戏知识。" });
  expect(screen.getByText("公开官网资料是可追溯证据，不等同于游戏公司的内部 GDD。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "English" })).toBeInTheDocument();
  expect(screen.getByText("异环")).toBeInTheDocument();
  expect(screen.getByText("暂无待选候选。先运行一次来源发现。")).toBeInTheDocument();
});

test("switches to English and remembers the preference", async () => {
  workspaceFetch();
  render(<App />);
  const language = await screen.findByRole("button", { name: "English" });

  fireEvent.click(language);

  expect(screen.getByRole("heading", { name: "Turn public material into reviewable game knowledge." })).toBeInTheDocument();
  expect(localStorage.getItem("gamecrafter-language")).toBe("en");
  expect(screen.getByRole("button", { name: "简体中文" })).toBeInTheDocument();
});

test("can create the local NTE validation project", async () => {
  const fetchMock = workspaceFetch({ projects: [] });
  render(<App />);
  const create = await screen.findByRole("button", { name: "创建《异环》项目" });

  fireEvent.click(create);

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects",
      expect.objectContaining({ method: "POST" }),
    ),
  );
});

test("requires a human click before importing a discovered candidate", async () => {
  const candidate = {
    id: "candidate-1",
    title: "Official NTE update",
    url: "https://nte.perfectworld.com/en/article/news/update.html",
    site: "nte-global",
    locale: "en",
    region: "global",
    source_type: "update",
    published_at: "2026-07-29T00:00:00Z",
    classification_basis: "official listing metadata",
    status: "discovered",
  };
  const fetchMock = workspaceFetch({ candidates: [candidate] });
  render(<App />);
  const importButton = await screen.findByRole("button", { name: "选择并导入" });

  fireEvent.click(importButton);

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/source-imports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ candidate_id: "candidate-1" }),
      }),
    ),
  );
  await waitFor(() =>
    expect(FakeEventSource.instances[0]?.url).toBe("/api/runs/run-1/events"),
  );
});

test("shows a visible API failure instead of a fake healthy state", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 503 }));
  render(<App />);

  expect(await screen.findByRole("heading", { name: "本地 API 暂不可用" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试连接" })).toBeInTheDocument();
});

test("runs exact zero-cost extraction without leaving the Knowledge workspace", async () => {
  const fetchMock = workspaceFetch({
    entities: [entity],
    versions: [sourceVersion],
    capability: {
      available: true,
      mode: "offline_replay",
      reason_code: "available",
      reason: "available",
    },
  });
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "知识" }));
  expect(await screen.findByRole("heading", { name: "知识提取工作台" })).toBeInTheDocument();
  expect(await screen.findByText("离线回放可用")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "开始提取" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-extractions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ source_version_id: "version-1", subject_entity_id: "entity-1" }),
      }),
    ),
  );
  expect(await screen.findByText("知识提取已进入本地队列。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "知识" })).toHaveClass("active");
  expect(FakeEventSource.instances.at(-1)?.url).toBe("/api/runs/knowledge-run-1/events");
});

test("renders the server-stored exact quote and source lineage", async () => {
  workspaceFetch({
    entities: [entity],
    versions: [sourceVersion],
    claims: [
      {
        id: "claim-1",
        subject_entity_id: "entity-1",
        extraction_run_id: "knowledge-run-1",
        predicate: "game.developer",
        value_kind: "string",
        value: "Hotta Studio",
        confidence: 0.96,
        locale: "en",
        region: "global",
        status: "candidate_unreviewed",
        created_at: "2026-08-15T00:00:00Z",
        evidence: [
          {
            source_version_id: "version-1",
            source_id: "source-1",
            source_url: "https://nte.perfectworld.com/en/",
            source_title: "NTE official homepage",
            source_version_number: 1,
            locale: "en",
            region: "global",
            fetched_at: "2026-08-15T00:00:00Z",
            ordinal: 0,
            start_offset: 8,
            end_offset: 36,
            quote: "Developed by Hotta Studio.",
            quote_sha256: "b".repeat(64),
          },
        ],
      },
    ],
  });
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "知识" }));

  expect(await screen.findByText("Developed by Hotta Studio.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "NTE official homepage" })).toHaveAttribute(
    "href",
    "https://nte.perfectworld.com/en/",
  );
  expect(screen.getAllByText("AI 候选 · 未经人工审核").length).toBeGreaterThan(0);
  expect(screen.getByText("8–36")).toBeInTheDocument();
});

test("creates and corrects a generic game entity through auditable forms", async () => {
  const fetchMock = workspaceFetch({ entities: [], versions: [] });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "知识" }));

  fireEvent.click(await screen.findByRole("button", { name: "新建游戏实体" }));
  fireEvent.change(screen.getByLabelText("游戏名称"), { target: { value: "异环" } });
  fireEvent.change(screen.getByLabelText(/^英文名或其他别名/), {
    target: { value: "NTE, Neverness to Everness" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建实体" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-entities",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          display_name: "异环",
          aliases: ["NTE", "Neverness to Everness"],
        }),
      }),
    ),
  );
  fireEvent.click(await screen.findByRole("button", { name: "纠正名称" }));
  fireEvent.change(screen.getByLabelText("游戏名称"), {
    target: { value: "异环（Neverness to Everness）" },
  });
  fireEvent.change(screen.getByLabelText("修改原因"), { target: { value: "修正输入错误" } });
  fireEvent.click(screen.getByRole("button", { name: "保存纠正" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-entities/entity-1",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
});

test("offers a direct Sources shortcut when no evidence version exists", async () => {
  workspaceFetch({ entities: [entity], versions: [] });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "知识" }));

  fireEvent.click(await screen.findByRole("button", { name: "去添加来源" }));

  expect(screen.getByRole("button", { name: /^来源/ })).toHaveClass("active");
  expect(screen.getByText("暂无待选候选。先运行一次来源发现。")).toBeInTheDocument();
});

test("shows deterministic conflict relations and preserves evidence navigation", async () => {
  const conflictingClaim = {
    id: "claim-conflict-1",
    subject_entity_id: "entity-1",
    extraction_run_id: "knowledge-run-1",
    predicate: "game.name",
    value_kind: "string",
    value: "Neverness to Everness",
    normalized_value: "neverness to everness",
    confidence: 0.91,
    locale: "en",
    region: "global",
    status: "candidate_unreviewed",
    created_at: "2026-08-15T00:00:00Z",
    evidence: [
      {
        source_version_id: "version-1",
        source_id: "source-1",
        source_url: "https://nte.perfectworld.com/en/",
        source_title: "NTE official homepage",
        source_version_number: 1,
        locale: "en",
        region: "global",
        fetched_at: "2026-08-15T00:00:00Z",
        ordinal: 0,
        start_offset: 0,
        end_offset: 21,
        quote: "Neverness to Everness",
        quote_sha256: "d".repeat(64),
      },
    ],
  };
  const fetchMock = workspaceFetch({
    entities: [entity],
    versions: [sourceVersion],
    claims: [conflictingClaim],
    conflicts: [
      {
        id: "conflict-1",
        predicate: "game.name",
        status: "open",
        policy_version: "claim-conflict-v1",
        member_count: 2,
        distinct_value_count: 2,
        subject: entity,
        members: [
          {
            relation: "conflicting",
            basis: "claim-conflict-v1: single-valued exact scope",
            claim: conflictingClaim,
          },
          {
            relation: "conflicting",
            basis: "claim-conflict-v1: single-valued exact scope",
            claim: {
              ...conflictingClaim,
              id: "claim-conflict-2",
              value: "NTE",
              normalized_value: "nte",
            },
          },
        ],
      },
    ],
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "知识" }));

  expect(await screen.findByRole("heading", { name: "事实冲突检查" })).toBeInTheDocument();
  expect(await screen.findByText("待处理")).toBeInTheDocument();
  expect(screen.getAllByText("冲突").length).toBeGreaterThan(0);
  expect(screen.getByText("2 个不同值 · 2 条候选")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "检测冲突" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-conflicts/reconcile",
      { method: "POST" },
    ),
  );
  expect(await screen.findByText(/冲突检查完成/)).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: /Neverness to Everness/ }).at(-1)!);
  expect(screen.getByText("0–21")).toBeInTheDocument();
});
