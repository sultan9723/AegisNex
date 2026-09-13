import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const routeParams = vi.hoisted(() => ({ current: { id: "1" } }));

vi.mock("next/navigation", () => ({
  useParams: () => routeParams.current,
}));

import ClientEvidencePage from "./page";

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("Client evidence page", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    routeParams.current = { id: "1" };
  });

  it("loads a real client and renders incidents assigned to the same canonical id", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/orgs/1")) {
        return jsonResponse({
          id: 1,
          name: "Kammand",
          slug: "kammand",
          domain: "kammand.com",
          settings: {},
          is_active: true,
          created_at: "2026-09-11T11:32:17Z",
        });
      }
      if (url.endsWith("/api/orgs/1/stats")) {
        return jsonResponse({ org_id: 1, user_count: 0, team_count: 0, project_count: 0 });
      }
      if (url.endsWith("/api/incidents?limit=1000&org_id=1")) {
        return jsonResponse({
          active_incidents: [],
          resolved_incidents: [],
          recent_incidents: [],
          incidents: [{
            incident_id: "INC-KAMMAND-1",
            timestamp: "2026-09-11T12:00:00Z",
            severity: "high",
            service_name: "kammand-api",
            description: "Assigned incident",
            org_id: 1,
            org_name: "Kammand",
            status: "active",
            incident_status: "active",
            remediation_history: [],
          }],
          active_count: 1,
          resolved_count: 0,
          count: 1,
          total: 1,
        });
      }
      if (url.endsWith("/api/approvals?limit=100")) {
        return jsonResponse({ approvals: [], count: 0 });
      }
      return jsonResponse({ detail: `Unhandled ${url}` }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientEvidencePage />);

    expect(await screen.findByRole("heading", { name: "Kammand" })).toBeInTheDocument();
    expect(await screen.findByText("kammand-api")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/incidents?limit=1000&org_id=1"))).toBe(true);
  });

  it("shows the proper invalid-client-id error without calling the backend", async () => {
    routeParams.current = { id: "not-a-number" };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientEvidencePage />);

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Invalid client id")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalled());
  });
});
