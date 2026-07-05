"use client";

import { useCallback, useEffect, useState } from "react";
import { Boxes, Play, Square, RefreshCw, Timer, Terminal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getContainers, startContainer, stopContainer, restartContainer, getContainerLogs, type ContainerRow } from "@/lib/api";
import { Skeleton, SkeletonList } from "@/components/common/Skeleton";
import { useWebSocket } from "@/lib/ws";
import { toast } from "sonner";

function formatUptime(container: ContainerRow): string {
  if (container.status !== "running") return "\u2014";
  if (container.started_at) {
    const started = new Date(container.started_at).getTime();
    const now = Date.now();
    const diff = Math.floor((now - started) / 1000);
    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
    return `${Math.floor(diff / 86400)}d ${Math.floor((diff % 86400) / 3600)}h`;
  }
  return "\u2014";
}

export default function ContainersPage() {
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [logs, setLogs] = useState<{ name: string; lines: string[] } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getContainers().then((res) => setContainers(res.containers)).catch(() => setContainers([])).finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  useWebSocket("/ws/containers", (data: unknown) => {
    const msg = data as { type?: string; payload?: { containers?: ContainerRow[] } };
    if (msg.type === "container_list" && msg.payload?.containers) {
      setContainers(msg.payload.containers);
      setLoading(false);
    }
  });

  const running = containers.filter((c) => c.status === "running");
  const stopped = containers.filter((c) => c.status !== "running");
  const totalRestarts = containers.reduce((s, c) => s + (c.restart_count ?? 0), 0);

  const handleAction = async (name: string, action: "start" | "stop" | "restart") => {
    setActionLoading(`${action}-${name}`);
    try {
      if (action === "start") { await startContainer(name); toast.success(`Started ${name}`); }
      else if (action === "stop") { await stopContainer(name); toast.success(`Stopped ${name}`); }
      else { await restartContainer(name); toast.success(`Restarted ${name}`); }
      await load();
    } catch {
      toast.error(`Failed to ${action} ${name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewLogs = async (name: string) => {
    try {
      const res = await getContainerLogs(name, 50);
      if (res.status === "ok") setLogs({ name, lines: res.logs });
    } catch {
      toast.error(`Failed to load logs for ${name}`);
    }
  };

  return (
    <RouteScaffold title="Docker Containers" description="Monitor and manage Docker containers with real-time status updates and health checks." icon={Boxes}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardSmall icon={Boxes} label="Total Containers" value={loading ? "..." : String(containers.length)} detail="All containers" />
        <MetricCardSmall icon={Play} label="Running" value={loading ? "..." : String(running.length)} detail="Active containers" color="text-success" />
        <MetricCardSmall icon={Square} label="Stopped" value={loading ? "..." : String(stopped.length)} detail="Inactive containers" />
        <MetricCardSmall icon={Timer} label="Total Restarts" value={loading ? "..." : String(totalRestarts)} detail="All time" />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Container List</CardTitle>
              <p className="mt-0.5 text-xs text-text-secondary">All Docker containers and their current status</p>
            </div>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`size-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="divide-y divide-border/50">
            {loading && <div className="py-4"><SkeletonList count={5} /></div>}
            {!loading && containers.length === 0 && <p className="py-6 text-center text-sm text-text-tertiary">No Docker containers found.</p>}
            {containers.map((container) => (
              <div key={container.name} className="flex items-center justify-between py-3.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary">{container.name}</p>
                  {container.image && <p className="text-xs text-text-tertiary">{container.image}</p>}
                  <div className="mt-0.5 flex items-center gap-4 text-xs text-text-tertiary">
                    <span>Uptime: {formatUptime(container)}</span>
                    <span>Restarts: {container.restart_count ?? 0}</span>
                    {typeof container.cpu_percent === "number" && <span>CPU: {container.cpu_percent.toFixed(1)}%</span>}
                    {typeof container.memory_percent === "number" && <span>Mem: {container.memory_percent.toFixed(1)}%</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0 ml-4">
                  <Badge variant={container.status === "running" ? "success-subtle" : "secondary"} dot pulse={container.status === "running"}>{container.status}</Badge>
                  {container.status !== "running" && (
                    <Button variant="ghost" size="icon-sm" onClick={() => handleAction(container.name, "start")} disabled={actionLoading === `start-${container.name}`} title="Start">
                      <Play className="size-3.5" />
                    </Button>
                  )}
                  {container.status === "running" && (
                    <Button variant="ghost" size="icon-sm" onClick={() => handleAction(container.name, "stop")} disabled={actionLoading === `stop-${container.name}`} title="Stop">
                      <Square className="size-3.5" />
                    </Button>
                  )}
                  <Button variant="ghost" size="icon-sm" onClick={() => handleAction(container.name, "restart")} disabled={actionLoading === `restart-${container.name}`} title="Restart">
                    <RefreshCw className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon-sm" onClick={() => handleViewLogs(container.name)} title="View Logs">
                    <Terminal className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {logs && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Logs: {logs.name}</CardTitle>
                <p className="mt-0.5 text-xs text-text-secondary">Recent log output</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setLogs(null)}>Close</Button>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <pre className="max-h-96 overflow-auto rounded-lg bg-surface p-4 text-xs text-text-secondary font-mono leading-relaxed">
              {logs.lines.length === 0 ? <span className="text-text-tertiary">No logs available.</span> : logs.lines.map((line, i) => <div key={i}>{line}</div>)}
            </pre>
          </CardContent>
        </Card>
      )}
    </RouteScaffold>
  );
}

function MetricCardSmall({ icon: Icon, label, value, detail, color }: { icon: any; label: string; value: string; detail?: string; color?: string }) {
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
