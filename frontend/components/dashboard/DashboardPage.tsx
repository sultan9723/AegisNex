"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, Brain, CheckCircle2,
  Container, Cpu, HardDrive, Network, PlugZap, Plus, Server, Shield,
  ShieldAlert, ShieldCheck, Wifi, WifiOff, XCircle, Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingState } from "@/components/common/LoadingState";
import { StatusBadge, type StatusState } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SkeletonDashboard } from "@/components/common/Skeleton";
import {
  getDashboardWebSocketUrl,
  getPlatformHealth,
  type ContainerRow,
  type DashboardRealtimeEvent,
  type DashboardSnapshot,
  type IncidentRow,
  type MetricsResponse,
  type PlatformHealth,
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

type ActivityItem = {
  id: string;
  type: "incident" | "remediation" | "container" | "alert";
  message: string;
  detail: string;
  timestamp: string;
  severity?: string;
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

function buildActivityFeed(data: DashboardData): ActivityItem[] {
  const items: ActivityItem[] = [];
  const added: Record<string, true> = {};

  for (const inc of data.incidents.recent_incidents.slice(0, 3)) {
    const key = `inc-${inc.incident_id}`;
    if (!added[key]) {
      added[key] = true;
      items.push({
        id: key, type: "incident", severity: inc.severity,
        message: `${inc.service_name}`,
        detail: inc.description ?? "",
        timestamp: inc.timestamp,
      });
    }
  }

  for (const rem of data.remediations.recent_remediations.slice(0, 3)) {
    const key = `rem-${rem.timestamp}-${rem.service_name}`;
    if (!added[key]) {
      added[key] = true;
      items.push({
        id: key, type: "remediation",
        message: `${rem.action} on ${rem.service_name}`,
        detail: rem.source ?? "",
        timestamp: rem.timestamp,
      });
    }
  }

  const alertItems = buildAlerts(data).slice(0, 3);
  for (const al of alertItems) {
    const key = `alt-${al.key}`;
    if (!added[key]) {
      added[key] = true;
      items.push({
        id: key, type: "alert",
        message: `${al.source}: ${al.name}`,
        detail: al.detail,
        timestamp: new Date().toISOString(),
        severity: al.status,
      });
    }
  }

  return items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 5);
}

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

function getTrendDirection(chartData: { labels?: string[]; values?: number[] } | undefined): "up" | "down" | "neutral" {
  if (!chartData?.values || chartData.values.length < 2) return "neutral";
  const last = chartData.values[chartData.values.length - 1];
  const prev = chartData.values[chartData.values.length - 2];
  if (last > prev) return "up";
  if (last < prev) return "down";
  return "neutral";
}

function getInfraStatus(healthScore: number): StatusState {
  return healthScore >= 80 ? "healthy" : healthScore >= 60 ? "warning" : "danger";
}

function formatBytes(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatNetworkTotal(metrics: DashboardData["metrics"]["metrics"]): string {
  const sent = metrics.network_bytes_sent;
  const recv = metrics.network_bytes_recv;
  if (sent === undefined && recv === undefined) return "—";
  const total = (sent ?? 0) + (recv ?? 0);
  return formatBytes(total);
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("Disconnected");
  const [platformHealth, setPlatformHealth] = useState<PlatformHealth | null>(null);
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

  const loadPlatformHealth = useCallback(async () => {
    try {
      const res = await getPlatformHealth();
      setPlatformHealth(res.platform_health);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    const healthTimeout = window.setTimeout(() => void loadPlatformHealth(), 0);
    return () => { window.clearTimeout(timeout); window.clearTimeout(healthTimeout); };
  }, [load, loadPlatformHealth]);

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
  const activityFeed = useMemo(() => (data ? buildActivityFeed(data) : []), [data]);

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
  const criticalIncidents = activeIncidents.filter((i) => i.severity === "critical" || i.severity === "high");
  const health = data.system.health_score;
  const healthStatus = statusFromHealth(health.score);
  const running = data.system.running_container_count;
  const totalContainers = data.containers.count;
  const metrics = data.metrics.metrics;

  const cpuTrend = getTrendDirection(data.metrics.chart_data.cpu);
  const memTrend = getTrendDirection(data.metrics.chart_data.memory);
  const diskTrend = getTrendDirection(data.metrics.chart_data.disk);

  const infraStatus = getInfraStatus(health.score);

  const recommendation = activeIncidents.length === 0
    ? "All systems operational. No incidents to address."
    : `Active incidents on ${Array.from(new Set(activeIncidents.map(i => i.service_name))).join(", ")}. Prioritize investigation.`;

  const sslWarnings = data.ssl_monitoring.warning_count;
  const httpDown = data.http_monitoring.checks.filter(c => !c.available).length;
  const tcpDown = data.tcp_monitoring.checks.filter(c => !c.reachable).length;

  const topRisk = sslWarnings > 0
    ? `${sslWarnings} SSL certificate${sslWarnings > 1 ? "s" : ""} approaching expiration.`
    : httpDown > 0
      ? `${httpDown} HTTP endpoint${httpDown > 1 ? "s" : ""} currently unreachable.`
      : tcpDown > 0
        ? `${tcpDown} TCP service${tcpDown > 1 ? "s" : ""} not reachable.`
        : health.score < 80
          ? `Platform health score at ${health.score}% — below threshold.`
          : "No significant risks detected. All services healthy.";

  const nextAction = activeIncidents.length > 0
    ? "Open incident response workflow to address active issues."
    : sslWarnings > 0
      ? "Review and renew expiring SSL certificates."
      : httpDown > 0 || tcpDown > 0
        ? "Investigate unreachable endpoints and restore connectivity."
        : "Run a routine health check across all targets.";

  return (
    <ErrorBoundary>
    <div className="space-y-8 animate-fade-in-up">

      {/* ── Platform Health Bar ── */}
      <div className="flex items-center gap-3 text-xs text-text-secondary mb-1">
        <ShieldCheck className="size-4 text-primary" />
        <span>Platform Overview</span>
        <ConnectionIndicator status={connectionStatus} />
      </div>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <PlatformHealthCard
          icon={Shield}
          label="Health Score"
          value={`${health.score}`}
          status={healthStatus}
        />
        <PlatformHealthCard
          icon={ShieldAlert}
          label="Critical Incidents"
          value={`${criticalIncidents.length}`}
          status={criticalIncidents.length > 0 ? "danger" : "healthy"}
        />
        <PlatformHealthCard
          icon={Container}
          label="Running Containers"
          value={`${running}`}
          status={running > 0 ? "healthy" : "warning"}
        />
        <PlatformHealthCard
          icon={Server}
          label="Infrastructure"
          value={health.status || "Normal"}
          status={infraStatus}
        />
        <PlatformHealthCard
          icon={BookOpen}
          label="Knowledge Base"
          value="Connected"
          status="healthy"
        />
        <PlatformHealthCard
          icon={Brain}
          label="AI Copilot"
          value="Active"
          status="healthy"
        />
      </div>

      {/* ── Platform Health Status ── */}
      <PlatformHealthBanner health={platformHealth} />

      {/* ── AI Insights + System Metrics ── */}
      <div className="grid gap-5 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <AIPanel
            recommendation={recommendation}
            topRisk={topRisk}
            nextAction={nextAction}
          />
        </div>
        <div className="lg:col-span-7">
          <div className="grid grid-cols-2 gap-3">
            <CompactMetricCard
              icon={Cpu}
              label="CPU"
              value={pct(metrics.cpu_percent)}
              trend={cpuTrend}
              progress={metrics.cpu_percent}
              color="hsl(var(--chart-1))"
            />
            <CompactMetricCard
              icon={Activity}
              label="Memory"
              value={pct(metrics.ram_percent)}
              trend={memTrend}
              progress={metrics.ram_percent}
              color="hsl(var(--chart-2))"
            />
            <CompactMetricCard
              icon={HardDrive}
              label="Disk"
              value={pct(metrics.disk_percent)}
              trend={diskTrend}
              progress={metrics.disk_percent}
              color="hsl(var(--chart-3))"
            />
            <CompactMetricCard
              icon={Network}
              label="Network"
              value={formatNetworkTotal(metrics)}
              trend="neutral"
              color="hsl(var(--chart-4))"
            />
          </div>
        </div>
      </div>

      {/* ── Incidents + Activity ── */}
      <div className="grid gap-5 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <IncidentsPanel incidents={activeIncidents} />
        </div>
        <div className="lg:col-span-7">
          <ActivityPanel items={activityFeed} />
        </div>
      </div>

      {/* ── Quick Actions ── */}
      <div>
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Quick Actions</p>
        <div className="grid grid-cols-5 gap-3">
          <QuickAction icon={Brain} label="AI Assistant" href="/ai" />
          <QuickAction icon={Plus} label="Add Target" href="/targets" />
          <QuickAction icon={BookOpen} label="Knowledge" href="/knowledge" />
          <QuickAction icon={Activity} label="Reports" href="/reports" />
          <QuickAction icon={Container} label="Containers" href="/containers" />
        </div>
      </div>
    </div>
    </ErrorBoundary>
  );
}

/* ── Internal Presentational Components ── */

function PlatformHealthBanner({ health }: { health: PlatformHealth | null }) {
  if (!health) return null;
  const statusConfig = health.status === "healthy"
    ? { icon: CheckCircle2, label: "Platform Healthy", color: "text-success", bg: "bg-success/10", border: "border-success/20" }
    : health.status === "degraded"
      ? { icon: AlertTriangle, label: "Platform Degraded", color: "text-warning", bg: "bg-warning/10", border: "border-warning/20" }
      : { icon: XCircle, label: "Platform Critical", color: "text-danger", bg: "bg-danger/10", border: "border-danger/20" };
  const StatusIcon = statusConfig.icon;
  return (
    <div className={`flex items-center justify-between rounded-xl border ${statusConfig.border} ${statusConfig.bg} px-4 py-3`}>
      <div className="flex items-center gap-3">
        <StatusIcon className={`size-5 ${statusConfig.color}`} />
        <span className={`text-sm font-semibold ${statusConfig.color}`}>{statusConfig.label}</span>
      </div>
      <div className="flex items-center gap-5 text-xs text-text-secondary">
        <span>Core Services <strong className="text-text-primary">{health.required_healthy}/{health.required_total}</strong> Healthy</span>
        <span>Optional Integrations <strong className="text-text-primary">{health.optional_configured}/{health.optional_total}</strong> Configured</span>
      </div>
    </div>
  );
}

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

function PlatformHealthCard({ icon: Icon, label, value, status }: { icon: LucideIcon; label: string; value: string; status: StatusState }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-surface-elevated/40 px-4 py-3.5 transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/60">
      <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
        <Icon className="size-3.5 text-text-secondary" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</p>
        <div className="mt-0.5">
          <StatusBadge status={status} label={value} />
        </div>
      </div>
    </div>
  );
}

function AIPanel({ recommendation, topRisk, nextAction }: { recommendation: string; topRisk: string; nextAction: string }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/50 p-5 shadow-sm transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/70">
      <div className="flex items-center gap-3 mb-4">
        <div className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
          <Brain className="size-4" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text-primary">AI Insights</h3>
          <p className="text-[11px] text-text-tertiary">Real-time platform analysis</p>
        </div>
      </div>
      <div className="space-y-3">
        <InsightRow icon={Zap} label="Recommendation" value={recommendation} color="text-primary" />
        <InsightRow icon={AlertTriangle} label="Top Risk" value={topRisk} color="text-warning" />
        <InsightRow icon={ArrowRight} label="Next Action" value={nextAction} color="text-info" />
      </div>
      <Link href="/ai" tabIndex={-1}>
        <Button variant="outline" size="sm" className="mt-4 w-full">
          <Brain className="size-3.5" />
          Open AI Workspace
        </Button>
      </Link>
    </div>
  );
}

function InsightRow({ icon: Icon, label, value, color }: { icon: LucideIcon; label: string; value: string; color: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-md ${color.replace("text-", "bg-")}/10 ${color}`}>
        <Icon className="size-3" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium text-text-tertiary">{label}</p>
        <p className="text-[13px] leading-relaxed text-text-primary">{value}</p>
      </div>
    </div>
  );
}

function CompactMetricCard({ icon: Icon, label, value, trend, progress, color }: { icon: LucideIcon; label: string; value: string; trend?: "up" | "down" | "neutral"; progress?: number; color: string }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-4 shadow-sm transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/60 hover:shadow-md">
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 place-items-center rounded-lg" style={{ backgroundColor: `${color}15`, color }}>
            <Icon className="size-3.5" />
          </div>
          <span className="text-[11px] font-medium text-text-tertiary">{label}</span>
        </div>
        {trend && trend !== "neutral" && (
          <span className={cn("text-xs font-semibold", trend === "up" ? "text-success" : "text-danger")}>
            {trend === "up" ? "↑" : "↓"}
          </span>
        )}
      </div>
      <div className="flex items-end justify-between">
        <span className="text-2xl font-semibold tracking-tight text-text-primary">{value}</span>
      </div>
      {typeof progress === "number" && (
        <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.max(0, Math.min(100, progress))}%`, backgroundColor: color }}
          />
        </div>
      )}
    </div>
  );
}

function IncidentsPanel({ incidents }: { incidents: IncidentRow[] }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/50 p-5 shadow-sm transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/70">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-4 text-danger" />
          <h3 className="text-sm font-semibold text-text-primary">Active Incidents</h3>
          {incidents.length > 0 && (
            <Badge variant="danger-subtle" size="sm">{incidents.length}</Badge>
          )}
        </div>
        <Link href="/incidents" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1 transition-colors">
          View All <ArrowRight className="size-3" />
        </Link>
      </div>
      {incidents.length === 0 ? (
        <div className="flex items-center gap-3 py-4">
          <div className="grid size-8 place-items-center rounded-lg bg-success/10 text-success">
            <CheckCircle2 className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">All clear</p>
            <p className="text-xs text-text-secondary mt-0.5">No active incidents across any services.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-0.5">
          {incidents.slice(0, 5).map((incident) => (
            <IncidentRowItem key={incident.incident_id} incident={incident} />
          ))}
        </div>
      )}
    </div>
  );
}

function IncidentRowItem({ incident }: { incident: IncidentRow }) {
  const isCritical = incident.severity === "critical" || incident.severity === "high";
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150 hover:bg-surface-elevated/80">
      <div className="flex items-start gap-3 min-w-0">
        <div className={cn("mt-1.5 size-2 shrink-0 rounded-full", isCritical ? "bg-danger" : "bg-warning")} />
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-text-primary">{incident.service_name}</p>
          <p className="truncate text-[11px] text-text-tertiary mt-0.5">{formatTimestamp(incident.timestamp)}</p>
        </div>
      </div>
      <Badge
        variant={isCritical ? "danger-subtle" : "warning-subtle"}
        size="sm"
        dot={isCritical}
        pulse={isCritical}
      >
        {incident.severity}
      </Badge>
    </div>
  );
}

function ActivityPanel({ items }: { items: ActivityItem[] }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/50 p-5 shadow-sm transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/70">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="size-4 text-text-secondary" />
        <h3 className="text-sm font-semibold text-text-primary">Recent Activity</h3>
      </div>
      {items.length === 0 ? (
        <div className="flex items-center gap-3 py-4">
          <div className="grid size-8 place-items-center rounded-lg bg-text-tertiary/10 text-text-tertiary">
            <Activity className="size-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">No recent activity</p>
            <p className="text-xs text-text-secondary mt-0.5">Activity will appear as events occur.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-0">
          {items.map((item) => (
            <ActivityLine key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityLine({ item }: { item: ActivityItem }) {
  const colorMap: Record<string, string> = {
    incident: "text-danger",
    remediation: "text-info",
    container: "text-primary",
    alert: "text-warning",
  };
  const bgMap: Record<string, string> = {
    incident: "bg-danger/10",
    remediation: "bg-info/10",
    container: "bg-primary/10",
    alert: "bg-warning/10",
  };
  const iconMap: Record<string, LucideIcon> = {
    incident: ShieldAlert,
    remediation: Zap,
    container: Container,
    alert: AlertTriangle,
  };
  const Icon = iconMap[item.type] ?? Activity;
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border/20 last:border-0">
      <div className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg", bgMap[item.type] ?? "bg-surface-elevated", colorMap[item.type] ?? "text-text-tertiary")}>
        <Icon className="size-3" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-text-primary">{item.message}</p>
        <p className="text-[11px] text-text-tertiary mt-0.5 line-clamp-1">{item.detail}</p>
      </div>
      <span className="shrink-0 text-[11px] text-text-tertiary pt-0.5">{formatTimestamp(item.timestamp)}</span>
    </div>
  );
}

const QUICK_ACTION_ITEMS = [
  { icon: Brain, label: "AI Assistant", href: "/ai" },
  { icon: Plus, label: "Add Target", href: "/targets" },
  { icon: BookOpen, label: "Knowledge", href: "/knowledge" },
  { icon: Activity, label: "Reports", href: "/reports" },
  { icon: Container, label: "Containers", href: "/containers" },
];

function QuickAction({ icon: Icon, label, href }: { icon: LucideIcon; label: string; href: string }) {
  return (
    <Link
      href={href}
      className="flex flex-col items-center gap-2 rounded-xl border border-border/40 bg-surface-elevated/40 px-3 py-4 text-center transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/60 hover:shadow-md active:scale-[0.98]"
    >
      <div className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
        <Icon className="size-4" />
      </div>
      <span className="text-[11px] font-medium text-text-secondary leading-tight">{label}</span>
    </Link>
  );
}
