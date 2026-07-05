"use client";

import { useEffect, useState } from "react";
import { X, History, Activity, Clock, AlertTriangle, CheckCircle2, RefreshCw, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  getContainerLogs, getIncidentDetail, getMonitoringTargetHistory,
  type ContainerRow, type IncidentRow, type IncidentDetailResponse, type IncidentTransitionRow,
  type MonitoringTarget, type CheckHistoryRow,
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

  useEffect(() => {
    if (open && incidentId) {
      setLoading(true);
      getIncidentDetail(incidentId).then(setDetail).catch(() => toast.error("Failed to load incident details")).finally(() => setLoading(false));
    }
  }, [open, incidentId]);

  const inc = detail?.incident;
  const displayId = inc?.incident_id?.startsWith("INC-") ? inc.incident_id : `INC-${String(inc?.incident_id ?? "").padStart(3, "0")}`;

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
