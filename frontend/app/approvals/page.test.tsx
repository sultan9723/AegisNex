import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import ApprovalsPage from "./page";
import type { ApprovalRequest } from "@/lib/api";

const pendingApproval = {
  approval_id: "apr-pending-1",
  request_type: "container_restart",
  requester: "auto-pipeline",
  summary: "Restart web-api container",
  details: { container: "web-api", mode: "diagnostics_only", read_only: true },
  status: "pending",
  created_at: "2026-09-11T10:00:00Z",
  reviewed_by: null,
  reviewed_at: null,
  comment: null,
};

const approvedApproval = {
  approval_id: "apr-approved-1",
  request_type: "container_restart",
  requester: "auto-pipeline",
  summary: "Restart db container",
  details: { container: "db", mode: "diagnostics_only", read_only: true },
  status: "approved",
  created_at: "2026-09-11T09:00:00Z",
  reviewed_by: "admin@example.com",
  reviewed_at: "2026-09-11T09:15:00Z",
  comment: "Explained to owner",
};

const rejectedApproval = {
  approval_id: "apr-rejected-1",
  request_type: "container_restart",
  requester: "auto-pipeline",
  summary: "Stop backup container",
  details: { container: "backups", mode: "diagnostics_only", read_only: true },
  status: "rejected",
  created_at: "2026-09-11T08:00:00Z",
  reviewed_by: "admin@example.com",
  reviewed_at: "2026-09-11T08:30:00Z",
  comment: "Not enough context",
};

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("Approvals page decision controls", () => {
  let approvals: ApprovalRequest[];

  beforeEach(() => {
    approvals = [{ ...pendingApproval }, { ...approvedApproval }, { ...rejectedApproval }];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init: RequestInit | undefined) => {
        const url = String(input);
        if (url.includes("/respond")) {
          const body = JSON.parse(String(init?.body ?? "{}"));
          approvals = approvals.map((approval) =>
            approval.approval_id === "apr-pending-1"
              ? {
                  ...approval,
                  status: body.decision,
                  reviewed_by: "admin@example.com",
                  reviewed_at: "2026-09-11T11:00:00Z",
                }
              : approval,
          );
          return jsonResponse(approvals.find((approval) => approval.approval_id === "apr-pending-1"));
        }
        if (url.includes("/api/approvals")) {
          return jsonResponse({ approvals, count: approvals.length });
        }
        return jsonResponse({});
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows enabled Approve/Reject only for pending requests and hides them for finalized requests", async () => {
    render(<ApprovalsPage />);

    expect(await screen.findByText("Restart web-api container")).toBeInTheDocument();
    expect(screen.getByText("Restart db container")).toBeInTheDocument();
    expect(screen.getByText("Stop backup container")).toBeInTheDocument();

    const approveButtons = screen.getAllByRole("button", { name: /Approve/i });
    const rejectButtons = screen.getAllByRole("button", { name: /Reject/i });
    expect(approveButtons).toHaveLength(1);
    expect(rejectButtons).toHaveLength(1);
    expect(approveButtons[0]).toBeEnabled();
    expect(rejectButtons[0]).toBeEnabled();

    expect(screen.getAllByText(/Decision:/)).toHaveLength(2);
    expect(screen.getAllByText("admin@example.com").length).toBeGreaterThanOrEqual(2);
  });

  it("approves a pending request from the UI and re-renders it as decided", async () => {
    render(<ApprovalsPage />);

    const approveButton = (await screen.findAllByRole("button", { name: /Approve/i }))[0];
    fireEvent.click(approveButton);

    await waitFor(() => {
      const fetchMock = vi.mocked(fetch);
      const respondCall = fetchMock.mock.calls.find(([, init]) => String(init?.method ?? "").toUpperCase() === "POST");
      expect(respondCall).toBeTruthy();
      const requestUrl = String(respondCall?.[0]);
      expect(requestUrl).toContain("/api/approvals/apr-pending-1/respond");
      const body = JSON.parse(String((respondCall?.[1] as RequestInit | undefined)?.body ?? "{}"));
      expect(body.decision).toBe("approved");
    });

    await waitFor(() => {
      expect(screen.queryAllByRole("button", { name: /Approve/i })).toHaveLength(0);
      expect(screen.queryAllByRole("button", { name: /Reject/i })).toHaveLength(0);
    });
    expect((await screen.findAllByText(/Decision:/)).length).toBeGreaterThanOrEqual(1);
  });

  it("rejects a pending request from the UI", async () => {
    render(<ApprovalsPage />);

    const rejectButton = (await screen.findAllByRole("button", { name: /Reject/i }))[0];
    fireEvent.click(rejectButton);

    await waitFor(() => {
      const fetchMock = vi.mocked(fetch);
      const respondCall = fetchMock.mock.calls.find(([, init]) => String(init?.method ?? "").toUpperCase() === "POST");
      const body = JSON.parse(String((respondCall?.[1] as RequestInit | undefined)?.body ?? "{}"));
      expect(body.decision).toBe("rejected");
    });

    await waitFor(() => {
      expect(screen.queryAllByRole("button", { name: /Reject/i })).toHaveLength(0);
    });
  });
});