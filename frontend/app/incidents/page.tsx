"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldAlert, AlertTriangle, CheckCircle2, Clock, Activity, Eye, ThumbsUp, CheckCircle, RotateCcw, Trash2, X, Loader2, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getIncidents, getIncidentDetail, acknowledgeIncident, resolveIncident, reopenIncident, deleteIncident, type IncidentRow, type IncidentsResponse, type IncidentDetailResponse, type IncidentTransitionRow } from "@/lib/api";
import { useWebSocket } from "@/lib/ws";
import { toast } from "sonner";
import { publish } from "@/lib/workflow";
import { IncidentDetailDrawer } from "@/components/layout/ActionDrawer";
import { SkeletonList } from "@/components/common/Skeleton";

function formatTimestamp(ts: string): string {
  const diff = Date.now() - new Date(ts.replace("Z", "+00:00")).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function getSeverityVariant(severity: string): "danger-subtle" | "warning-subtle" | "info-subtle" {
  if (severity === "critical") return "danger-subtle";
  if (severity === "high" || severity === "warning") return "warning-subtle";
  return "info-subtle";
}

export default function IncidentsPage() {
  const [data, setData] = useState<IncidentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [resolveDialog, setResolveDialog] = useState<IncidentRow | null>(null);
  const [resolveNotes, setResolveNotes] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<IncidentRow | null>(null);

  const load = useCallback(() => {
    getIncidents(50).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  useWebSocket("/ws/incidents", (msg: unknown) => {
    const event = msg as { type?: string; payload?: unknown };
    if (event.type === "incident_list" && event.payload) {
      const pl = event.payload as { incidents?: IncidentRow[] };
      if (pl.incidents) {
        setData((prev) => {
          const incidents = pl.incidents ?? prev?.incidents ?? [];
          const active = incidents.filter((i) => (i.incident_status ?? i.status) === "active" || (i.incident_status ?? i.status) === "acknowledged");
          const resolved = incidents.filter((i) => (i.incident_status ?? i.status) === "resolved");
          return prev ? { ...prev, incidents, active_count: active.length, resolved_count: resolved.length } : { incidents, active_count: active.length, resolved_count: resolved.length, active_incidents: active, resolved_incidents: resolved, recent_incidents: incidents.slice(0, 6), count: incidents.length };
        });
        setLoading(false);
      }
    } else if (event.type === "incident_created" && event.payload) {
      const incident = event.payload as IncidentRow;
      setData((prev) => {
        if (!prev) return prev;
        if (prev.incidents.some((i) => i.incident_id === incident.incident_id)) return prev;
        const newIncidents = [incident, ...prev.incidents].slice(0, 50);
        return { ...prev, incidents: newIncidents, recent_incidents: newIncidents.slice(0, 6), active_incidents: [incident, ...prev.active_incidents], active_count: prev.active_count + 1, count: prev.count + 1 };
      });
    } else if (event.type === "incident_resolved" && event.payload) {
      const incident = event.payload as IncidentRow;
      setData((prev) => {
        if (!prev) return prev;
        const updatedIncidents = prev.incidents.map((i) => i.incident_id === incident.incident_id ? { ...i, incident_status: "resolved", status: "resolved", resolved_timestamp: incident.resolved_timestamp, resolved_at: incident.resolved_at } : i);
        return {
          ...prev, incidents: updatedIncidents,
          active_incidents: prev.active_incidents.filter((i) => i.incident_id !== incident.incident_id),
          resolved_incidents: [incident, ...prev.resolved_incidents],
          active_count: Math.max(0, prev.active_count - 1), resolved_count: prev.resolved_count + 1,
        };
      });
    }
  });

  const handleViewDetail = (incident: IncidentRow) => {
    setSelectedIncidentId(incident.incident_id);
    setDetailOpen(true);
  };

  const handleAcknowledge = async (incidentId: string) => {
    setActionLoadingId(`ack-${incidentId}`);
    try {
      await acknowledgeIncident(incidentId);
      toast.success("Incident acknowledged");
      load();
    } catch {
      toast.error("Failed to acknowledge incident");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleResolve = async () => {
    if (!resolveDialog) return;
    const incidentId = resolveDialog.incident_id;
    const notes = resolveNotes;
    setActionLoadingId(`res-${incidentId}`);
    try {
      await resolveIncident(incidentId, notes);
      toast.success("Incident resolved", {
        action: {
          label: "Undo",
          onClick: async () => {
            await reopenIncident(incidentId);
            publish("IncidentReopened", { id: incidentId });
            toast.success("Incident reopened");
            load();
          },
        },
        duration: 10000,
      });
      publish("IncidentResolved", { id: incidentId, notes });
      setResolveDialog(null);
      setResolveNotes("");
      load();
    } catch {
      toast.error("Failed to resolve incident");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReopen = async (incidentId: string) => {
    setActionLoadingId(`reopen-${incidentId}`);
    try {
      await reopenIncident(incidentId);
      toast.success("Incident reopened");
      load();
    } catch {
      toast.error("Failed to reopen incident");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDelete = async (incident: IncidentRow) => {
    setActionLoadingId(`del-${incident.incident_id}`);
    try {
      await deleteIncident(incident.incident_id);
      toast.success("Incident deleted");
      setDeleteConfirm(null);
      load();
    } catch {
      toast.error("Failed to delete incident");
    } finally {
      setActionLoadingId(null);
    }
  };

  const incidents = data?.incidents ?? [];
  const activeCount = data?.active_count ?? incidents.filter((i) => (i.incident_status ?? i.status) === "active" || (i.incident_status ?? i.status) === "acknowledged").length;

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();

  const resolvedToday = incidents.filter((i) => {
    const ts = i.resolved_at ?? i.resolved_timestamp;
    return ts && ts >= todayStart;
  }).length;

  const thisMonthCount = incidents.filter((i) => {
    const ts = i.timestamp;
    return ts >= monthStart;
  }).length;

  const resolvedLast7 = incidents.filter((i) => {
    const ts = i.resolved_at ?? i.resolved_timestamp;
    if (!ts) return false;
    const d = new Date(ts.replace("Z", "+00:00")).getTime();
    return d >= Date.now() - 7 * 86400000;
  });

  let avgResolution = "\u2014";
  if (resolvedLast7.length > 0) {
    const totalMinutes = resolvedLast7.reduce((sum, i) => {
      const start = new Date(i.timestamp.replace("Z", "+00:00")).getTime();
      const end = new Date((i.resolved_at ?? i.resolved_timestamp ?? i.timestamp).replace("Z", "+00:00")).getTime();
      return sum + Math.max(0, (end - start) / 60000);
    }, 0);
    const avg = Math.round(totalMinutes / resolvedLast7.length);
    avgResolution = avg < 60 ? `${avg}m` : `${Math.floor(avg / 60)}h ${avg % 60}m`;
  }

  const displayId = (i: IncidentRow) => i.incident_id?.startsWith("INC-") ? i.incident_id : `INC-${String(i.incident_id).padStart(3, "0")}`;
  const displayStatus = (i: IncidentRow) => i.incident_status ?? i.status;
  const isActive = (i: IncidentRow) => { const s = displayStatus(i); return s === "active" || s === "acknowledged"; };

  return (
    <RouteScaffold title="Incidents" description="Track and manage security incidents, service disruptions, and automated remediation actions." icon={ShieldAlert}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardValue icon={AlertTriangle} label="Active Incidents" value={loading ? "..." : String(activeCount)} detail="Requires attention" color="text-danger" />
        <MetricCardValue icon={CheckCircle2} label="Resolved Today" value={loading ? "..." : String(resolvedToday)} detail="Last 24 hours" color="text-success" />
        <MetricCardValue icon={Clock} label="Avg Resolution" value={loading ? "..." : avgResolution} detail="Last 7 days" />
        <MetricCardValue icon={Activity} label="Total This Month" value={loading ? "..." : String(thisMonthCount)} detail="All incidents" />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Recent Incidents</CardTitle>
              <p className="mt-0.5 text-xs text-text-secondary">Latest security and service incidents</p>
            </div>
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="divide-y divide-border/50">
            {loading && <div className="py-4"><SkeletonList count={6} /></div>}
            {!loading && incidents.length === 0 && <p className="py-6 text-center text-sm text-text-tertiary">No incidents recorded.</p>}
            {incidents.slice(0, 25).map((incident) => (
              <div key={incident.incident_id} className="flex items-start justify-between gap-4 py-3.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-text-primary">{incident.service_name}</p>
                    <Badge variant="secondary" size="sm">{displayId(incident)}</Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-text-secondary">{incident.description}</p>
                  <p className="mt-0.5 text-[11px] text-text-tertiary">{formatTimestamp(incident.timestamp)}</p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <Badge variant={getSeverityVariant(incident.severity)}>{incident.severity}</Badge>
                    <Button variant="ghost" size="icon-sm" onClick={() => handleViewDetail(incident)} title="View details">
                      <Eye className="size-3.5" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge variant={isActive(incident) ? "warning-subtle" : "success-subtle"} dot pulse={isActive(incident)}>{displayStatus(incident)}</Badge>
                    {isActive(incident) && displayStatus(incident) === "active" && (
                      <Button variant="ghost" size="icon-sm" onClick={() => handleAcknowledge(incident.incident_id)} disabled={actionLoadingId === `ack-${incident.incident_id}`} title="Acknowledge">
                        {actionLoadingId === `ack-${incident.incident_id}` ? <Loader2 className="size-3.5 animate-spin" /> : <ThumbsUp className="size-3.5" />}
                      </Button>
                    )}
                    {isActive(incident) && (
                      <Button variant="ghost" size="icon-sm" onClick={() => setResolveDialog(incident)} disabled={actionLoadingId === `res-${incident.incident_id}`} title="Resolve">
                        {actionLoadingId === `res-${incident.incident_id}` ? <Loader2 className="size-3.5 animate-spin" /> : <CheckCircle className="size-3.5 text-success" />}
                      </Button>
                    )}
                    {!isActive(incident) && (
                      <Button variant="ghost" size="icon-sm" onClick={() => handleReopen(incident.incident_id)} disabled={actionLoadingId === `reopen-${incident.incident_id}`} title="Reopen">
                        {actionLoadingId === `reopen-${incident.incident_id}` ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
                      </Button>
                    )}
                    <Button variant="ghost" size="icon-sm" onClick={() => setDeleteConfirm(incident)} disabled={actionLoadingId === `del-${incident.incident_id}`} title="Delete">
                      <Trash2 className="size-3.5 text-danger" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {selectedIncidentId && (
        <IncidentDetailDrawer incidentId={selectedIncidentId} open={detailOpen} onClose={() => { setDetailOpen(false); setSelectedIncidentId(null); }} />
      )}

      <Dialog open={resolveDialog !== null} onOpenChange={(o) => { if (!o) { setResolveDialog(null); setResolveNotes(""); } }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Resolve Incident</DialogTitle>
            <DialogDescription>
              Provide resolution notes for {resolveDialog ? displayId(resolveDialog) : ""}.
            </DialogDescription>
          </DialogHeader>
          <textarea
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary resize-none focus:border-primary/60 focus:outline-none focus:ring-2 focus:ring-primary/15"
            rows={3}
            value={resolveNotes}
            onChange={(e) => setResolveNotes(e.target.value)}
            placeholder="What was the root cause and how was it resolved?"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => { setResolveDialog(null); setResolveNotes(""); }}>Cancel</Button>
            <Button variant="success" onClick={handleResolve}>Resolve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteConfirm(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Incident</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete {deleteConfirm ? displayId(deleteConfirm) : ""}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteConfirm && handleDelete(deleteConfirm)}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </RouteScaffold>
  );
}

function MetricCardValue({ icon: Icon, label, value, detail, color }: { icon: any; label: string; value: string; detail?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-surface-elevated/70 p-4 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-tertiary">{label}</p>
          <p className={`mt-1 text-2xl font-semibold tracking-tight ${color ?? "text-text-primary"}`}>{value}</p>
        </div>
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
          <Icon className="size-4" />
        </div>
      </div>
      {detail && <p className="mt-2 text-xs text-text-secondary">{detail}</p>}
    </div>
  );
}
