import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
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
});
