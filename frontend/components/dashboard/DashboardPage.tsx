"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingState } from "@/components/common/LoadingState";
import { StatusBadge, type StatusState } from "@/components/common/StatusBadge";
import { TrendChart } from "@/components/dashboard/TrendChart";
import {
  getContainers,
  getDashboardWebSocketUrl,
  getHttpMonitoring,
  getIncidents,
  getMetrics,
  getNotifications,
  getRemediations,
  getSslMonitoring,
  getSystemHealth,
  getTcpMonitoring,
  type ContainerRow,
  type DashboardRealtimeEvent,
  type DashboardSnapshot,
  type IncidentRow,
  type MetricsResponse,
  type RemediationRow,
} from "@/lib/api";
import { formatTimestamp, pct } from "@/lib/format";

type DashboardData = DashboardSnapshot;
type ConnectionStatus = "Connected" | "Reconnecting" | "Disconnected";

type AlertRow = {
  key: string;
  source: "HTTP" | "SSL" | "TCP";
  name: string;
  status: string;
  detail: string;
};

function buildTrend(metrics: MetricsResponse) {
  const cpu = metrics.chart_data.cpu;
  const memory = metrics.chart_data.memory;
  const labels = cpu?.labels?.length ? cpu.labels : memory?.labels ?? [];
  if (!labels.length) {
    return [
      {
        timestamp: formatTimestamp(metrics.timestamp),
        cpu: Number(metrics.metrics.cpu_percent ?? 0),
        memory: Number(metrics.metrics.ram_percent ?? 0),
      },
    ];
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
      const [system, containers, incidents, metrics, notifications, remediations, httpMonitoring, sslMonitoring, tcpMonitoring] = await Promise.all([
        getSystemHealth(),
        getContainers(),
        getIncidents(),
        getMetrics(),
        getNotifications(),
        getRemediations(),
        getHttpMonitoring(),
        getSslMonitoring(),
        getTcpMonitoring(),
      ]);
      setData({ system, containers, incidents, metrics, notifications, remediations, http_monitoring: httpMonitoring, ssl_monitoring: sslMonitoring, tcp_monitoring: tcpMonitoring });
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
        reconnectAttempt.current = 0;
        setConnectionStatus("Connected");
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
        if (closedByComponent) {
          setConnectionStatus("Disconnected");
          return;
        }
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
  }, []);

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

  if (loading) return <LoadingState />;
  if (error || !data) {
    return (
      <EmptyState
        title="FastAPI backend unavailable"
        description={error ?? "Start the AegisNex backend on http://127.0.0.1:8000."}
        actionLabel="Retry"
        onAction={() => {
          setLoading(true);
          void load();
        }}
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
    <div className="space-y-10">
      <header className="grid gap-6 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-7">
          <div className="mb-4 flex items-center gap-3 text-sm text-muted-foreground">
            <ShieldCheck className="size-5 text-primary" />
            <span>Operations overview</span>
            <RealtimeStatus status={connectionStatus} />
          </div>
          <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
            Incidents, health, and active alerts
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
            Current platform state from persisted monitoring checks, incident records, and host telemetry.
            Last sampled {formatTimestamp(data.system.timestamp)}.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-8 lg:col-span-5">
          <HeaderStat label="Active incidents" value={String(activeIncidents.length)} tone={activeIncidents.length ? "danger" : "normal"} />
          <HeaderStat label="Active alerts" value={String(alerts.length)} tone={alerts.length ? "warning" : "normal"} />
          <HeaderStat label="Containers" value={`${running}/${totalContainers}`} tone={running === totalContainers ? "normal" : "warning"} />
        </div>
      </header>

      <section className="grid gap-8 lg:grid-cols-12">
        <PrimaryPanel className="lg:col-span-5">
          <div className="flex items-start justify-between gap-6">
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.12em] text-muted-foreground">Health score</p>
              <div className="mt-5 flex items-end gap-4">
                <span className="text-7xl font-semibold leading-none text-foreground">{health.score}</span>
                <StatusBadge status={healthStatus} label={health.status} />
              </div>
            </div>
            <HealthRing score={health.score} />
          </div>
          <div className="mt-10 grid grid-cols-3 gap-6 border-t border-border pt-6">
            <SmallMetric label="CPU" value={pct(metrics.cpu_percent)} />
            <SmallMetric label="Memory" value={pct(metrics.ram_percent)} />
            <SmallMetric label="Disk" value={pct(metrics.disk_percent)} />
          </div>
        </PrimaryPanel>

        <PrimaryPanel className="lg:col-span-7">
          <SectionHeading title="Incident queue" count={activeIncidents.length} />
          <div className="mt-5 divide-y divide-border">
            {activeIncidents.length ? (
              activeIncidents.slice(0, 6).map((incident) => (
                <IncidentRow key={incident.incident_id} incident={incident} />
              ))
            ) : (
              <EmptyLine icon={CheckCircle2} title="No active incidents" description="All monitored services are currently outside incident state." />
            )}
          </div>
        </PrimaryPanel>
      </section>

      <section className="grid gap-8 lg:grid-cols-12">
        <PrimaryPanel className="lg:col-span-8">
          <SectionHeading title="Active alerts" count={alerts.length} />
          <div className="mt-5 divide-y divide-border">
            {alerts.length ? (
              alerts.slice(0, 8).map((alert) => <AlertLine key={alert.key} alert={alert} />)
            ) : (
              <EmptyLine icon={CheckCircle2} title="No active alerts" description="HTTP, SSL, and TCP targets have no active warning state." />
            )}
          </div>
        </PrimaryPanel>

        <PrimaryPanel className="lg:col-span-4">
          <SectionHeading title="Signal summary" />
          <div className="mt-6 space-y-6">
            <SummaryLine label="HTTP availability" value={pct(data.http_monitoring.availability_percent)} status={data.http_monitoring.status} />
            <SummaryLine label="SSL warnings" value={`${data.ssl_monitoring.warning_count}/${data.ssl_monitoring.total_count}`} status={data.ssl_monitoring.status} />
            <SummaryLine label="TCP availability" value={pct(data.tcp_monitoring.availability_percent)} status={data.tcp_monitoring.status} />
            <SummaryLine label="Failed notifications" value={String(data.notifications.notification_stats.failed_notifications)} status={data.notifications.notification_stats.failed_notifications ? "warning" : "ok"} />
          </div>
        </PrimaryPanel>
      </section>

      <section className="grid gap-8 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <TrendChart title="CPU trend" data={trend} dataKey="cpu" color="#00E5FF" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Memory trend" data={trend} dataKey="memory" color="#8B5CF6" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Incident trend" data={eventTrend} dataKey="incidents" color="#EF4444" type="bar" />
        </div>
        <div className="lg:col-span-6">
          <TrendChart title="Remediation trend" data={eventTrend} dataKey="remediations" color="#22C55E" type="bar" />
        </div>
      </section>
    </div>
  );
}

function buildAlerts(data: DashboardData): AlertRow[] {
  const http = data.http_monitoring.checks
    .filter((check) => !check.available)
    .map((check) => ({
      key: `http-${check.name}`,
      source: "HTTP" as const,
      name: check.name,
      status: "down",
      detail: check.error || `HTTP ${check.status_code ?? "no response"}`,
    }));
  const ssl = data.ssl_monitoring.checks
    .filter((check) => check.status !== "ok")
    .map((check) => ({
      key: `ssl-${check.name}`,
      source: "SSL" as const,
      name: check.name,
      status: check.status,
      detail: check.error || `${check.days_remaining ?? "unknown"} days remaining`,
    }));
  const tcp = data.tcp_monitoring.checks
    .filter((check) => !check.reachable)
    .map((check) => ({
      key: `tcp-${check.name}`,
      source: "TCP" as const,
      name: check.name,
      status: "down",
      detail: check.error || `${check.host}:${check.port}`,
    }));
  return [...http, ...ssl, ...tcp];
}

function addIncident(data: DashboardData, incident: IncidentRow): DashboardData {
  if (data.incidents.incidents.some((item) => item.incident_id === incident.incident_id)) return data;
  const activeIncidents = [incident, ...data.incidents.active_incidents];
  const incidents = [incident, ...data.incidents.incidents];
  return {
    ...data,
    system: { ...data.system, active_incident_count: activeIncidents.length },
    incidents: {
      ...data.incidents,
      active_incidents: activeIncidents,
      recent_incidents: [incident, ...data.incidents.recent_incidents].slice(0, 6),
      incidents,
      active_count: activeIncidents.length,
      count: incidents.length,
    },
  };
}

function resolveIncident(data: DashboardData, incident: IncidentRow): DashboardData {
  const activeIncidents = data.incidents.active_incidents.filter((item) => item.incident_id !== incident.incident_id);
  const resolvedExists = data.incidents.resolved_incidents.some((item) => item.incident_id === incident.incident_id);
  const resolvedIncidents = resolvedExists
    ? data.incidents.resolved_incidents.map((item) => (item.incident_id === incident.incident_id ? incident : item))
    : [incident, ...data.incidents.resolved_incidents];
  const incidents = data.incidents.incidents.map((item) => (item.incident_id === incident.incident_id ? incident : item));
  return {
    ...data,
    system: { ...data.system, active_incident_count: activeIncidents.length },
    incidents: {
      ...data.incidents,
      active_incidents: activeIncidents,
      resolved_incidents: resolvedIncidents,
      recent_incidents: data.incidents.recent_incidents.map((item) => (item.incident_id === incident.incident_id ? incident : item)),
      incidents,
      active_count: activeIncidents.length,
      resolved_count: resolvedIncidents.length,
    },
  };
}

function addRemediation(data: DashboardData, remediation: RemediationRow): DashboardData {
  const key = `${remediation.timestamp}-${remediation.service_name}-${remediation.action}-${remediation.incident_id ?? ""}`;
  const exists = data.remediations.actions.some(
    (item) => `${item.timestamp}-${item.service_name}-${item.action}-${item.incident_id ?? ""}` === key,
  );
  if (exists) return data;
  return {
    ...data,
    remediations: {
      ...data.remediations,
      actions: [remediation, ...data.remediations.actions],
      recent_remediations: [remediation, ...data.remediations.recent_remediations].slice(0, 6),
      count: data.remediations.count + 1,
    },
  };
}

function updateContainer(data: DashboardData, container: ContainerRow): DashboardData {
  const containers = data.containers.containers.some((item) => item.name === container.name)
    ? data.containers.containers.map((item) => (item.name === container.name ? container : item))
    : [container, ...data.containers.containers];
  const runningContainerCount = containers.filter((item) => item.status === "running").length;
  return {
    ...data,
    system: { ...data.system, running_container_count: runningContainerCount },
    containers: { ...data.containers, containers, count: containers.length },
  };
}

function bucketByHour(timestamps: string[]) {
  const buckets = new Map<string, number>();
  timestamps.forEach((timestamp) => {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return;
    const label = `${String(date.getHours()).padStart(2, "0")}:00`;
    buckets.set(label, (buckets.get(label) ?? 0) + 1);
  });
  return buckets;
}

function statusFromHealth(score: number): StatusState {
  if (score >= 80) return "healthy";
  if (score >= 60) return "warning";
  return "danger";
}

function RealtimeStatus({ status }: { status: ConnectionStatus }) {
  const Icon = status === "Connected" ? Wifi : WifiOff;
  const color = status === "Connected" ? "text-[#22C55E]" : status === "Reconnecting" ? "text-[#F59E0B]" : "text-[#EF4444]";
  return (
    <span className={`inline-flex items-center gap-1.5 ${color}`}>
      <Icon className="size-4" />
      {status}
    </span>
  );
}

function HeaderStat({ label, value, tone }: { label: string; value: string; tone: "normal" | "warning" | "danger" }) {
  const valueColor = tone === "danger" ? "text-rose-300" : tone === "warning" ? "text-amber-300" : "text-foreground";
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className={`mt-2 text-3xl font-semibold ${valueColor}`}>{value}</p>
    </div>
  );
}

function PrimaryPanel({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={`rounded-xl border border-border bg-card/90 p-6 shadow-sm md:p-8 ${className}`}>
      {children}
    </div>
  );
}

function SectionHeading({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      {typeof count === "number" && <span className="text-sm text-muted-foreground">{count}</span>}
    </div>
  );
}

function HealthRing({ score }: { score: number }) {
  const normalized = Math.max(0, Math.min(100, score));
  const color = normalized >= 80 ? "#22C55E" : normalized >= 60 ? "#F59E0B" : "#EF4444";
  return (
    <div className="relative size-28">
      <svg className="-rotate-90" viewBox="0 0 112 112" aria-hidden="true">
        <circle cx="56" cy="56" r="44" fill="none" stroke="hsl(var(--border))" strokeWidth="10" />
        <circle
          cx="56"
          cy="56"
          r="44"
          fill="none"
          stroke={color}
          strokeLinecap="round"
          strokeWidth="10"
          strokeDasharray={276}
          strokeDashoffset={276 - (normalized / 100) * 276}
        />
      </svg>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function IncidentRow({ incident }: { incident: IncidentRow }) {
  return (
    <div className="grid gap-4 py-4 md:grid-cols-[1fr_auto] md:items-center">
      <div className="min-w-0">
        <p className="truncate text-base font-medium text-foreground">{incident.service_name}</p>
        <p className="mt-1 truncate text-sm text-muted-foreground">{incident.description}</p>
        <p className="mt-1 text-xs text-muted-foreground">{formatTimestamp(incident.timestamp)}</p>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={incident.severity === "critical" || incident.severity === "high" ? "danger" : "warning"} label={incident.severity} />
        <StatusBadge status="warning" label={incident.status} />
      </div>
    </div>
  );
}

function AlertLine({ alert }: { alert: AlertRow }) {
  return (
    <div className="grid gap-4 py-4 md:grid-cols-[96px_1fr_auto] md:items-center">
      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{alert.source}</span>
      <div className="min-w-0">
        <p className="truncate text-base font-medium text-foreground">{alert.name}</p>
        <p className="mt-1 truncate text-sm text-muted-foreground">{alert.detail}</p>
      </div>
      <StatusBadge status={alert.status === "warning" ? "warning" : "danger"} label={alert.status} />
    </div>
  );
}

function SummaryLine({ label, value, status }: { label: string; value: string; status: string }) {
  const healthy = status === "ok" || status === "healthy";
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={healthy ? "text-base font-semibold text-foreground" : "text-base font-semibold text-amber-300"}>{value}</span>
    </div>
  );
}

function EmptyLine({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 py-8">
      <Icon className="mt-0.5 size-5 text-emerald-300" />
      <div>
        <p className="text-base font-medium text-foreground">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
