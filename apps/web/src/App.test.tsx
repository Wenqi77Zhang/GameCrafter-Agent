import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const project = { id: "project-1", slug: "nte", name: "异环", default_locale: "zh-CN" };

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

function workspaceFetch(options?: { projects?: typeof project[]; candidates?: unknown[] }) {
  const projects = options?.projects ?? [project];
  const candidates = options?.candidates ?? [];
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok" });
    if (path === "/api/projects" && init?.method === "POST") return json(project, 201);
    if (path === "/api/projects") return json({ items: projects });
    if (path.endsWith("/candidates")) return json({ items: candidates });
    if (path.endsWith("/sources")) return json({ items: [] });
    if (path.endsWith("/runs")) return json({ items: [] });
    if (path.endsWith("/source-imports")) {
      return json(
        {
          id: "run-1",
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
