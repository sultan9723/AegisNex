"use client";

import { useEffect, useState } from "react";
import { Server, Cpu, HardDrive, Network, Activity } from "lucide-react";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getSystemHealth, getSystemInfo, getMetrics, type SystemHealthResponse, type SystemInfoResponse, type MetricsResponse } from "@/lib/api";
import { useWebSocket } from "@/lib/ws";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "\u2014";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h`;
  return `${Math.floor(seconds / 60)}m`;
}

export default function InfrastructurePage() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [sysInfo, setSysInfo] = useState<SystemInfoResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getSystemHealth().catch(() => null),
      getSystemInfo().catch(() => null),
      getMetrics().catch(() => null),
    ]).then(([h, s, m]) => {
      setHealth(h);
      setSysInfo(s);
      setMetrics(m);
    }).finally(() => setLoading(false));
  }, []);

  // Live update from dashboard WebSocket (for CPU/memory/disk live values)
  useWebSocket("/ws/dashboard", (msg: unknown) => {
    const event = msg as { type?: string; payload?: { system?: SystemHealthResponse; metrics?: MetricsResponse } };
    if (event.type === "metric_update" && event.payload) {
      if (event.payload.system) setHealth(event.payload.system);
      if (event.payload.metrics) setMetrics(event.payload.metrics);
      setLoading(false);
    }
  });

  const cpu = health?.metrics?.cpu_percent ?? metrics?.metrics?.cpu_percent;
  const mem = health?.metrics?.ram_percent ?? metrics?.metrics?.ram_percent;
  const disk = health?.metrics?.disk_percent ?? metrics?.metrics?.disk_percent;
  const networkOnline = metrics?.network ? Object.values(metrics.network).some((v: unknown) => v === true || v === "up" || v === "connected") : null;

  return (
    <RouteScaffold title="Infrastructure Overview" description="Monitor host system resources, network connectivity, and infrastructure health metrics in real-time." icon={Server}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardSmall icon={Cpu} label="CPU Usage" value={loading ? "..." : cpu != null ? `${cpu.toFixed(1)}%` : "\u2014"} progress={cpu ?? undefined} status="normal" />
        <MetricCardSmall icon={Activity} label="Memory Usage" value={loading ? "..." : mem != null ? `${mem.toFixed(1)}%` : "\u2014"} progress={mem ?? undefined} status="normal" />
        <MetricCardSmall icon={HardDrive} label="Disk Usage" value={loading ? "..." : disk != null ? `${disk.toFixed(1)}%` : "\u2014"} progress={disk ?? undefined} status="normal" />
        <MetricCardSmall icon={Network} label="Network" value={loading ? "..." : networkOnline === true ? "Online" : networkOnline === false ? "Offline" : "\u2014"} status={networkOnline === true ? "healthy" : "unknown"} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>System Information</CardTitle>
          <p className="mt-0.5 text-xs text-text-secondary">Host system details and configuration</p>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="divide-y divide-border/50">
            <InfoRow label="Operating System" value={loading ? "..." : sysInfo?.os ?? "\u2014"} />
            <InfoRow label="Hostname" value={loading ? "..." : sysInfo?.hostname ?? "\u2014"} />
            <InfoRow label="Uptime" value={loading ? "..." : formatDuration(sysInfo?.uptime_seconds ?? null)} />
            <InfoRow label="Docker Version" value={loading ? "..." : sysInfo?.docker_version ?? "Not available"} />
          </div>
        </CardContent>
      </Card>
    </RouteScaffold>
  );
}

function MetricCardSmall({ icon: Icon, label, value, progress, status }: { icon: any; label: string; value: string; progress?: number; status?: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-surface-elevated/70 p-4 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
            <Icon className="size-3.5" />
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-tertiary">{label}</p>
            <p className="mt-0.5 text-lg font-semibold tracking-tight text-text-primary">{value}</p>
          </div>
        </div>
        {status && <Badge variant={status === "healthy" ? "success-subtle" : "secondary"} dot>{status === "healthy" ? "Normal" : status}</Badge>}
      </div>
      {typeof progress === "number" && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-chart-2 transition-all duration-700"
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="text-sm font-medium text-text-primary">{value}</span>
    </div>
  );
}
