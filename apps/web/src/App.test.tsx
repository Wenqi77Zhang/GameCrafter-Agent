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
  snapshots?: Array<Record<string, unknown>>;
  snapshotReadiness?: Record<string, unknown>;
  marketingTasks?: Array<Record<string, unknown>>;
  trendSignals?: Array<Record<string, unknown>>;
  topicCandidates?: Array<Record<string, unknown>>;
  scriptRuns?: Array<Record<string, unknown>>;
}) {
  const projects = options?.projects ?? [project];
  const candidates = options?.candidates ?? [];
  const entities = [...(options?.entities ?? [])];
  const versions = [...(options?.versions ?? [])];
  const claims = [...(options?.claims ?? [])];
  const conflicts = [...(options?.conflicts ?? [])];
  const snapshots = [...(options?.snapshots ?? [])];
  const marketingTasks = [...(options?.marketingTasks ?? [])];
  const trendSignals = [...(options?.trendSignals ?? [])];
  const topicCandidates = [...(options?.topicCandidates ?? [])];
  const scriptRuns = [...(options?.scriptRuns ?? [])];
  const runs: Array<Record<string, unknown>> = [];
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok" });
    if (path === "/api/projects" && init?.method === "POST") return json(project, 201);
    if (path === "/api/projects") return json({ items: projects });
    if (path.endsWith("/candidates")) return json({ items: candidates });
    if (path.endsWith("/sources")) return json({ items: [] });
    if (path.endsWith("/runs") && !path.endsWith("/script-runs")) return json({ items: runs });
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
    if (path.includes("/knowledge-claims/") && path.endsWith("/reviews") && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as {
        decision: "approve" | "approve_with_edit" | "reject" | "defer";
        approved_value: unknown;
        reason: string;
      };
      const claimId = path.split("/knowledge-claims/")[1].split("/")[0];
      const claim = claims.find((item) => item.id === claimId);
      const review = {
        id: "review-1",
        decision: payload.decision,
        approved_value_kind: payload.decision.startsWith("approve") ? claim?.value_kind : null,
        approved_value: payload.decision === "approve" ? claim?.value : payload.approved_value,
        reason: payload.reason,
        reviewer_id: "local-user",
        created_at: "2026-08-15T01:00:00Z",
      };
      if (claim) {
        claim.latest_review = review;
        claim.reviews = [...((claim.reviews as unknown[]) ?? []), review];
        claim.status = payload.decision === "approve" ? "human_approved" : `human_${payload.decision}`;
      }
      return json(review, 201);
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
    if (path.includes("/knowledge-conflicts/") && path.endsWith("/closure") && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { outcome: "resolved" | "dismissed"; reason: string };
      const groupId = path.split("/knowledge-conflicts/")[1].split("/")[0];
      const group = conflicts.find((item) => item.id === groupId);
      if (group) {
        group.status = payload.outcome;
        group.resolution_summary = payload.reason;
      }
      return json({ id: groupId, status: payload.outcome, resolution_summary: payload.reason }, 201);
    }
    if (path.includes("/knowledge-conflicts")) return json({ items: conflicts });
    if (path.endsWith("/knowledge-snapshot-readiness")) {
      return json(
        options?.snapshotReadiness ?? {
          publishable: false,
          schema_version: "knowledge-snapshot-v1",
          content_sha256: null,
          stats: {
            claim_count: claims.length,
            approved_count: 0,
            rejected_count: 0,
            deferred_count: 0,
            unreviewed_count: claims.length,
            open_conflict_count: conflicts.filter((item) => item.status === "open").length,
          },
          blockers: [{ code: claims.length ? "unreviewed_claims" : "no_claims", message: "blocked" }],
          next_version_number: snapshots.length + 1,
          latest_snapshot_id: snapshots[0]?.id ?? null,
        },
      );
    }
    if (path.endsWith("/knowledge-snapshots") && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { notes: string | null };
      const approved = claims.filter((item) => String(item.status).startsWith("human_approved"));
      const snapshot = {
        id: "snapshot-1",
        version_number: snapshots.length + 1,
        is_latest: true,
        schema_version: "knowledge-snapshot-v1",
        content_sha256: "f".repeat(64),
        member_count: approved.length,
        members: approved.map((item) => ({
          claim_id: item.id,
          review_id: (item.latest_review as Record<string, unknown>)?.id,
          subject: {
            entity_id: "entity-1",
            entity_revision_id: "entity-revision-1",
            revision_number: 1,
            canonical_key: "game:nte",
            display_name: "异环",
          },
          predicate: item.predicate,
          value_kind: item.value_kind,
          value: item.value,
          review: item.latest_review,
          evidence: item.evidence,
        })),
        published_by: "local-user",
        notes: payload.notes,
        published_at: "2026-08-15T02:00:00Z",
      };
      snapshots.forEach((item) => { item.is_latest = false; });
      snapshots.unshift(snapshot);
      return json(snapshot, 201);
    }
    if (path.endsWith("/knowledge-snapshots")) return json({ items: snapshots });
    if (path.endsWith("/marketing-tasks")) return json({ items: marketingTasks });
    if (path.endsWith("/trend-signals")) return json({ items: trendSignals });
    if (path.endsWith("/topic-candidates") && init?.method !== "POST") {
      return json({ items: topicCandidates });
    }
    if (path.endsWith("/topic-analysis") && init?.method === "POST") {
      return json({ items: topicCandidates });
    }
    if (path.endsWith("/script-runs")) return json({ items: scriptRuns });
    if (path.includes("/topic-candidates/") && path.endsWith("/reviews") && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { decision: string; reason: string };
      const candidateId = path.split("/topic-candidates/")[1].split("/")[0];
      const candidate = topicCandidates.find((item) => item.id === candidateId);
      const review = { id: "topic-review-1", candidate_id: candidateId, decision: payload.decision, reason: payload.reason, reviewer_id: "local-user", created_at: "2026-08-15T03:00:00Z" };
      if (candidate) {
        candidate.status = payload.decision;
        candidate.review_history = [...((candidate.review_history as unknown[]) ?? []), review];
      }
      return json(review, 201);
    }
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
  expect(screen.getByText("AI 候选 · 每条显示独立人工状态")).toBeInTheDocument();
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
    reviews: [],
    latest_review: null,
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
        resolution_summary: null,
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

  fireEvent.change(screen.getByLabelText("决定理由"), {
    target: { value: "与官网标题及精确证据一致。" },
  });
  fireEvent.click(screen.getByRole("button", { name: "记录人工决定" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-claims/claim-conflict-1/reviews",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": expect.stringContaining("claim-review-") }),
      }),
    ),
  );
  expect(await screen.findByText(/人工决定已追加/)).toBeInTheDocument();
  expect(screen.getByText("与官网标题及精确证据一致。")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "关闭冲突组" }));
  fireEvent.change(screen.getByLabelText("关闭冲突组"), { target: { value: "dismissed" } });
  fireEvent.change(screen.getByLabelText("关闭理由"), {
    target: { value: "人工确认该组无需继续处理。" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认关闭" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-conflicts/conflict-1/closure",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(await screen.findByText("人工确认该组无需继续处理。")).toBeInTheDocument();
});

test("publishes and renders an immutable approved knowledge snapshot", async () => {
  const approval = {
    id: "review-approved-1",
    decision: "approve",
    approved_value_kind: "string",
    approved_value: "Neverness to Everness",
    reason: "Matches exact official evidence.",
    reviewer_id: "local-user",
    created_at: "2026-08-15T01:00:00Z",
  };
  const approvedClaim = {
    id: "claim-approved-1",
    subject_entity_id: "entity-1",
    extraction_run_id: "knowledge-run-1",
    predicate: "game.name",
    value_kind: "string",
    value: "Neverness to Everness",
    normalized_value: "neverness to everness",
    confidence: 0.91,
    locale: "en",
    region: "global",
    status: "human_approved",
    created_at: "2026-08-15T00:00:00Z",
    reviews: [approval],
    latest_review: approval,
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
    claims: [approvedClaim],
    snapshotReadiness: {
      publishable: true,
      schema_version: "knowledge-snapshot-v1",
      content_sha256: "f".repeat(64),
      stats: {
        claim_count: 1,
        approved_count: 1,
        rejected_count: 0,
        deferred_count: 0,
        unreviewed_count: 0,
        open_conflict_count: 0,
      },
      blockers: [],
      next_version_number: 1,
      latest_snapshot_id: null,
    },
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "知识" }));

  expect(await screen.findByRole("heading", { name: "发布知识快照" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("版本备注（可选）"), {
    target: { value: "《异环》官网英文资料首轮人工确认" },
  });
  fireEvent.click(screen.getByRole("button", { name: "发布不可变快照" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/knowledge-snapshots",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": expect.stringContaining("knowledge-snapshot-") }),
      }),
    ),
  );
  expect(await screen.findByText(/知识快照已发布/)).toBeInTheDocument();
  expect(screen.getByText("《异环》官网英文资料首轮人工确认")).toBeInTheDocument();
  expect(screen.getByText("1 条事实")).toBeInTheDocument();
});

test("shows traceable deterministic topic fit and records the human gate", async () => {
  const trend = {
    id: "trend-1",
    source_name: "TikTok Creative Center",
    source_url: "https://ads.tiktok.com/business/creativecenter/trend-1",
    observed_at: "2026-08-15T02:00:00Z",
    region: "US",
    signal_type: "hashtag",
    title: "#NTE",
    keywords: ["NTE"],
    metric_name: "posts",
    metric_value: 1250,
    notes: "Manually verified.",
  };
  const task = {
    id: "marketing-task-1",
    knowledge_snapshot_id: "snapshot-1",
    knowledge_snapshot_version: 1,
    platform: "TikTok",
    markets: ["US", "UK"],
    audience: "Potential new players",
    goal: "Awareness",
    output_language: "en",
    duration_seconds: 30,
    candidate_count: 1,
    approved_candidate_id: null,
    created_at: "2026-08-15T02:10:00Z",
  };
  const candidate = {
    id: "topic-1",
    trend_signal: trend,
    score: 100,
    dimensions: {
      freshness: { score: 25, max: 25 },
      market_alignment: { score: 25, max: 25 },
      source_completeness: { score: 25, max: 25 },
      knowledge_relevance: { score: 25, max: 25 },
    },
    matched_snapshot_member_ids: ["member-1"],
    angle: "Use #NTE as the verified TikTok angle.",
    hook: "What if #NTE happened inside Neverness to Everness?",
    rationale: "Deterministic trend-fit-v1 score 100/100. No model was used.",
    risks: ["manual_source_observation_not_independently_verified"],
    rule_version: "trend-fit-v1",
    status: "unreviewed",
    review_history: [],
  };
  const fetchMock = workspaceFetch({
    snapshots: [{ id: "snapshot-1", version_number: 1, member_count: 1, published_at: "2026-08-15T01:00:00Z" }],
    marketingTasks: [task],
    trendSignals: [trend],
    topicCandidates: [candidate],
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "营销" }));

  expect(await screen.findByText("确定性规则 · 无模型调用")).toBeInTheDocument();
  expect(screen.getByText("What if #NTE happened inside Neverness to Everness?")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("决定理由"), {
    target: { value: "趋势来源、市场与知识证据均符合本次目标。" },
  });
  fireEvent.click(screen.getByRole("button", { name: "记录人工决定" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/marketing-tasks/marketing-task-1/topic-candidates/topic-1/reviews",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(await screen.findByText("趋势来源、市场与知识证据均符合本次目标。")).toBeInTheDocument();
});

test("renders the zero-cost script evaluation and final human gate", async () => {
  const task = {
    id: "marketing-task-approved",
    platform: "TikTok",
    duration_seconds: 30,
    output_language: "en",
    approved_candidate_id: "topic-1",
    created_at: "2026-08-15T02:10:00Z",
  };
  const content = {
    schema_version: "tiktok-script-v1",
    platform: "TikTok",
    output_language: "en",
    duration_seconds: 30,
    title: "Neverness to Everness: #NTE",
    caption: "A verified first look.",
    hashtags: ["#NTE", "#GameTok"],
    sections: [
      { start_second: 0, end_second: 6, purpose: "hook", voiceover: "What if this trend entered NTE?", on_screen_text: "#NTE", visual_direction: "Official footage.", knowledge_member_ids: [], trend_signal_ids: ["trend-1"] },
      { start_second: 6, end_second: 30, purpose: "cta", voiceover: "Would you play? Follow for verified updates.", on_screen_text: "Follow", visual_direction: "Official key art.", knowledge_member_ids: ["member-1"], trend_signal_ids: [] },
    ],
  };
  workspaceFetch({
    marketingTasks: [task],
    scriptRuns: [{
      id: "script-run-1", marketing_task_id: task.id, revision_budget: 2, revisions_used: 0,
      score_threshold: 80, generator_version: "tiktok-template-v1", evaluator_version: "script-quality-v1",
      created_at: "2026-08-15T03:00:00Z",
      versions: [{ id: "script-version-1", version_number: 1, origin: "generated", content, content_sha256: "a".repeat(64), created_at: "2026-08-15T03:01:00Z" }],
      evaluations: [{ id: "evaluation-1", script_version_id: "script-version-1", score: 100, passed: true, dimensions: { evidence_lineage: { score: 20, max: 20 } }, issues: [], rule_version: "script-quality-v1" }],
      final_reviews: [],
    }],
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "创作" }));

  expect(await screen.findByRole("heading", { name: "证据约束的 TikTok 脚本" })).toBeInTheDocument();
  expect(screen.getByText("确定性模板 + 确定性评测 · 零模型费用")).toBeInTheDocument();
  expect(screen.getByText("100/100")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeDisabled();
  expect(screen.getByRole("heading", { name: "人工终审" })).toBeInTheDocument();
});
