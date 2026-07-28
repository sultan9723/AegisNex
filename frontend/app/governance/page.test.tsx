import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import GovernancePage from "./page";

const plannerAgent = {
  agent_id: "planner",
  id: "planner",
  name: "Planner",
  agent_type: "planning",
  description: "Breaks requests into plans",
  owner: "AegisNex AI Platform",
  team: "intelligence",
  department: "AI Platform",
  purpose: "Plan multi-step agent work before execution.",
  provider: "openai",
  model: "gpt-4o",
  version: "2.3.0",
  status: "active",
  risk_level: "medium",
  trust_score: 91,
  daily_budget: 45,
  monthly_budget: 1200,
  average_cost: 0.018,
  average_latency: 1180,
  success_rate: 96.4,
  permissions: ["plan:create", "context:read"],
  connected_tools: ["rag_search", "tool_router"],
  policies: ["global-registered-agent-default-allow"],
  approval_required: false,
  allowed_tools: ["rag_search", "tool_router"],
  allowed_resources: ["/api/ai/plan"],
  max_actions_per_hour: 180,
  total_actions: 2,
  execution_count: 2,
  total_denied: 0,
  total_anomalies: 0,
  created_at: "2026-07-16T12:00:00Z",
  last_active_at: "2026-07-16T13:00:00Z",
  last_execution: "2026-07-16T13:00:00Z",
};

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("Governance agent registry", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/governance/stats")) {
        return jsonResponse({
          total_agents: 1,
          active_agents: 1,
          by_risk: { medium: 1 },
          by_type: { planning: 1 },
          total_actions: 2,
          total_denied: 0,
          open_anomalies: 0,
          avg_trust_score: 91,
        });
      }
      if (url.endsWith("/governance/agents")) {
        return jsonResponse({ agents: [plannerAgent] });
      }
      if (url.includes("/governance/actions")) {
        return jsonResponse({ actions: [] });
      }
      if (url.endsWith("/governance/policies")) {
        return jsonResponse({ policies: [] });
      }
      if (url.includes("/approvals")) {
        return jsonResponse({ approvals: [] });
      }
      if (url.includes("/governance/anomalies")) {
        return jsonResponse({ anomalies: [] });
      }
      if (url.endsWith("/governance/agents/planner")) {
        return jsonResponse(plannerAgent);
      }
      if (url.includes("/governance/agents/planner/history")) {
        return jsonResponse({
          history: [{
            action_id: "run-1",
            agent_id: "planner",
            action_type: "plan",
            action_summary: "Built a 5-step remediation plan",
            target_resource: "/api/ai/plan",
            reasoning: "Selected safe read-only tools",
            confidence_score: 0.95,
            policy_verdict: "allowed",
            status: "success",
            duration_ms: 1180,
            created_at: "2026-07-16T13:00:00Z",
          }],
        });
      }
      if (url.includes("/governance/agents/planner/policies")) {
        return jsonResponse({ policies: [{ name: "global-registered-agent-default-allow" }] });
      }
      if (url.includes("/governance/agents/planner/tools")) {
        return jsonResponse({
          agent_id: "planner",
          tools: ["rag_search", "tool_router"],
          permissions: ["plan:create", "context:read"],
          resources: ["/api/ai/plan"],
        });
      }
      if (url.includes("/governance/agents/planner/metrics")) {
        return jsonResponse({
          agent_id: "planner",
          execution_count: 2,
          history_count: 2,
          success_rate: 96.4,
          average_cost: 0.018,
          average_latency: 1180,
          average_confidence: 0.95,
          denied_count: 0,
          trust_score: 91,
          daily_budget: 45,
          monthly_budget: 1200,
          last_execution: "2026-07-16T13:00:00Z",
        });
      }
      return jsonResponse({});
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the agent registry table and detail drawer", async () => {
    render(<GovernancePage />);

    fireEvent.click(await screen.findByRole("button", { name: /Agent Registry/i }));

    expect(await screen.findByText("Registered agents")).toBeInTheDocument();
    expect(screen.getByText("Planner")).toBeInTheDocument();
    expect(screen.getByText("AegisNex AI Platform")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("$1,200")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Planner"));

    await waitFor(() => expect(screen.getByLabelText("Agent details")).toBeInTheDocument());
    expect(screen.getByText("Plan multi-step agent work before execution.")).toBeInTheDocument();
    expect(screen.getByText("plan:create")).toBeInTheDocument();
    expect(screen.getByText("rag_search")).toBeInTheDocument();
    expect(screen.getByText("Built a 5-step remediation plan")).toBeInTheDocument();
    expect(screen.getAllByText("96.4%").length).toBeGreaterThanOrEqual(1);
  });
});
