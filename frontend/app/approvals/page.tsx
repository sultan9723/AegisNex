"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { getApprovals, respondQueuedApproval, type ApprovalRequest } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, EmptyStateError } from "@/components/common/EmptyState";

function formatDate(value: string) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString();
}

function parseDetails(details: ApprovalRequest["details"]) {
  if (!details) return {};
  if (typeof details === "string") {
    try {
      return JSON.parse(details) as Record<string, unknown>;
    } catch {
      return { details };
    }
  }
  return details;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "approved") return <Badge variant="success-subtle">approved</Badge>;
  if (status === "rejected") return <Badge variant="danger-subtle">rejected</Badge>;
  return <Badge variant="warning-subtle">pending</Badge>;
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getApprovals({ limit: 50 });
      setApprovals(response.approvals ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals");
      setApprovals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  const counts = useMemo(() => {
    return approvals.reduce(
      (acc, approval) => {
        const status = approval.status || "pending";
        if (status === "approved") acc.approved += 1;
        else if (status === "rejected") acc.rejected += 1;
        else acc.pending += 1;
        return acc;
      },
      { pending: 0, approved: 0, rejected: 0 },
    );
  }, [approvals]);

  const handleDecision = async (approvalId: string, decision: "approved" | "rejected") => {
    setSavingId(approvalId);
    setNotice("");
    setError("");
    try {
      await respondQueuedApproval(approvalId, decision);
      setNotice(decision === "approved" ? "Approval accepted" : "Approval rejected");
      await loadApprovals();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update approval");
    } finally {
      setSavingId("");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Badge variant="warning-subtle" size="sm">human gate</Badge>
            <Badge variant="secondary" size="sm">real queue</Badge>
          </div>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-text-primary">Approvals</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            Review AI or remediation actions that require human approval before execution. Empty means no current
            backend approval requests exist.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadApprovals} disabled={loading}>
          <RefreshCw className={loading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-bold text-text-primary">{counts.pending}</p>
          <p className="mt-1 text-xs text-text-tertiary">Pending review</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-bold text-text-primary">{counts.approved}</p>
          <p className="mt-1 text-xs text-text-tertiary">Approved</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-bold text-text-primary">{counts.rejected}</p>
          <p className="mt-1 text-xs text-text-tertiary">Rejected</p>
        </div>
      </div>

      {(error || notice) && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${error ? "border-danger-border bg-danger-bg text-danger-subtle" : "border-success-border bg-success-bg text-success-subtle"}`}>
          {error || notice}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="rounded-xl border border-border bg-surface p-5">
              <div className="skeleton h-4 w-64" />
              <div className="skeleton mt-4 h-3 w-96" />
              <div className="skeleton mt-6 h-8 w-48" />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyStateError message={error} onRetry={loadApprovals} />
      ) : approvals.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="No approval requests"
          description="AI actions, remediation plans, or runbooks that need human review will appear here once the backend creates approval requests."
        />
      ) : (
        <div className="space-y-3">
          {approvals.map((approval) => {
            const details = parseDetails(approval.details);
            const pending = approval.status === "pending";
            return (
              <section key={approval.approval_id} className="rounded-xl border border-border bg-surface p-5">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={approval.status} />
                      <span className="font-mono text-[10px] text-text-tertiary">{approval.approval_id}</span>
                      <span className="text-[11px] text-text-tertiary">{formatDate(approval.created_at)}</span>
                    </div>
                    <h2 className="mt-3 text-base font-semibold text-text-primary">{approval.summary || "Approval request"}</h2>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-tertiary">
                      <span>Requester: <span className="text-text-secondary">{approval.requester || "unknown"}</span></span>
                      <span>Type: <span className="text-text-secondary">{approval.request_type || "action"}</span></span>
                      {approval.reviewed_by && <span>Reviewed by: <span className="text-text-secondary">{approval.reviewed_by}</span></span>}
                    </div>
                    {Object.keys(details).length > 0 && (
                      <div className="mt-4 rounded-lg border border-border bg-background p-3">
                        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Request details</p>
                        <dl className="grid gap-2 text-xs sm:grid-cols-2">
                          {Object.entries(details).slice(0, 8).map(([key, value]) => (
                            <div key={key}>
                              <dt className="text-text-tertiary">{key.replace(/_/g, " ")}</dt>
                              <dd className="mt-0.5 break-words font-medium text-text-secondary">
                                {typeof value === "object" ? JSON.stringify(value) : String(value)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="success"
                      size="sm"
                      disabled={!pending || savingId === approval.approval_id}
                      onClick={() => handleDecision(approval.approval_id, "approved")}
                    >
                      <CheckCircle2 />
                      Approve
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={!pending || savingId === approval.approval_id}
                      onClick={() => handleDecision(approval.approval_id, "rejected")}
                    >
                      <XCircle />
                      Reject
                    </Button>
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      )}

      <div className="rounded-xl border border-border bg-surface p-5">
        <div className="flex gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-warning-bg">
            <ShieldAlert className="size-4 text-warning-subtle" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">What this page proves</h2>
            <p className="mt-1 text-sm text-text-secondary">
              This is the operator control point for the MSP workflow: AI can investigate, but risky actions must wait
              here for a real human decision before execution.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
