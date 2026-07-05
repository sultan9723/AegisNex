"use client";

import { useCallback, useEffect, useState } from "react";
import { ListChecks, Globe, Lock, Activity, Plus, Play, Pencil, Trash2, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getMonitoringTargets, createMonitoringTarget, updateMonitoringTarget, deleteMonitoringTarget, runMonitoringTarget, type MonitoringTarget, type MonitoringTargetPayload } from "@/lib/api";
import { useWebSocket } from "@/lib/ws";
import { useAction } from "@/lib/useAction";
import { toast } from "sonner";
import { publish } from "@/lib/workflow";
import { TargetHistoryDrawer } from "@/components/layout/ActionDrawer";
import { SkeletonList } from "@/components/common/Skeleton";

const DEFAULT_PAYLOAD: MonitoringTargetPayload = {
  name: "", target_type: "http", address: "", expected_status: 200, timeout_seconds: 30, warning_days: 30, is_active: true,
};

function targetStatus(target: MonitoringTarget): { label: string; variant: "success-subtle" | "warning-subtle" | "danger-subtle" } {
  const latest = target.latest_result;
  if (latest && typeof latest === "object" && "status" in latest) {
    const s = String(latest.status);
    if (s === "healthy" || s === "reachable" || s === "valid") return { label: "healthy", variant: "success-subtle" };
    if (s === "warning" || s === "expiring") return { label: "warning", variant: "warning-subtle" };
    return { label: "error", variant: "danger-subtle" };
  }
  if (target.last_error) return { label: "error", variant: "danger-subtle" };
  if (target.last_successful_check_at) return { label: "healthy", variant: "success-subtle" };
  return { label: "pending", variant: "warning-subtle" };
}

export default function TargetsPage() {
  const [data, setData] = useState<{ targets: MonitoringTarget[]; count: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTarget, setEditingTarget] = useState<MonitoringTarget | null>(null);
  const [form, setForm] = useState<MonitoringTargetPayload>(DEFAULT_PAYLOAD);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof MonitoringTargetPayload, string>>>({});
  const [deleteConfirm, setDeleteConfirm] = useState<MonitoringTarget | null>(null);
  const [runningTargets, setRunningTargets] = useState<Set<number>>(new Set());
  const [historyTarget, setHistoryTarget] = useState<MonitoringTarget | null>(null);

  const load = useCallback(() => {
    getMonitoringTargets().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  useWebSocket("/ws/targets", (msg: unknown) => {
    const event = msg as { type?: string; payload?: { targets?: MonitoringTarget[]; count?: number } };
    if (event.type === "target_list" && event.payload) {
      setData({ targets: event.payload.targets ?? [], count: event.payload.count ?? 0 });
      setLoading(false);
    }
  });

  const validate = (): boolean => {
    const errors: Partial<Record<keyof MonitoringTargetPayload, string>> = {};
    if (!form.name.trim()) errors.name = "Name is required";
    if (!form.address.trim()) errors.address = "Address is required";
    if (form.target_type === "http" && (form.expected_status == null || form.expected_status < 100)) errors.expected_status = "Valid HTTP status code required";
    if (form.timeout_seconds < 1 || form.timeout_seconds > 300) errors.timeout_seconds = "Timeout must be 1-300 seconds";
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const openAdd = () => {
    setEditingTarget(null);
    setForm(DEFAULT_PAYLOAD);
    setFormErrors({});
    setDialogOpen(true);
  };

  const openEdit = (target: MonitoringTarget) => {
    setEditingTarget(target);
    setForm({
      name: target.name,
      target_type: target.target_type,
      address: target.address,
      expected_status: target.expected_status,
      timeout_seconds: target.timeout_seconds,
      warning_days: target.warning_days,
      is_active: target.is_active,
    });
    setFormErrors({});
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!validate()) return;
    if (editingTarget) {
      const res = await updateMonitoringTarget(editingTarget.id, form);
      if (res) {
        toast.success("Target updated successfully");
        setDialogOpen(false);
        load();
      }
    } else {
      const res = await createMonitoringTarget(form);
      if (res) {
        toast.success("Target created successfully");
        setDialogOpen(false);
        load();
      }
    }
  };

  const handleDelete = async (target: MonitoringTarget) => {
    const res = await deleteMonitoringTarget(target.id);
    if (res) {
      toast.success("Target deleted", {
        action: {
          label: "Undo",
          onClick: async () => {
            await createMonitoringTarget({ name: target.name, target_type: target.target_type, address: target.address, expected_status: target.expected_status, timeout_seconds: target.timeout_seconds, warning_days: target.warning_days, is_active: target.is_active });
            publish("TargetCreated", { id: target.id });
            toast.success("Target restored");
            load();
          },
        },
        duration: 10000,
      });
      publish("TargetDeleted", { id: target.id });
      setDeleteConfirm(null);
      load();
    }
  };

  const handleRun = async (target: MonitoringTarget) => {
    setRunningTargets((prev) => new Set(prev).add(target.id));
    try {
      const res = await runMonitoringTarget(target.id);
      if (res) toast.success(`Check triggered for ${target.name}`);
    } catch {
      toast.error(`Failed to trigger check for ${target.name}`);
    } finally {
      setRunningTargets((prev) => { const next = new Set(prev); next.delete(target.id); return next; });
    }
  };

  const targets = data?.targets ?? [];
  const httpCount = targets.filter((t) => t.target_type === "http").length;
  const sslCount = targets.filter((t) => t.target_type === "ssl").length;
  const tcpCount = targets.filter((t) => t.target_type === "tcp").length;

  return (
    <RouteScaffold title="Monitoring Targets" description="Configure and monitor HTTP endpoints, TCP ports, and SSL certificates for your infrastructure." icon={ListChecks}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardSmall icon={ListChecks} label="Total Targets" value={loading ? "..." : String(data?.count ?? 0)} detail="Active monitors" />
        <MetricCardSmall icon={Globe} label="HTTP Checks" value={loading ? "..." : String(httpCount)} detail="Endpoints monitored" />
        <MetricCardSmall icon={Lock} label="SSL Certificates" value={loading ? "..." : String(sslCount)} detail="Certificates tracked" />
        <MetricCardSmall icon={Activity} label="TCP Ports" value={loading ? "..." : String(tcpCount)} detail="Ports monitored" />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Target List</CardTitle>
              <p className="mt-0.5 text-xs text-text-secondary">All configured monitoring targets</p>
            </div>
            <Button size="sm" onClick={openAdd}>
              <Plus className="size-3.5 mr-1" />
              Add Target
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="divide-y divide-border/50">
            {loading && <div className="py-4"><SkeletonList count={5} /></div>}
            {!loading && targets.length === 0 && <p className="py-6 text-center text-sm text-text-tertiary">No monitoring targets configured.</p>}
            {targets.map((target) => {
              const st = targetStatus(target);
              const responseTime = target.last_response_time_ms != null ? `${target.last_response_time_ms}ms` : null;
              return (
                <div key={target.id} className="flex items-center justify-between py-3.5">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{target.name}</p>
                    <div className="mt-0.5 flex items-center gap-4 text-xs text-text-tertiary">
                      <Badge variant="secondary" size="sm">{target.target_type.toUpperCase()}</Badge>
                      {responseTime && <span>Response: {responseTime}</span>}
                      {target.target_type === "ssl" && target.warning_days != null && <span>Warning threshold: {target.warning_days} days</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge variant={st.variant} dot pulse={st.label !== "healthy"}>{st.label}</Badge>
                    <Button variant="ghost" size="icon-sm" onClick={() => handleRun(target)} disabled={runningTargets.has(target.id)} title="Run check">
                      {runningTargets.has(target.id) ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                    </Button>
                    <Button variant="ghost" size="icon-sm" onClick={() => setHistoryTarget(target)} title="History">
                      <Activity className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-sm" onClick={() => openEdit(target)} title="Edit">
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-sm" onClick={() => setDeleteConfirm(target)} title="Delete">
                      <Trash2 className="size-3.5 text-danger" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingTarget ? "Edit Target" : "Add Target"}</DialogTitle>
            <DialogDescription>
              {editingTarget ? "Update the monitoring target configuration." : "Configure a new monitoring target."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-text-primary">Name</label>
              <Input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder="My Service" />
              {formErrors.name && <p className="mt-1 text-xs text-danger">{formErrors.name}</p>}
            </div>
            <div>
              <label className="text-xs font-medium text-text-primary">Type</label>
              <div className="flex gap-2 mt-1">
                {(["http", "tcp", "ssl", "dns", "container"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm((p) => ({ ...p, target_type: t }))}
                    className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                      form.target_type === t ? "bg-primary text-primary-foreground" : "bg-surface-elevated text-text-secondary hover:bg-surface-elevated/80"
                    }`}
                  >
                    {t.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-text-primary">Address</label>
              <Input
                value={form.address}
                onChange={(e) => setForm((p) => ({ ...p, address: e.target.value }))}
                placeholder={form.target_type === "http" ? "https://example.com" : form.target_type === "ssl" ? "example.com" : "example.com:443"}
              />
              {formErrors.address && <p className="mt-1 text-xs text-danger">{formErrors.address}</p>}
            </div>
            {form.target_type === "http" && (
              <div>
                <label className="text-xs font-medium text-text-primary">Expected Status Code</label>
                <Input type="number" value={form.expected_status ?? 200} onChange={(e) => setForm((p) => ({ ...p, expected_status: parseInt(e.target.value) || 200 }))} />
                {formErrors.expected_status && <p className="mt-1 text-xs text-danger">{formErrors.expected_status}</p>}
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-text-primary">Timeout (seconds)</label>
              <Input type="number" value={form.timeout_seconds} onChange={(e) => setForm((p) => ({ ...p, timeout_seconds: parseInt(e.target.value) || 30 }))} />
              {formErrors.timeout_seconds && <p className="mt-1 text-xs text-danger">{formErrors.timeout_seconds}</p>}
            </div>
            {form.target_type === "ssl" && (
              <div>
                <label className="text-xs font-medium text-text-primary">Warning Days</label>
                <Input type="number" value={form.warning_days} onChange={(e) => setForm((p) => ({ ...p, warning_days: parseInt(e.target.value) || 30 }))} />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>{editingTarget ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteConfirm(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Target</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &ldquo;{deleteConfirm?.name}&rdquo;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteConfirm && handleDelete(deleteConfirm)}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {historyTarget && (
        <TargetHistoryDrawer target={historyTarget} open={historyTarget !== null} onClose={() => setHistoryTarget(null)} />
      )}
    </RouteScaffold>
  );
}

function MetricCardSmall({ icon: Icon, label, value, detail }: { icon: any; label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-surface-elevated/70 p-4 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-tertiary">{label}</p>
          <p className="mt-1 text-2xl font-semibold tracking-tight text-text-primary">{value}</p>
        </div>
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
          <Icon className="size-4" />
        </div>
      </div>
      {detail && <p className="mt-2 text-xs text-text-secondary">{detail}</p>}
    </div>
  );
}
