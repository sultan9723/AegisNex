import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import ClientsPage from "./page";

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("Clients page", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("uses the canonical client id from /api/orgs for the evidence link and scoped counts", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/orgs")) {
        return jsonResponse({
          organizations: [{
            id: 1,
            name: "Kammand",
            slug: "kammand",
            domain: "kammand.com",
            settings: {},
            is_active: true,
            created_at: "2026-09-11T11:32:17Z",
          }],
          count: 1,
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
          incidents: [],
          active_count: 0,
          resolved_count: 0,
          count: 0,
          total: 0,
        });
      }
      return jsonResponse({ detail: `Unhandled ${url}` }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientsPage />);

    expect(await screen.findByText("Kammand")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open evidence view/i })).toHaveAttribute("href", "/clients/1");
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(2);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/incidents?limit=1000&org_id=1"))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/incidents?limit=1000"))).toBe(false);
  });
});
