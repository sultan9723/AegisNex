"use client";

import { useEffect, useState } from "react";
import { X, History, Activity, Clock, AlertTriangle, CheckCircle2, RefreshCw, Loader2, Sparkles, Shield, ThumbsUp, ThumbsDown, Play, Download, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  getContainerLogs, getIncidentDetail, getMonitoringTargetHistory, explainIncident,
  proposeIncidentRemediation, approveIncidentRemediation, rejectIncidentRemediation, executeIncidentRemediation,
  assignIncidentClient, getClientOrganizations,
  type ContainerRow, type IncidentRow, type IncidentDetailResponse, type IncidentTransitionRow,
  type MonitoringTarget, type CheckHistoryRow, type IncidentExplanation, type ClientOrganization,
} from "@/lib/api";
import { toast } from "sonner";

function formatTs(ts: string): string {
  try {
    const d = new Date(ts.replace("Z", "+00:00"));
    return d.toLocaleString();
  } catch { return ts; }
}

const relative = (ts: string): string => {
  const diff = Date.now() - new Date(ts.replace("Z", "+00:00")).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

function latestEvidencePacket(incident: IncidentRow | undefined): Record<string, unknown> | null {
  const history = incident?.remediation_history;
  if (!Array.isArray(history)) return null;
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = history[index];
    const details = entry?.details;
    if (details && typeof details === "object" && !Array.isArray(details)) {
      const packet = (details as Record<string, unknown>).evidence_packet;
      if (packet && typeof packet === "object" && !Array.isArray(packet)) {
        return {
          ...(packet as Record<string, unknown>),
          execution: details,
        };
      }
    }
  }
  return null;
}

function downloadEvidencePacket(incidentId: string, packet: Record<string, unknown>) {
  const blob = new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${incidentId}-diagnostic-evidence.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ContainerDrawer({ container, open, onClose }: { container: ContainerRow; open: boolean; onClose: () => void }) {
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  useEffect(() => {
    if (open && container.name) {
      setLogsLoading(true);
      getContainerLogs(container.name, 50).then((res) => {
        if (res.status === "ok") setLogs(res.logs);
      }).catch(() => {}).finally(() => setLogsLoading(false));
    }
  }, [open, container.name]);

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{container.name}</SheetTitle>
          <SheetDescription>Container details and logs</SheetDescription>
        </SheetHeader>
        <div className="space-y-6">
          <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-text-secondary">Status</span>
              <StatusBadge status={container.status === "running" ? "healthy" : "stopped"} label={container.status} pulse={container.status === "running"} />
            </div>
            {container.image && <InfoRow label="Image" value={container.image} />}
            {container.started_at && <InfoRow label="Started" value={formatTs(container.started_at)} />}
            {typeof container.cpu_percent === "number" && <InfoRow label="CPU" value={`${container.cpu_percent.toFixed(1)}%`} />}
            {typeof container.memory_percent === "number" && <InfoRow label="Memory" value={`${container.memory_percent.toFixed(1)}%`} />}
            <InfoRow label="Restarts" value={String(container.restart_count ?? 0)} />
            {container.ports && container.ports.length > 0 && (
              <div>
                <span className="text-xs font-medium text-text-secondary">Ports</span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {container.ports.map((p, i) => (
                    <Badge key={i} variant="outline" size="sm">{p.container_port}{p.host_port ? `:${p.host_port}` : ""}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <Activity className="size-4 text-text-tertiary" />
              <h3 className="text-sm font-semibold text-text-primary">Recent Logs</h3>
            </div>
            {logsLoading ? (
              <div className="flex items-center justify-center py-8"><Loader2 className="size-5 animate-spin text-text-tertiary" /></div>
            ) : (
              <pre className="max-h-64 overflow-auto rounded-lg bg-surface p-3 text-xs text-text-secondary font-mono leading-relaxed">
                {logs.length === 0 ? <span className="text-text-tertiary">No logs available.</span> : logs.map((line, i) => <div key={i}>{line}</div>)}
              </pre>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function IncidentDetailDrawer({ incidentId, open, onClose }: { incidentId: string; open: boolean; onClose: () => void }) {
  const [detail, setDetail] = useState<IncidentDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [explanation, setExplanation] = useState<IncidentExplanation | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [evidencePacket, setEvidencePacket] = useState<Record<string, unknown> | null>(null);
  const [clients, setClients] = useState<ClientOrganization[]>([]);
  const [clientSaving, setClientSaving] = useState(false);

  useEffect(() => {
    if (open && incidentId) {
      setLoading(true);
      setExplanation(null);
      setEvidencePacket(null);
      getIncidentDetail(incidentId).then(setDetail).catch(() => toast.error("Failed to load incident details")).finally(() => setLoading(false));
      getClientOrganizations().then((result) => setClients(result.organizations ?? [])).catch(() => setClients([]));
    }
  }, [open, incidentId]);

  const handleExplain = async () => {
    if (!incidentId) return;
    setExplaining(true);
    try {
      const result = await explainIncident(incidentId);
      setExplanation(result);
    } catch {
      toast.error("Failed to generate AI analysis");
    } finally {
      setExplaining(false);
    }
  };

  const handleProposeDiagnostics = async () => {
    if (!inc) return;
    setActionLoading(true);
    try {
      const plan = {
        mode: "diagnostics_only",
        read_only: true,
        service: inc.service_name,
        incident_id: inc.incident_id,
        incident_type: inc.incident_type,
        actions: [
          {
            action: "collect_incident_context",
            target: inc.service_name,
            read_only: true,
            destructive: false,
            reason: "Collect the current incident description, severity, status, and service context.",
          },
          {
            action: "review_health_check_results",
            target: inc.service_name,
            read_only: true,
            destructive: false,
            reason: "Review health check output already attached to this incident.",
          },
          {
            action: "review_incident_timeline",
            target: inc.incident_id,
            read_only: true,
            destructive: false,
            reason: "Review incident status transitions and operator decisions.",
          },
          {
            action: "prepare_evidence_packet",
            target: inc.incident_id,
            read_only: true,
            destructive: false,
            reason: "Prepare an evidence packet for operator review and audit.",
          },
        ],
      };
      await proposeIncidentRemediation(inc.incident_id, plan, "operator", 0.72);
      toast.success("Diagnostic plan sent for approval");
      const updated = await getIncidentDetail(incidentId);
      setDetail(updated);
    } catch {
      toast.error("Failed to propose diagnostic plan");
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveRemediation = async () => {
    if (!incidentId) return;
    setActionLoading(true);
    try {
      await approveIncidentRemediation(incidentId);
      toast.success("Remediation approved");
      const updated = await getIncidentDetail(incidentId);
      setDetail(updated);
    } catch {
      toast.error("Failed to approve remediation");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectRemediation = async () => {
    if (!incidentId) return;
    setActionLoading(true);
    try {
      await rejectIncidentRemediation(incidentId, "user", "Rejected by operator");
      toast.success("Remediation rejected");
      const updated = await getIncidentDetail(incidentId);
      setDetail(updated);
    } catch {
      toast.error("Failed to reject remediation");
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecuteRemediation = async () => {
    if (!incidentId) return;
    setActionLoading(true);
    try {
      const result = await executeIncidentRemediation(incidentId);
      const packet =
        result.execution_result?.evidence_packet &&
        typeof result.execution_result.evidence_packet === "object"
          ? {
              ...(result.execution_result.evidence_packet as Record<string, unknown>),
              execution: result.execution_result,
            }
          : result.execution_result;
      setEvidencePacket(packet);
      toast.success("Evidence packet collected");
      const updated = await getIncidentDetail(incidentId);
      setDetail(updated);
    } catch {
      toast.error("Failed to collect evidence");
    } finally {
      setActionLoading(false);
    }
  };

  const inc = detail?.incident;
  const displayId = inc?.incident_id?.startsWith("INC-") ? inc.incident_id : `INC-${String(inc?.incident_id ?? "").padStart(3, "0")}`;
  const storedEvidencePacket = evidencePacket ?? latestEvidencePacket(inc);

  const handleAssignClient = async (value: string) => {
    if (!inc) return;
    setClientSaving(true);
    try {
      const orgId = value ? Number(value) : null;
      await assignIncidentClient(inc.incident_id, orgId);
      const updated = await getIncidentDetail(inc.incident_id);
      setDetail(updated);
      toast.success(orgId ? "Incident assigned to client" : "Client assignment cleared");
    } catch {
      toast.error("Failed to update incident client");
    } finally {
      setClientSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{inc?.service_name ?? "Incident"}</SheetTitle>
          <SheetDescription>{displayId}</SheetDescription>
        </SheetHeader>
        {loading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="size-6 animate-spin text-text-tertiary" /></div>
        ) : inc ? (
          <div className="space-y-6">
            <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-secondary">Severity</span>
                <Badge variant={inc.severity === "critical" ? "danger-subtle" : inc.severity === "high" ? "warning-subtle" : "info-subtle"}>{inc.severity}</Badge>
              </div>
              <InfoRow label="Status" value={inc.incident_status ?? inc.status} />
              <InfoRow label="Created" value={relative(inc.timestamp)} />
              {inc.resolved_at && <InfoRow label="Resolved" value={relative(inc.resolved_at)} />}
              {inc.acknowledged_by && <InfoRow label="Acknowledged by" value={inc.acknowledged_by} />}
              {inc.resolved_by && <InfoRow label="Resolved by" value={inc.resolved_by} />}
              {inc.resolution_notes && <InfoRow label="Notes" value={inc.resolution_notes} />}
            </div>

            <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Client</h3>
                  <p className="mt-0.5 text-[10px] text-text-tertiary">Assign this incident to a managed organization.</p>
                </div>
                {clientSaving && <Loader2 className="size-4 animate-spin text-text-tertiary" />}
              </div>
              <select
                className="h-9 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text-primary outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
                value={inc.org_id ?? ""}
                onChange={(event) => handleAssignClient(event.target.value)}
                disabled={clientSaving}
              >
                <option value="">Unassigned</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
              {inc.org_name && (
                <p className="mt-2 text-xs text-text-secondary">Current client: {inc.org_name}</p>
              )}
            </div>

            <div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExplain}
                  disabled={explaining || actionLoading}
                  className="w-full"
                >
                  {explaining ? (
                    <Loader2 className="size-4 animate-spin mr-2" />
                  ) : (
                    <Sparkles className="size-4 mr-2" />
                  )}
                  {explaining ? "Analyzing..." : "Explain"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleProposeDiagnostics}
                  disabled={actionLoading || Boolean(inc.proposed_remediation)}
                  className="w-full"
                >
                  {actionLoading ? (
                    <Loader2 className="size-4 animate-spin mr-2" />
                  ) : (
                    <Shield className="size-4 mr-2" />
                  )}
                  Propose Diagnostics
                </Button>
              </div>
            </div>

            {inc?.proposed_remediation && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Shield className="size-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-text-primary">Proposed Remediation</h3>
                  <Badge variant="warning-subtle" size="sm">{inc.remediation_approval_status || "pending"}</Badge>
                </div>
                {inc.remediation_proposed_by && (
                  <p className="text-[10px] text-text-tertiary">Proposed by {inc.remediation_proposed_by} {inc.remediation_proposed_at ? `at ${relative(inc.remediation_proposed_at)}` : ""}</p>
                )}
                {typeof inc.remediation_plan_confidence === "number" && (
                  <p className="text-[10px] text-text-tertiary">Confidence: {(inc.remediation_plan_confidence * 100).toFixed(0)}%</p>
                )}
                <div className="rounded-lg border border-border/40 bg-surface/50 p-3">
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    <Badge variant="secondary" size="sm">{String(inc.proposed_remediation.mode || "plan")}</Badge>
                    {inc.proposed_remediation.read_only === true && <Badge variant="success-subtle" size="sm">read only</Badge>}
                  </div>
                  {Array.isArray(inc.proposed_remediation.actions) ? (
                    <div className="space-y-2">
                      {inc.proposed_remediation.actions.map((action: Record<string, unknown>, index: number) => (
                        <div key={index} className="rounded border border-border/30 bg-background/60 p-2">
                          <p className="text-xs font-medium text-text-primary">{String(action.action || "Diagnostic step")}</p>
                          {typeof action.reason === "string" && (
                            <p className="mt-0.5 text-[10px] leading-relaxed text-text-tertiary">{action.reason}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <pre className="whitespace-pre-wrap font-mono text-[10px] text-text-secondary">
                      {JSON.stringify(inc.proposed_remediation, null, 2)}
                    </pre>
                  )}
                </div>
                {inc.remediation_approval_status === "pending" && (
                  <div className="flex gap-2 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleApproveRemediation}
                      disabled={actionLoading}
                      className="flex-1"
                    >
                      {actionLoading ? <Loader2 className="size-3 animate-spin mr-1" /> : <ThumbsUp className="size-3 mr-1" />}
                      Approve
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRejectRemediation}
                      disabled={actionLoading}
                      className="flex-1"
                    >
                      {actionLoading ? <Loader2 className="size-3 animate-spin mr-1" /> : <ThumbsDown className="size-3 mr-1" />}
                      Reject
                    </Button>
                  </div>
                )}
                {inc.remediation_approval_status === "approved" && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleExecuteRemediation}
                    disabled={actionLoading}
                    className="w-full"
                  >
                    {actionLoading ? <Loader2 className="size-3 animate-spin mr-1" /> : <Play className="size-3 mr-1" />}
                    Collect Evidence
                  </Button>
                )}
              </div>
            )}

            {storedEvidencePacket && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <FileText className="size-4 text-emerald-500" />
                    <h3 className="text-sm font-semibold text-text-primary">Evidence Packet</h3>
                    <Badge variant="success-subtle" size="sm">collected</Badge>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => inc && downloadEvidencePacket(inc.incident_id, storedEvidencePacket)}
                  >
                    <Download className="size-3.5" />
                    Export
                  </Button>
                </div>
                <p className="text-xs leading-relaxed text-text-secondary">
                  {String(storedEvidencePacket.summary || "Read-only diagnostic evidence is available for this incident.")}
                </p>
                <div className="grid gap-2 text-xs sm:grid-cols-2">
                  <InfoRow label="Infrastructure changed" value={storedEvidencePacket.infrastructure_mutated === false ? "No" : "Unknown"} />
                  <InfoRow label="Approval required" value={storedEvidencePacket.approval_required === true ? "Yes" : "Unknown"} />
                  <InfoRow label="Artifact" value={String(storedEvidencePacket.artifact_type || "diagnostic_evidence")} />
                  <InfoRow label="Source" value={String(storedEvidencePacket.source || "incident_record")} />
                </div>
                <pre className="max-h-48 overflow-auto rounded-lg bg-surface/70 p-3 font-mono text-[10px] leading-relaxed text-text-secondary">
                  {JSON.stringify(storedEvidencePacket.execution || storedEvidencePacket, null, 2)}
                </pre>
              </div>
            )}

            {explanation && (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-primary" />
                  <h3 className="text-sm font-semibold text-text-primary">AI Analysis</h3>
                  <Badge variant="secondary" size="sm">{(explanation.confidence * 100).toFixed(0)}% confidence</Badge>
                </div>
                <div className="text-xs text-text-secondary whitespace-pre-wrap leading-relaxed">
                  {explanation.analysis}
                </div>
                {explanation.similar_incidents.length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-text-secondary mb-1">Similar Past Incidents</h4>
                    {explanation.similar_incidents.slice(0, 3).map((sim, i) => (
                      <div key={i} className="text-[10px] text-text-tertiary mt-1 pl-2 border-l border-border/30">
                        {sim.content}
                      </div>
                    ))}
                  </div>
                )}
                {explanation.runbooks.length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-text-secondary mb-1">Relevant Runbooks</h4>
                    {explanation.runbooks.map((rb, i) => (
                      <div key={i} className="text-[10px] text-text-tertiary mt-1">
                        {rb.title || rb.source}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <div className="flex items-center gap-2 mb-2">
                <History className="size-4 text-text-tertiary" />
                <h3 className="text-sm font-semibold text-text-primary">Timeline</h3>
                <Badge variant="secondary" size="sm">{detail.timeline.length}</Badge>
              </div>
              {detail.timeline.length === 0 ? (
                <p className="text-xs text-text-tertiary py-4 text-center">No timeline events.</p>
              ) : (
                <div className="space-y-2">
                  {detail.timeline.map((entry: IncidentTransitionRow) => (
                    <div key={entry.id} className="flex items-start gap-3 rounded-lg border border-border/30 bg-surface-elevated/30 p-3">
                      <div className="mt-0.5 size-2 shrink-0 rounded-full bg-primary" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 text-xs flex-wrap">
                          <span className="font-medium text-text-primary">{entry.actor}</span>
                          <span className="text-text-tertiary">→</span>
                          {entry.from_status && <Badge variant="secondary" size="sm">{entry.from_status}</Badge>}
                          <span className="text-text-tertiary">→</span>
                          <Badge variant={entry.to_status === "resolved" ? "success-subtle" : "warning-subtle"} size="sm">{entry.to_status}</Badge>
                        </div>
                        <p className="mt-0.5 text-[10px] text-text-tertiary">{relative(entry.timestamp)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {inc?.remediation_history && inc.remediation_history.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="size-4 text-text-tertiary" />
                  <h3 className="text-sm font-semibold text-text-primary">Remediation History</h3>
                  <Badge variant="secondary" size="sm">{inc.remediation_history.length}</Badge>
                </div>
                <div className="space-y-2">
                  {inc.remediation_history.map((entry: Record<string, unknown>, i: number) => {
                    const proposedBy = typeof entry.proposed_by === "string" ? entry.proposed_by : null;
                    const executedAt = typeof entry.executed_at === "string" ? entry.executed_at : null;
                    const rejectionReason = typeof entry.rejection_reason === "string" ? entry.rejection_reason : null;
                    return (
                      <div key={i} className="rounded-lg border border-border/30 bg-surface-elevated/30 p-3">
                        <div className="flex items-center gap-2 text-xs flex-wrap">
                          <Badge variant={entry.outcome === "executed" && entry.successful ? "success-subtle" : entry.outcome === "rejected" || entry.outcome === "superseded" ? "secondary" : "warning-subtle"} size="sm">
                            {String(entry.approval_status || entry.outcome || "unknown")}
                          </Badge>
                          {proposedBy && <span className="text-text-tertiary">by {proposedBy}</span>}
                          {executedAt && <span className="text-text-tertiary">at {relative(executedAt)}</span>}
                        </div>
                        {rejectionReason && (
                          <p className="mt-1 text-[10px] text-text-tertiary">Reason: {rejectionReason}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-text-tertiary text-center py-8">No details available.</p>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function TargetHistoryDrawer({ target, open, onClose }: { target: MonitoringTarget; open: boolean; onClose: () => void }) {
  const [history, setHistory] = useState<CheckHistoryRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && target.id) {
      setLoading(true);
      getMonitoringTargetHistory(target.id).then((res) => setHistory(res.history)).catch(() => {}).finally(() => setLoading(false));
    }
  }, [open, target.id]);

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{target.name}</SheetTitle>
          <SheetDescription>Check history for {target.target_type.toUpperCase()} target</SheetDescription>
        </SheetHeader>
        <div className="space-y-6">
          <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4 space-y-3">
            <InfoRow label="Type" value={target.target_type.toUpperCase()} />
            <InfoRow label="Address" value={target.address} />
            <InfoRow label="Interval" value={`${target.timeout_seconds}s`} />
            {target.last_response_time_ms != null && <InfoRow label="Last Response" value={`${target.last_response_time_ms}ms`} />}
            {target.last_error && (
              <div className="flex items-start gap-2">
                <AlertTriangle className="size-3.5 text-danger mt-0.5 shrink-0" />
                <span className="text-xs text-danger">{target.last_error}</span>
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <Clock className="size-4 text-text-tertiary" />
              <h3 className="text-sm font-semibold text-text-primary">Check History</h3>
              <Badge variant="secondary" size="sm">{history.length}</Badge>
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-8"><Loader2 className="size-5 animate-spin text-text-tertiary" /></div>
            ) : history.length === 0 ? (
              <p className="text-xs text-text-tertiary py-4 text-center">No check history yet.</p>
            ) : (
              <div className="space-y-1.5">
                {history.slice(0, 20).map((h) => (
                  <div key={h.id} className="flex items-center justify-between rounded-lg border border-border/30 bg-surface-elevated/30 px-3 py-2">
                    <div className="flex items-center gap-2">
                      {h.status === "healthy" || h.status === "reachable" || h.status === "valid" ? (
                        <CheckCircle2 className="size-3 text-success" />
                      ) : (
                        <AlertTriangle className="size-3 text-danger" />
                      )}
                      <span className="text-xs text-text-primary">{h.target_name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {h.latency_ms != null && <span className="text-[10px] text-text-tertiary">{h.latency_ms}ms</span>}
                      <span className="text-[10px] text-text-tertiary">{relative(h.timestamp)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-text-secondary">{label}</span>
      <span className="text-xs font-medium text-text-primary">{value}</span>
    </div>
  );
}
