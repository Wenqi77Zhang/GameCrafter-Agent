import { afterEach, expect, test, vi } from "vitest";
import { api } from "./client";
afterEach(() => vi.restoreAllMocks());

test("validation messages identify the field and request without echoing sensitive input", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ["body", "password"], msg: "String should have at least 12 characters", input: "secret-value", ctx: { private: "secret-value" } }] }), { status: 422, headers: { "X-Request-ID": "safe-id" } }));
  let message = "";
  try { await api("/api/test"); } catch (error) { message = (error as Error).message; }
  expect(message).toContain("password: String should have at least 12 characters");
  expect(message).toContain("safe-id");
  expect(message).not.toContain("secret-value");
});

test("non-JSON proxy failure is still a clear HTTP error and 204 has no fake payload", async () => {
  const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("Unavailable", { status: 503 })).mockResolvedValueOnce(new Response(null, { status: 204 }));
  await expect(api("/api/test")).rejects.toThrow("HTTP 503");
  await expect(api("/api/test")).resolves.toBeUndefined();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
