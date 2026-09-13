import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { describeApiError, playgroundExecute } from "./api";

function makeResponse(status: number, body: unknown, ok = false): Response {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

describe("describeApiError", () => {
  it("surfaces FastAPI's {detail: ...} shape verbatim", async () => {
    const response = makeResponse(404, { detail: "Agent not found" });
    const message = await describeApiError(response, "/api/workforce/agents/xyz");
    expect(message).toBe("Agent not found");
  });

  it("surfaces the workforce {error, details} shape used by playground blocks", async () => {
    const response = makeResponse(409, {
      error: "budget_exceeded",
      details: { allowed: false, daily_budget: 0, monthly_budget: 0 },
    });
    const message = await describeApiError(response, "/api/workforce/agents/abc/playground");
    expect(message).toContain("budget_exceeded");
    expect(message).toContain("daily_budget");
  });

  it("surfaces {error} with no details object", async () => {
    const response = makeResponse(403, { error: "organization_required" });
    const message = await describeApiError(response, "/api/workforce/agents");
    expect(message).toBe("organization_required");
  });

  it("falls back to the generic message for a non-JSON body", async () => {
    const response = {
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    } as Response;
    const message = await describeApiError(response, "/api/workforce/agents/xyz/playground");
    expect(message).toBe("AegisNex API /api/workforce/agents/xyz/playground returned 500");
  });

  it("falls back to the generic message when the body has neither shape", async () => {
    const response = makeResponse(500, { unrelated: "field" });
    const message = await describeApiError(response, "/api/something");
    expect(message).toBe("AegisNex API /api/something returned 500");
  });
});

describe("playgroundExecute error surfacing (end-to-end through fetchJsonWithRetry)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("rejects with the real budget_exceeded reason instead of a generic 'returned 409'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          makeResponse(409, {
            error: "budget_exceeded",
            details: { allowed: false, daily_budget: 0, monthly_budget: 0 },
          }),
        ),
      ),
    );

    const promise = playgroundExecute("agent-123", { task: "test", simulate: false });
    const assertion = expect(promise).rejects.toThrow(/budget_exceeded/);
    await vi.runAllTimersAsync();
    await assertion;
  });
});
