import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import MissionControlPage from "./page";
import { getMissionControlWebSocketUrl } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

const realExecution = {
  execution_id: "mc-real-001",
  request: "Investigate production API latency",
  user: "operator@example.com",
  timestamp: "2026-09-11T10:00:00Z",
  current_status: "completed",
  total_latency_ms: 120,
  total_cost: 0,
  confidence: 0.91,
  overall_result: "Latency reviewed",
  stages: [
    {
      stage_id: "planner",
      start_time: null,
      finish_time: null,
      latency_ms: 120,
      status: "completed",
      confidence: 0.91,
      model: "gpt-4o-mini",
      provider: "openai",
      tokens: 32,
      estimated_cost: 0,
      summary: "Plan complete",
      connected_tools: [],
      evidence: [],
      policy_decisions: [],
      inputs: {},
      outputs: {},
    },
  ],
  error: "",
  metadata: {},
  execution_type: "analyze",
  organization: "",
  agents: ["ops-agent"],
  audit_links: {},
};

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

class MockWebSocket {
  static urls: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.urls.push(url);
    queueMicrotask(() => this.onopen?.());
  }

  close() {
    this.onclose?.();
  }
}

describe("Mission Control page", () => {
  beforeEach(() => {
    MockWebSocket.urls = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    setAccessToken("mission-token");
    process.env.NEXT_PUBLIC_WS_URL = "ws://localhost:8000";
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    setAccessToken(null);
    delete process.env.NEXT_PUBLIC_WS_URL;
  });

  it("loads and renders real backend executions with credentials", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/mission-control/executions")) {
        return jsonResponse({ executions: [realExecution], count: 1, total: 1, limit: 20, offset: 0 });
      }
      if (url.includes("/mission-control/stats")) {
        return jsonResponse({
          total: 1,
          completed: 1,
          failed: 0,
          running: 0,
          queued: 0,
          avg_latency: 120,
          avg_cost: 0,
          avg_confidence: 0.91,
          total_cost: 0,
          type_count: 1,
          user_count: 1,
        });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MissionControlPage />);

    expect(await screen.findByText("Investigate production API latency")).toBeInTheDocument();
    expect(screen.queryByText("No executions found")).not.toBeInTheDocument();
    const executionsCall = fetchMock.mock.calls.find(([input]) => String(input).includes("/mission-control/executions"));
    expect(executionsCall?.[1]).toMatchObject({ credentials: "include" });
  });

  it("shows a visible failure state instead of parsing non-2xx as valid data", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/refresh")) {
        return jsonResponse({ detail: "refresh failed" }, 401);
      }
      return jsonResponse({ detail: "Forbidden" }, 403);
    }));

    render(<MissionControlPage />);

    expect(await screen.findByText("Something went wrong", {}, { timeout: 6000 })).toBeInTheDocument();
    // The backend's real {"detail": "Forbidden"} reason must reach the UI,
    // not just a generic "returned 403".
    expect(screen.getByText("Forbidden")).toBeInTheDocument();
    expect(screen.queryByText("No executions found")).not.toBeInTheDocument();
  }, 10000);

  it("connects the websocket to the configured mission-control path with token auth", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/mission-control/executions")) {
        return jsonResponse({ executions: [], count: 0, total: 0, limit: 20, offset: 0 });
      }
      if (url.includes("/mission-control/stats")) {
        return jsonResponse({
          total: 0,
          completed: 0,
          failed: 0,
          running: 0,
          queued: 0,
          avg_latency: 0,
          avg_cost: 0,
          avg_confidence: 0,
          total_cost: 0,
          type_count: 0,
          user_count: 0,
        });
      }
      return jsonResponse({});
    }));

    render(<MissionControlPage />);

    await waitFor(() => {
      expect(MockWebSocket.urls).toContain("ws://localhost:8000/ws/mission-control?token=mission-token");
    });
  });
});

describe("Mission Control API helpers", () => {
  afterEach(() => {
    setAccessToken(null);
    delete process.env.NEXT_PUBLIC_WS_URL;
  });

  it("builds the authenticated mission-control websocket URL", () => {
    process.env.NEXT_PUBLIC_WS_URL = "ws://localhost:8000";
    setAccessToken("abc 123");

    expect(getMissionControlWebSocketUrl()).toBe("ws://localhost:8000/ws/mission-control?token=abc%20123");
  });
});
