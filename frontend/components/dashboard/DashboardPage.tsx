"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, Container, Cpu,
  HardDrive, ShieldCheck, Signal, Wifi, WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingState } from "@/components/common/LoadingState";
import { StatusBadge, type StatusState } from "@/components/common/StatusBadge";
import { TrendChart } from "@/components/dashboard/TrendChart";
import { SkeletonDashboard } from "@/components/common/Skeleton";
import {
  getDashboardWebSocketUrl,
  type ContainerRow,
  type DashboardRealtimeEvent,
  type DashboardSnapshot,
  type IncidentRow,
  type MetricsResponse,
  type RemediationRow,
  getDashboardSnapshot,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { formatTimestamp, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

type DashboardData = DashboardSnapshot;
type ConnectionStatus = "Connected" | "Reconnecting" | "Disconnected";

type AlertRow = {
  key: string; source: "HTTP" | "SSL" | "TCP";
  name: string; status: string; detail: string;
};

function buildTrend(metrics: MetricsResponse) {
  const cpu = metrics.chart_data.cpu;
  const memory = metrics.chart_data.memory;
  const labels = cpu?.labels?.length ? cpu.labels : memory?.labels ?? [];
  if (!labels.length) {
    return [{
      timestamp: formatTimestamp(metrics.timestamp),
      cpu: Number(metrics.metrics.cpu_percent ?? 0),
      memory: Number(metrics.metrics.ram_percent ?? 0),
    }];
  }
  return labels.map((label, index) => ({
    timestamp: label,
    cpu: Number(cpu?.values[index] ?? 0),
    memory: Number(memory?.values[index] ?? 0),
  }));
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("Disconnected");
  const reconnectAttempt = useRef(0);

  const load = useCallback(async () => {
    try {
      const snapshot = await getDashboardSnapshot();
      setData(snapshot);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load backend telemetry.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let closedByComponent = false;

    const applyRealtimeEvent = (event: DashboardRealtimeEvent) => {
      if (event.type === "metric_update") {
        setData(event.payload as DashboardSnapshot);
        return;
      }
      setData((current) => {
        if (!current) return current;
        if (event.type === "incident_created") return addIncident(current, event.payload as IncidentRow);
        if (event.type === "incident_resolved") return resolveIncident(current, event.payload as IncidentRow);
        if (event.type === "remediation_executed") return addRemediation(current, event.payload as RemediationRow);
        if (event.type === "container_status_changed") return updateContainer(current, event.payload as ContainerRow);
        return current;
      });
    };

    const scheduleReconnect = () => {
      if (closedByComponent) return;
      reconnectAttempt.current += 1;
      setConnectionStatus("Reconnecting");
      const delay = Math.min(10000, 1000 * 2 ** Math.min(reconnectAttempt.current, 4));
      reconnectTimer = window.setTimeout(connect, delay);
    };

    const connect = () => {
      setConnectionStatus("Reconnecting");
      socket = new WebSocket(getDashboardWebSocketUrl());
      socket.onopen = () => {
        const wasReconnect = reconnectAttempt.current > 0;
        reconnectAttempt.current = 0;
        setConnectionStatus("Connected");
        if (wasReconnect) void load();
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as DashboardRealtimeEvent;
          applyRealtimeEvent(event);
          setError(null);
          setLoading(false);
        } catch {
          setError("Received an invalid realtime dashboard event.");
        }
      };
      socket.onclose = () => {
        if (closedByComponent) { setConnectionStatus("Disconnected"); return; }
        scheduleReconnect();
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closedByComponent = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
      setConnectionStatus("Disconnected");
    };
  }, [load]);

  const trend = useMemo(() => (data ? buildTrend(data.metrics) : []), [data]);
  const eventTrend = useMemo(() => {
    const labels = trend.map((item) => item.timestamp);
    const incidentBuckets = bucketByHour(data?.incidents.incidents.map((item) => item.timestamp) ?? []);
    const remediationBuckets = bucketByHour(data?.remediations.actions.map((item) => item.timestamp) ?? []);
    return labels.map((timestamp) => ({
      timestamp,
      incidents: incidentBuckets.get(timestamp) ?? 0,
      remediations: remediationBuckets.get(timestamp) ?? 0,
    }));
  }, [data, trend]);

  if (loading) return <SkeletonDashboard />;

  if (error || !data) {
    if (error && (error.includes('Authentication required') || error.includes('401'))) {
      return <LoadingState message="Redirecting to login..." />;
    }
    return (
      <EmptyState
        title="Unable to load dashboard"
        description={error ?? "Could not connect to the AegisNex backend. Please check if the backend is running on http://localhost:8000."}
        actionLabel="Retry"
        onAction={() => { setLoading(true); void load(); }}
      />
    );
  }

  const activeIncidents = data.incidents.active_incidents;
  const alerts = buildAlerts(data);
  const health = data.system.health_score;
  const healthStatus = statusFromHealth(health.score);
  const running = data.system.running_container_count;
  const totalContainers = data.containers.count;
  const metrics = data.metrics.metrics;

  return (
    <ErrorBoundary>
    <div className="space-y-8 animate-fade-in-up">
      {/* Hero Header */}
      <header className="grid gap-6 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-7">
          <div className="mb-4 flex items-center gap-3 text-xs text-text-secondary">
            <ShieldCheck className="size-4 text-primary" />
            <span>Operations overview</span>
            <ConnectionIndicator status={connectionStatus} />
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-text-primary md:text-4xl">
            System <span className="gradient-text-cyan">Health</span> &amp; Incident Overview
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
            Current platform state from persisted monitoring checks, incident records, and host telemetry.
            Last sampled {formatTimestamp(data.system.timestamp)}.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 lg:col-span-5">
          <HeaderStat label="Active incidents" value={String(activeIncidents.length)} tone={activeIncidents.length ? "danger" : "normal"} />
          <HeaderStat label="Active alerts" value={String(alerts.length)} tone={alerts.length ? "warning" : "normal"} />
          <HeaderStat label="Containers" value={`${running}/${totalContainers}`} tone={running === totalContainers ? "normal" : "warning"} />
        </div>
      </header>

      {/* Metric Cards Row */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardSmall icon={Cpu} label="CPU Usage" value={pct(metrics.cpu_percent)} progress={metrics.cpu_percent} />
        <MetricCardSmall icon={Activity} label="Memory" value={pct(metrics.ram_percent)} progress={metrics.ram_percent} />
        <MetricCardSmall icon={HardDrive} label="Disk" value={pct(metrics.disk_percent)} progress={metrics.disk_percent} />
        <MetricCardSmall icon={Container} label="Containers" value={`${running}/${totalContainers}`} progress={totalContainers > 0 ? (running / totalContainers) * 100 : 0} />
      </section>

      {/* Health Score + Incident Queue */}
      <section className="grid gap-6 lg:grid-cols-12">
        <PrimaryPanel className="lg:col-span-5">
          <div className="flex items-start justify-between gap-6">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-text-tertiary">Health Score</p>
              <div className="mt-4 flex items-end gap-3">
                <span className="text-6xl font-semibold leading-none tracking-tight text-text-primary">{health.score}</span>
                <StatusBadge status={healthStatus} label={health.status} pulse />
              </div>
              <div className="mt-6 grid grid-cols-3 gap-5">
                <SmallMetric label="CPU" value={pct(metrics.cpu_percent)} />
                <SmallMetric label="Memory" value={pct(metrics.ram_percent)} />
                <SmallMetric label="Disk" value={pct(metrics.disk_percent)} />
              </div>
            </div>
            <HealthRing score={health.score} />
          </div>
          <div className="mt-6 rounded-lg border border-border/50 bg-surface/50 p-3">
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <Signal className="size-3.5 text-success" />
              <span>All systems are being monitored</span>
            </div>
          </div>
        </PrimaryPanel>

        <PrimaryPanel className="lg:col-span-7">
          <SectionHeading title="Incident Queue" count={activeIncidents.length} />
          <div className="mt-4 divide-y divide-border/50">
            {activeIncidents.length ? (
              activeIncidents.slice(0, 6).map((incident) => (
                <IncidentRowItem key={incident.incident_id} incident={incident} />
              ))
            ) : (
              <EmptyLine icon={CheckCircle2} title="No active incidents" description="All monitored services are currently outside incident state." />
            )}
          </div>
        </PrimaryPanel>
      </section>

      {/* Active Alerts + Signal Summary */}
      <section className="grid gap-6 lg:grid-cols-12">
        <PrimaryPanel className="lg:col-span-8">
          <SectionHeading title="Active Alerts" count={alerts.length} />
          <div className="mt-4 divide-y divide-border/50">
            {alerts.length ? (
              alerts.slice(0, 8).map((alert) => <AlertLineItem key={alert.key} alert={alert} />)
            ) : (
              <EmptyLine icon={CheckCircle2} title="No active alerts" description="HTTP, SSL, and TCP targets have no active warning state." />
            )}
          </div>
        </PrimaryPanel>

        <PrimaryPanel className="lg:col-span-4">
          <SectionHeading title="Signal Summary" />
          <div className="mt-6 space-y-5">
            <SummaryLine label="HTTP Availability" value={pct(data.http_monitoring.availability_percent)} status={data.http_monitoring.status} />
            <SummaryLine label="SSL Warnings" value={`${data.ssl_monitoring.warning_count}/${data.ssl_monitoring.total_count}`} status={data.ssl_monitoring.status} />
            <SummaryLine label="TCP Availability" value={pct(data.tcp_monitoring.availability_percent)} status={data.tcp_monitoring.status} />
            <SummaryLine label="Failed Notifications" value={String(data.notifications.notification_stats.failed_notifications)} status={data.notifications.notification_stats.failed_notifications ? "warning" : "ok"} />
          </div>
        </PrimaryPanel>
      </section>

      {/* Trend Charts */}
      <section className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <TrendChart title="CPU Trend" data={trend} dataKey="cpu" color="#00E5FF" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Memory Trend" data={trend} dataKey="memory" color="#8B5CF6" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Incident Trend" data={eventTrend} dataKey="incidents" color="#FB7185" type="bar" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Remediation Trend" data={eventTrend} dataKey="remediations" color="#34D399" type="bar" />
        </div>
      </section>
    </div>
    </ErrorBoundary>
  );
}

/* ---- Sub-components ---- */

function buildAlerts(data: DashboardData): AlertRow[] {
  const http = data.http_monitoring.checks
    .filter((c) => !c.available)
    .map((c) => ({ key: `http-${c.name}`, source: "HTTP" as const, name: c.name, status: "down", detail: c.error || `HTTP ${c.status_code ?? "no response"}` }));
  const ssl = data.ssl_monitoring.checks
    .filter((c) => c.status !== "ok")
    .map((c) => ({ key: `ssl-${c.name}`, source: "SSL" as const, name: c.name, status: c.status, detail: c.error || `${c.days_remaining ?? "unknown"} days remaining` }));
  const tcp = data.tcp_monitoring.checks
    .filter((c) => !c.reachable)
    .map((c) => ({ key: `tcp-${c.name}`, source: "TCP" as const, name: c.name, status: "down", detail: c.error || `${c.host}:${c.port}` }));
  return [...http, ...ssl, ...tcp];
}

function addIncident(data: DashboardData, incident: IncidentRow): DashboardData {
  if (data.incidents.incidents.some((i) => i.incident_id === incident.incident_id)) return data;
  const active = [incident, ...data.incidents.active_incidents];
  return { ...data, system: { ...data.system, active_incident_count: active.length }, incidents: { ...data.incidents, active_incidents: active, recent_incidents: [incident, ...data.incidents.recent_incidents].slice(0, 6), incidents: [incident, ...data.incidents.incidents], active_count: active.length, count: data.incidents.count + 1 } };
}

function resolveIncident(data: DashboardData, incident: IncidentRow): DashboardData {
  const active = data.incidents.active_incidents.filter((i) => i.incident_id !== incident.incident_id);
  const resolved = data.incidents.resolved_incidents.some((i) => i.incident_id === incident.incident_id) ? data.incidents.resolved_incidents.map((i) => (i.incident_id === incident.incident_id ? incident : i)) : [incident, ...data.incidents.resolved_incidents];
  return { ...data, system: { ...data.system, active_incident_count: active.length }, incidents: { ...data.incidents, active_incidents: active, resolved_incidents: resolved, incidents: data.incidents.incidents.map((i) => (i.incident_id === incident.incident_id ? incident : i)), active_count: active.length, resolved_count: resolved.length } };
}

function addRemediation(data: DashboardData, remediation: RemediationRow): DashboardData {
  const key = `${remediation.timestamp}-${remediation.service_name}-${remediation.action}-${remediation.incident_id ?? ""}`;
  if (data.remediations.actions.some((i) => `${i.timestamp}-${i.service_name}-${i.action}-${i.incident_id ?? ""}` === key)) return data;
  return { ...data, remediations: { ...data.remediations, actions: [remediation, ...data.remediations.actions], recent_remediations: [remediation, ...data.remediations.recent_remediations].slice(0, 6), count: data.remediations.count + 1 } };
}

function updateContainer(data: DashboardData, container: ContainerRow): DashboardData {
  const containers = data.containers.containers.some((c) => c.name === container.name) ? data.containers.containers.map((c) => (c.name === container.name ? container : c)) : [container, ...data.containers.containers];
  return { ...data, system: { ...data.system, running_container_count: containers.filter((c) => c.status === "running").length }, containers: { ...data.containers, containers, count: containers.length } };
}

function bucketByHour(timestamps: string[]) {
  const buckets = new Map<string, number>();
  timestamps.forEach((ts) => {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return;
    const label = `${String(d.getHours()).padStart(2, "0")}:00`;
    buckets.set(label, (buckets.get(label) ?? 0) + 1);
  });
  return buckets;
}

function statusFromHealth(score: number): StatusState {
  return score >= 80 ? "healthy" : score >= 60 ? "warning" : "danger";
}

/* ---- Presentational Components ---- */

function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  const Icon = status === "Connected" ? Wifi : WifiOff;
  const color = status === "Connected" ? "text-success" : status === "Reconnecting" ? "text-warning" : "text-danger";
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${color}`}>
      <Icon className="size-3" />
      {status}
    </span>
  );
}

function HeaderStat({ label, value, tone }: { label: string; value: string; tone: "normal" | "warning" | "danger" }) {
  const valueColor = tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-text-primary";
  return (
    <div className="rounded-xl border border-border/50 bg-surface-elevated/50 px-4 py-3 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-text-tertiary">{label}</p>
      <p className={`mt-1.5 text-2xl font-semibold tracking-tight ${valueColor}`}>{value}</p>
    </div>
  );
}

function MetricCardSmall({ icon: Icon, label, value, progress }: { icon: LucideIcon; label: string; value: string; progress?: number }) {
  return (
    <div className="rounded-xl border border-border/60 bg-surface-elevated/70 p-4 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md hover:bg-surface-elevated/90">
      <div className="flex items-center gap-3">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
          <Icon className="size-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-medium uppercase tracking-[0.08em] text-text-tertiary">{label}</p>
          <p className="mt-0.5 text-lg font-semibold tracking-tight text-text-primary">{value}</p>
        </div>
      </div>
      {typeof progress === "number" && (
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-chart-2 transition-all duration-700 ease-out-expo"
            style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
          />
        </div>
      )}
    </div>
  );
}

function PrimaryPanel({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-border/70 bg-surface-elevated/80 p-5 shadow-md md:p-6", className)}>
      {children}
    </div>
  );
}

function SectionHeading({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
      {typeof count === "number" && (
        <span className={cn(
          "inline-flex items-center justify-center rounded-md px-2 py-0.5 text-[11px] font-medium",
          count > 0 ? "bg-danger/10 text-danger" : "bg-success/10 text-success"
        )}>
          {count}
        </span>
      )}
    </div>
  );
}

function HealthRing({ score }: { score: number }) {
  const normalized = Math.max(0, Math.min(100, score));
  const color = normalized >= 80 ? "#34D399" : normalized >= 60 ? "#F59E0B" : "#FB7185";
  return (
    <div className="relative size-24 shrink-0">
      <svg className="-rotate-90" viewBox="0 0 100 100" aria-hidden="true" width="96" height="96">
        <defs>
          <linearGradient id="ring-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="1" />
            <stop offset="100%" stopColor={color} stopOpacity="0.6" />
          </linearGradient>
          <filter id="ring-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <circle cx="50" cy="50" r="42" fill="none" stroke="hsl(var(--border) / 0.4)" strokeWidth="6" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="url(#ring-grad)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={263.9}
          strokeDashoffset={263.9 - (normalized / 100) * 263.9}
          className="transition-all duration-1000 ease-out-expo"
          filter="url(#ring-glow)"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold tracking-tight text-text-primary">{score}</span>
      </div>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-[0.1em] text-text-tertiary">{label}</p>
      <p className="mt-1 text-lg font-semibold text-text-primary">{value}</p>
    </div>
  );
}

function IncidentRowItem({ incident }: { incident: IncidentRow }) {
  const severityColor = incident.severity === "critical" || incident.severity === "high" ? "border-l-danger/40" : "border-l-warning/40";
  return (
    <div className={`grid gap-4 py-3.5 md:grid-cols-[1fr_auto] md:items-center border-l-2 ${severityColor} pl-4 -ml-1`}>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-text-primary">{incident.service_name}</p>
        <p className="mt-0.5 truncate text-xs text-text-secondary">{incident.description}</p>
        <p className="mt-0.5 text-[11px] text-text-tertiary">{formatTimestamp(incident.timestamp)}</p>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={incident.severity === "critical" || incident.severity === "high" ? "danger" : "warning"} label={incident.severity} />
        <StatusBadge status="warning" label={incident.status} pulse />
      </div>
    </div>
  );
}

function AlertLineItem({ alert }: { alert: AlertRow }) {
  return (
    <div className="grid gap-3 py-3.5 md:grid-cols-[80px_1fr_auto] md:items-center">
      <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-tertiary">{alert.source}</span>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-text-primary">{alert.name}</p>
        <p className="mt-0.5 truncate text-xs text-text-secondary">{alert.detail}</p>
      </div>
      <StatusBadge status={alert.status === "warning" ? "warning" : "danger"} label={alert.status} pulse />
    </div>
  );
}

function SummaryLine({ label, value, status }: { label: string; value: string; status: string }) {
  const healthy = status === "ok" || status === "healthy";
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-text-secondary">{label}</span>
      <div className="flex items-center gap-2">
        <span className={cn("size-1.5 rounded-full", healthy ? "bg-success" : "bg-warning")} />
        <span className={cn("text-sm font-semibold", healthy ? "text-text-primary" : "text-warning")}>{value}</span>
      </div>
    </div>
  );
}

function EmptyLine({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 py-6">
      <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-success/10 text-success ring-1 ring-success/20">
        <Icon className="size-4" />
      </div>
      <div>
        <p className="text-sm font-medium text-text-primary">{title}</p>
        <p className="mt-0.5 text-xs text-text-secondary">{description}</p>
      </div>
    </div>
  );
}
