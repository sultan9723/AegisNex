"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Clock, FileText, RefreshCw, ShieldAlert } from "lucide-react";
import {
  getApprovals,
  getIncidents,
  type ApprovalRequest,
  type IncidentRow,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, EmptyStateError } from "@/components/common/EmptyState";

type EvidencePacket = {
  incident: IncidentRow;
  packet: Record<string, unknown>;
  execution: Record<string, unknown>;
  collectedAt: string;
};

function formatDate(value?: string | null) {
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
      return {};
    }
  }
  return details;
}

function extractEvidencePackets(incidents: IncidentRow[]): EvidencePacket[] {
  const packets: EvidencePacket[] = [];
  incidents.forEach((incident) => {
    const history = incident.remediation_history;
    if (!Array.isArray(history)) return;
    history.forEach((entry) => {
      const details = entry.details;
      if (!details || typeof details !== "object" || Array.isArray(details)) return;
      const record = details as Record<string, unknown>;
      const packet = record.evidence_packet;
      if (!packet || typeof packet !== "object" || Array.isArray(packet)) return;
      packets.push({
        incident,
        packet: packet as Record<string, unknown>,
        execution: record,
        collectedAt: String(entry.executed_at || record.executed_at || incident.timestamp),
      });
    });
  });
  return packets.sort((a, b) => b.collectedAt.localeCompare(a.collectedAt));
}

function downloadEvidencePacket(incidentId: string, packet: EvidencePacket) {
  const blob = new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${incidentId}-unassigned-evidence.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function StatTile({ label, value, icon: Icon }: { label: string; value: number | string; icon: React.ElementType }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-2xl font-bold text-text-primary">{value}</p>
          <p className="mt-1 text-xs text-text-tertiary">{label}</p>
        </div>
        <div className="grid size-9 place-items-center rounded-lg bg-muted">
          <Icon className="size-4 text-text-secondary" />
        </div>
      </div>
    </div>
  );
}

export default function UnassignedEvidencePage() {
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [incidentResult, approvalResult] = await Promise.all([
        getIncidents(1000),
        getApprovals({ limit: 100 }),
      ]);
      const unassigned = (incidentResult.incidents ?? []).filter((incident) => !incident.org_id);
      const incidentIds = new Set(unassigned.map((incident) => incident.incident_id));
      const matchingApprovals = (approvalResult.approvals ?? []).filter((approval) => {
        const details = parseDetails(approval.details);
        return incidentIds.has(String(details.incident_id || ""));
      });
      setIncidents(unassigned);
      setApprovals(matchingApprovals);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load unassigned evidence");
      setIncidents([]);
      setApprovals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const evidencePackets = useMemo(() => extractEvidencePackets(incidents), [incidents]);
  const activeIncidents = incidents.filter((incident) => {
    const status = incident.incident_status ?? incident.status;
    return status === "active" || status === "acknowledged";
  });
  const pendingApprovals = approvals.filter((approval) => approval.status === "pending");

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-64" />
        <div className="grid gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map((item) => <div key={item} className="skeleton h-24 rounded-xl" />)}
        </div>
        <div className="skeleton h-64 rounded-xl" />
      </div>
    );
  }

  if (error) return <EmptyStateError message={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Button variant="ghost" size="sm" asChild className="-ml-2 mb-3">
            <Link href="/clients"><ArrowLeft />Clients</Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning-subtle" size="sm">unassigned</Badge>
            <Badge variant="secondary" size="sm">real incidents only</Badge>
          </div>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-text-primary">Unassigned Evidence</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            Incidents, approvals, and diagnostic evidence that exist before you attach a real client organization.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Active incidents" value={activeIncidents.length} icon={ShieldAlert} />
        <StatTile label="Total incidents" value={incidents.length} icon={ShieldAlert} />
        <StatTile label="Pending approvals" value={pendingApprovals.length} icon={Clock} />
        <StatTile label="Evidence packets" value={evidencePackets.length} icon={FileText} />
      </div>

      <section className="rounded-xl border border-border bg-surface p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Evidence Packets</h2>
            <p className="mt-0.5 text-xs text-text-tertiary">Collected diagnostics that have not yet been attached to a client.</p>
          </div>
          <Badge variant="secondary" size="sm">{evidencePackets.length}</Badge>
        </div>
        {evidencePackets.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No unassigned evidence yet"
            description="Run the approved diagnostics workflow on an unassigned incident and the evidence packet will appear here."
          />
        ) : (
          <div className="space-y-3">
            {evidencePackets.map((item, index) => (
              <article key={`${item.incident.incident_id}-${index}`} className="rounded-lg border border-border bg-background p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="success-subtle" size="sm">collected</Badge>
                      <span className="font-mono text-[10px] text-text-tertiary">{item.incident.incident_id}</span>
                      <span className="text-[11px] text-text-tertiary">{formatDate(item.collectedAt)}</span>
                    </div>
                    <h3 className="mt-2 text-sm font-semibold text-text-primary">
                      {String(item.packet.title || `Diagnostic evidence for ${item.incident.service_name}`)}
                    </h3>
                    <p className="mt-1 text-xs leading-relaxed text-text-secondary">
                      {String(item.packet.summary || item.incident.description || "Read-only diagnostic evidence collected.")}
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => downloadEvidencePacket(item.incident.incident_id, item)}>
                    Export JSON
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text-primary">Unassigned Incidents</h2>
            <Badge variant="secondary" size="sm">{incidents.length}</Badge>
          </div>
          {incidents.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-tertiary">No unassigned incidents.</p>
          ) : (
            <div className="divide-y divide-border/50">
              {incidents.slice(0, 20).map((incident) => (
                <div key={incident.incident_id} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-text-primary">{incident.service_name}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-text-secondary">{incident.description}</p>
                    </div>
                    <Badge variant={(incident.incident_status ?? incident.status) === "resolved" ? "success-subtle" : "warning-subtle"} size="sm">
                      {incident.incident_status ?? incident.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-surface p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text-primary">Unassigned Approvals</h2>
            <Badge variant="secondary" size="sm">{approvals.length}</Badge>
          </div>
          {approvals.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-tertiary">No approval requests tied to unassigned incidents.</p>
          ) : (
            <div className="space-y-3">
              {approvals.slice(0, 20).map((approval) => (
                <div key={approval.approval_id} className="rounded-lg border border-border bg-background p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={approval.status === "approved" ? "success-subtle" : approval.status === "rejected" ? "danger-subtle" : "warning-subtle"} size="sm">
                      {approval.status}
                    </Badge>
                    <span className="font-mono text-[10px] text-text-tertiary">{approval.approval_id}</span>
                  </div>
                  <p className="mt-2 text-sm font-medium text-text-primary">{approval.summary || "Approval request"}</p>
                  <p className="mt-1 text-xs text-text-tertiary">{formatDate(approval.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
