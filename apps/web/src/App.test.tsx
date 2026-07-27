import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("shows the verified API state", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        status: "ok",
        service: "gamecrafter-api",
        version: "0.1.0",
        environment: "test",
        phase: "M0",
        timestamp: "2026-07-27T00:00:00Z",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<App />);

  await waitFor(() => expect(screen.getByText("API connected")).toBeInTheDocument());
  expect(screen.getByText(/NTE: Neverness to Everness/)).toBeInTheDocument();
});

test("shows a visible failure instead of a fake healthy state", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 503 }));

  render(<App />);

  await waitFor(() => expect(screen.getByText("API unavailable")).toBeInTheDocument());
  expect(screen.getByText("API returned 503")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
});

test("rejects a malformed health payload", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok", service: "unexpected-service" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<App />);

  await waitFor(() => expect(screen.getByText("API unavailable")).toBeInTheDocument());
  expect(screen.getByText("API returned an invalid health payload")).toBeInTheDocument();
});

test("can retry after the API becomes available", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(null, { status: 503 }))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "ok",
          service: "gamecrafter-api",
          version: "0.1.0",
          environment: "test",
          phase: "M0",
          timestamp: "2026-07-27T00:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

  render(<App />);

  const retry = await screen.findByRole("button", { name: "Check again" });
  fireEvent.click(retry);

  await waitFor(() => expect(screen.getByText("API connected")).toBeInTheDocument());
  expect(globalThis.fetch).toHaveBeenCalledTimes(2);
});
