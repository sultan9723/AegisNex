"use client";

import { useEffect, useState } from "react";
import { Server, Cpu, HardDrive, Network, Activity, Thermometer, Clock, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getSystemHealth, getSystemInfo, getMetrics, type SystemHealthResponse, type SystemInfoResponse, type MetricsResponse } from "@/lib/api";
import { useWebSocket } from "@/lib/ws";
import { Skeleton } from "@/components/common/Skeleton";
import { cn } from "@/lib/utils";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "\u2014";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h`;
  return `${Math.floor(seconds / 60)}m`;
}

function getBarColor(value: number): string {
  if (value >= 90) return "bg-danger";
  if (value >= 70) return "bg-warning";
  return "bg-gradient-to-r from-cyan-500 to-violet-500";
}

function getTextColor(value: number): string {
  if (value >= 90) return "text-danger";
  if (value >= 70) return "text-warning";
  return "text-text-primary";
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
  const healthScore = health?.health_score;
  const uptime = sysInfo?.uptime_seconds;

  return (
    <div className="space-y-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold text-text-primary">Infrastructure</h1>
            {healthScore && (
              <Badge variant={healthScore.score >= 80 ? "success-subtle" : healthScore.score >= 60 ? "warning-subtle" : "danger-subtle"} dot>
                {healthScore.score}%
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-text-tertiary">Host system resources and connectivity</p>
        </div>
      </div>

      {/* Resource gauges */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ResourceGauge
          icon={Cpu}
          label="CPU"
          value={cpu}
          loading={loading}
          subtitle={sysInfo?.hostname ?? "Host"}
        />
        <ResourceGauge
          icon={Activity}
          label="Memory"
          value={mem}
          loading={loading}
          subtitle={health?.metrics?.ram_total_gb ? `${health.metrics.ram_total_gb.toFixed(1)} GB total` : undefined}
        />
        <ResourceGauge
          icon={HardDrive}
          label="Disk"
          value={disk}
          loading={loading}
          subtitle={health?.metrics?.disk_free_gb ? `${health.metrics.disk_free_gb.toFixed(1)} GB free` : undefined}
        />
        <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-5 transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/55">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2.5">
              <div className="grid size-8 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
                <Network className="size-3.5 text-text-secondary" />
              </div>
              <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-tertiary">Network</span>
            </div>
            {networkOnline !== null && (
              <div className={cn("flex items-center gap-1.5 text-[11px] font-semibold", networkOnline ? "text-success" : "text-danger")}>
                <span className={cn("size-1.5 rounded-full", networkOnline ? "bg-success" : "bg-danger")} />
                {networkOnline ? "Online" : "Offline"}
              </div>
            )}
          </div>
          <div className="space-y-1.5 text-[11px] text-text-tertiary">
            <div className="flex justify-between">
              <span>Sent</span>
              <span className="text-text-secondary">{formatBytes(metrics?.metrics?.network_bytes_sent)}</span>
            </div>
            <div className="flex justify-between">
              <span>Received</span>
              <span className="text-text-secondary">{formatBytes(metrics?.metrics?.network_bytes_recv)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* System info */}
      <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-5 transition-all duration-200 hover:border-border/60">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="grid size-8 place-items-center rounded-lg bg-violet-500/10 text-violet-400">
            <Server className="size-3.5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">System Information</h3>
            <p className="text-[11px] text-text-tertiary">Host details and configuration</p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <InfoItem label="Operating System" value={loading ? undefined : sysInfo?.os} />
          <InfoItem label="Hostname" value={loading ? undefined : sysInfo?.hostname} />
          <InfoItem label="Uptime" value={loading ? undefined : formatDuration(uptime ?? null)} icon={Clock} />
          <InfoItem label="Docker" value={loading ? undefined : sysInfo?.docker_version ?? "Not available"} />
          {sysInfo?.python_version && (
            <InfoItem label="Python" value={sysInfo.python_version} />
          )}
          {healthScore && (
            <InfoItem
              label="Health Score"
              value={`${healthScore.score}% \u2014 ${healthScore.status}`}
              icon={Shield}
              valueColor={healthScore.score >= 80 ? "text-success" : healthScore.score >= 60 ? "text-warning" : "text-danger"}
            />
          )}
          {health?.metrics?.process_count != null && (
            <InfoItem label="Processes" value={String(health.metrics.process_count)} icon={Activity} />
          )}
          {health?.metrics?.cpu_load_1m != null && (
            <InfoItem label="Load Average" value={`${health.metrics.cpu_load_1m?.toFixed(2)} / ${health.metrics.cpu_load_5m?.toFixed(2)} / ${health.metrics.cpu_load_15m?.toFixed(2)}`} icon={Thermometer} />
          )}
        </div>
      </div>
    </div>
  );
}

function ResourceGauge({ icon: Icon, label, value, loading, subtitle }: { icon: React.ElementType; label: string; value?: number; loading: boolean; subtitle?: string }) {
  const pctValue = value ?? 0;
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-5 transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/55">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
            <Icon className="size-3.5 text-text-secondary" />
          </div>
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</span>
        </div>
      </div>
      {loading ? (
        <Skeleton className="mb-2 h-8 w-20" />
      ) : (
        <p className={cn("text-2xl font-bold tracking-tight", getTextColor(pctValue))}>
          {value != null ? `${pctValue.toFixed(1)}%` : "\u2014"}
        </p>
      )}
      {subtitle && <p className="mt-1 text-[11px] text-text-tertiary">{subtitle}</p>}
      {!loading && value != null && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface">
          <div
            className={cn("h-full rounded-full transition-all duration-700", getBarColor(pctValue))}
            style={{ width: `${Math.min(100, pctValue)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function InfoItem({ label, value, icon: Icon, valueColor }: { label: string; value?: string; icon?: React.ElementType; valueColor?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/20 bg-surface/30 px-3 py-2.5">
      {Icon && (
        <div className="grid size-7 shrink-0 place-items-center rounded-md bg-surface-elevated/60">
          <Icon className="size-3 text-text-tertiary" />
        </div>
      )}
      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</p>
        {value === undefined ? (
          <Skeleton className="mt-1 h-3.5 w-16" />
        ) : (
          <p className={cn("mt-0.5 text-[13px] font-semibold text-text-primary truncate", valueColor)}>{value}</p>
        )}
      </div>
    </div>
  );
}

function formatBytes(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null) return "\u2014";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
