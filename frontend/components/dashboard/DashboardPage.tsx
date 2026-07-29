"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, Brain, CheckCircle2,
  Container, Cpu, HardDrive, Network, PlugZap, Plus, Server, Shield,
  ShieldAlert, ShieldCheck, Wifi, WifiOff, XCircle, Zap, Bot,
  TrendingUp, TrendingDown, Minus, ChevronRight, Clock, Globe,
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
  type: "incident" | "remediation" | "container" | "alert" | "agent";
  message: string;
  detail: string;
  timestamp: string;
  severity?: string;
};

const relative = (ts: string): string => {
  const diff = Date.now() - new Date(ts.replace("Z", "+00:00")).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
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

  const agentActivity = data.agent_activity?.recent_actions ?? [];
  for (const action of agentActivity.slice(0, 3)) {
    const key = `agent-${action.action_id}`;
    if (!added[key]) {
      added[key] = true;
      items.push({
        id: key, type: "agent",
        message: `${action.agent_id}: ${action.action_summary}`,
        detail: action.reasoning || action.action_type,
        timestamp: action.created_at,
        severity: action.policy_verdict === "denied" ? "warning" : "info",
      });
    }
  }

  return items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 10);
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

function formatBytes(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null) return "\u2014";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatNetworkTotal(metrics: DashboardData["metrics"]["metrics"]): string {
  const sent = metrics.network_bytes_sent;
  const recv = metrics.network_bytes_recv;
  if (sent === undefined && recv === undefined) return "\u2014";
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
      if (event.type === "agent_activity") {
        setData((current) => {
          if (!current) return current;
          return {
            ...current,
            agent_activity: event.payload as DashboardData["agent_activity"],
          };
        });
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

  const sslWarnings = data.ssl_monitoring.warning_count;
  const httpDown = data.http_monitoring.checks.filter(c => !c.available).length;
  const tcpDown = data.tcp_monitoring.checks.filter(c => !c.reachable).length;

  const recommendation = activeIncidents.length === 0
    ? "All systems operational. No incidents to address."
    : `Active incidents on ${Array.from(new Set(activeIncidents.map(i => i.service_name))).join(", ")}. Prioritize investigation.`;

  const topRisk = sslWarnings > 0
    ? `${sslWarnings} SSL certificate${sslWarnings > 1 ? "s" : ""} approaching expiration.`
    : httpDown > 0
      ? `${httpDown} HTTP endpoint${httpDown > 1 ? "s" : ""} currently unreachable.`
      : tcpDown > 0
        ? `${tcpDown} TCP service${tcpDown > 1 ? "s" : ""} not reachable.`
        : health.score < 80
          ? `Platform health score at ${health.score}% \u2014 below threshold.`
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
      <div className="space-y-6 animate-fade-in-up">

        {/* Hero health strip */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-bold text-text-primary">Command Center</h1>
              <ConnectionIndicator status={connectionStatus} />
            </div>
            <p className="mt-0.5 text-xs text-text-tertiary">
              Real-time platform overview
            </p>
          </div>
          <div className="flex items-center gap-2">
            <PlatformHealthBannerInline health={platformHealth} />
          </div>
        </div>

        {/* Key metrics strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <MetricPill
            icon={Shield}
            label="Health"
            value={`${health.score}`}
            suffix="%"
            status={healthStatus}
          />
          <MetricPill
            icon={ShieldAlert}
            label="Active Incidents"
            value={`${activeIncidents.length}`}
            status={activeIncidents.length > 0 ? (criticalIncidents.length > 0 ? "danger" : "warning") : "healthy"}
          />
          <MetricPill
            icon={Container}
            label="Containers"
            value={`${running}/${totalContainers}`}
            status={running > 0 ? "healthy" : "warning"}
          />
          <MetricPill
            icon={Cpu}
            label="CPU"
            value={pct(metrics.cpu_percent)}
            trend={cpuTrend}
            status={(metrics.cpu_percent ?? 0) > 90 ? "danger" : (metrics.cpu_percent ?? 0) > 70 ? "warning" : "healthy"}
          />
          <MetricPill
            icon={Activity}
            label="Memory"
            value={pct(metrics.ram_percent)}
            trend={memTrend}
            status={(metrics.ram_percent ?? 0) > 90 ? "danger" : (metrics.ram_percent ?? 0) > 70 ? "warning" : "healthy"}
          />
          <MetricPill
            icon={HardDrive}
            label="Disk"
            value={pct(metrics.disk_percent)}
            trend={diskTrend}
            status={(metrics.disk_percent ?? 0) > 90 ? "danger" : (metrics.disk_percent ?? 0) > 70 ? "warning" : "healthy"}
          />
        </div>

        {/* Main grid: AI + Metrics + Incidents */}
        <div className="grid gap-4 lg:grid-cols-12">

          {/* AI Recommendations panel */}
          <div className="lg:col-span-4">
            <PanelCard className="h-full">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary">
                  <Brain className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">AI Insights</h3>
                  <p className="text-[11px] text-text-tertiary">Automated analysis</p>
                </div>
              </div>
              <div className="space-y-3">
                <InsightPill icon={Zap} label="Recommendation" value={recommendation} color="primary" />
                <InsightPill icon={AlertTriangle} label="Top Risk" value={topRisk} color="warning" />
                <InsightPill icon={ArrowRight} label="Next Action" value={nextAction} color="info" />
              </div>
              <Link href="/ai" className="mt-4 block">
                <Button variant="outline" size="sm" className="w-full">
                  <Sparkles className="size-3.5" />
                  Open AI Workspace
                </Button>
              </Link>
            </PanelCard>
          </div>

          {/* System metrics */}
          <div className="lg:col-span-4">
            <PanelCard className="h-full">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="grid size-8 place-items-center rounded-lg bg-violet-500/10 text-violet-400">
                  <Activity className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">System Metrics</h3>
                  <p className="text-[11px] text-text-tertiary">Live resource utilization</p>
                </div>
              </div>
              <div className="space-y-3">
                <MetricBar icon={Cpu} label="CPU" value={metrics.cpu_percent ?? 0} color="hsl(186 100% 50%)" trend={cpuTrend} />
                <MetricBar icon={Activity} label="Memory" value={metrics.ram_percent ?? 0} color="hsl(161 100% 45%)" trend={memTrend} />
                <MetricBar icon={HardDrive} label="Disk" value={metrics.disk_percent ?? 0} color="hsl(180 85% 60%)" trend={diskTrend} />
                <div className="flex items-center justify-between pt-1 border-t border-border/20">
                  <div className="flex items-center gap-2">
                    <Network className="size-3.5 text-text-tertiary" />
                    <span className="text-[11px] text-text-secondary">Network I/O</span>
                  </div>
                  <span className="text-xs font-semibold text-text-primary">{formatNetworkTotal(metrics)}</span>
                </div>
              </div>
            </PanelCard>
          </div>

          {/* Active Incidents */}
          <div className="lg:col-span-4">
            <PanelCard className="h-full">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="grid size-8 place-items-center rounded-lg bg-danger/10 text-danger">
                    <ShieldAlert className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">Incidents</h3>
                    <p className="text-[11px] text-text-tertiary">Active issues</p>
                  </div>
                </div>
                {activeIncidents.length > 0 && (
                  <Badge variant="danger-subtle" size="sm" pulse>{activeIncidents.length}</Badge>
                )}
              </div>
              {activeIncidents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <div className="grid size-10 place-items-center rounded-full bg-success/10 text-success mb-2">
                    <CheckCircle2 className="size-5" />
                  </div>
                  <p className="text-sm font-medium text-text-primary">All clear</p>
                  <p className="text-[11px] text-text-tertiary mt-0.5">No active incidents</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {activeIncidents.slice(0, 4).map((incident) => (
                    <IncidentRowCompact key={incident.incident_id} incident={incident} />
                  ))}
                  {activeIncidents.length > 4 && (
                    <Link href="/incidents" className="flex items-center gap-1 pt-2 text-[11px] font-medium text-primary hover:underline">
                      <ChevronRight className="size-3" />
                      View all {activeIncidents.length} incidents
                    </Link>
                  )}
                </div>
              )}
            </PanelCard>
          </div>
        </div>

        {/* Bottom row: Activity + Quick Actions */}
        <div className="grid gap-4 lg:grid-cols-12">

          {/* Activity feed */}
          <div className="lg:col-span-8">
            <PanelCard>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="grid size-8 place-items-center rounded-lg bg-cyan-500/10 text-cyan-400">
                    <Clock className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">Recent Activity</h3>
                    <p className="text-[11px] text-text-tertiary">Latest events across the platform</p>
                  </div>
                </div>
              </div>
              {activityFeed.length === 0 ? (
                <div className="flex items-center gap-3 py-6">
                  <p className="text-xs text-text-tertiary">No recent activity</p>
                </div>
              ) : (
                <div className="space-y-0">
                  {activityFeed.map((item) => (
                    <ActivityRow key={item.id} item={item} />
                  ))}
                </div>
              )}
            </PanelCard>
          </div>

          {/* Quick Actions */}
          <div className="lg:col-span-4">
            <PanelCard className="h-full">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="grid size-8 place-items-center rounded-lg bg-amber-500/10 text-amber-400">
                  <Plus className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Quick Actions</h3>
                  <p className="text-[11px] text-text-tertiary">Jump to common tasks</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <QuickActionCard icon={Brain} label="AI Assistant" href="/ai" />
                <QuickActionCard icon={Plus} label="Add Target" href="/targets" />
                <QuickActionCard icon={BookOpen} label="Knowledge" href="/infrastructure" />
                <QuickActionCard icon={Activity} label="Reports" href="/reports" />
                <QuickActionCard icon={Container} label="Containers" href="/containers" />
                <QuickActionCard icon={PlugZap} label="Integrations" href="/integrations" />
              </div>
            </PanelCard>
          </div>
        </div>

        {/* Agent Activity Row */}
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-12">
            <PanelCard>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="grid size-8 place-items-center rounded-lg bg-emerald-500/10 text-emerald-400">
                    <Bot className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">Agent Activity</h3>
                    <p className="text-[11px] text-text-tertiary">Recent actions from AI agents</p>
                  </div>
                </div>
                <Link href="/governance" className="text-[11px] font-medium text-primary hover:underline flex items-center gap-1">
                  View All <ChevronRight className="size-3" />
                </Link>
              </div>
              {(data.agent_activity?.recent_actions ?? []).length === 0 ? (
                <div className="flex items-center gap-3 py-4">
                  <Bot className="size-4 text-text-tertiary" />
                  <p className="text-xs text-text-tertiary">No recent agent activity</p>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {(data.agent_activity?.recent_actions ?? []).slice(0, 6).map((action) => (
                    <div key={action.action_id} className="flex items-start gap-3 rounded-lg border border-border/30 bg-surface-elevated/30 p-3">
                      <div className="mt-0.5 size-2 shrink-0 rounded-full bg-emerald-400" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-text-primary truncate">{action.agent_id}</p>
                        <p className="text-[10px] text-text-secondary mt-0.5 line-clamp-2">{action.action_summary}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge variant={action.policy_verdict === "denied" ? "danger-subtle" : action.policy_verdict === "pending_approval" ? "warning-subtle" : "success-subtle"} size="sm">
                            {action.policy_verdict}
                          </Badge>
                          <span className="text-[9px] text-text-tertiary">{relative(action.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {data.agent_activity?.stats && (
                <div className="flex items-center gap-4 mt-3 pt-3 border-t border-border/20">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-text-tertiary">Total Actions:</span>
                    <span className="text-xs font-semibold text-text-primary">{data.agent_activity.stats.total_actions}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-text-tertiary">Success Rate:</span>
                    <span className="text-xs font-semibold text-text-primary">{(data.agent_activity.stats.success_rate * 100).toFixed(0)}%</span>
                  </div>
                  {data.agent_activity.stats.pending_approvals > 0 && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-text-tertiary">Pending Approvals:</span>
                      <Badge variant="warning-subtle" size="sm">{data.agent_activity.stats.pending_approvals}</Badge>
                    </div>
                  )}
                </div>
              )}
            </PanelCard>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}

/* ── Presentational components ── */

function PanelCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn(
      "rounded-xl border border-border/40 bg-surface-elevated/40 p-5 shadow-sm transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/55",
      className,
    )}>
      {children}
    </div>
  );
}

function MetricPill({
  icon: Icon, label, value, suffix, trend, status,
}: {
  icon: LucideIcon; label: string; value: string; suffix?: string;
  trend?: "up" | "down" | "neutral"; status: StatusState;
}) {
  const statusColor = status === "healthy" ? "text-success" : status === "warning" ? "text-warning" : "text-danger";
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-surface-elevated/40 px-3.5 py-3 transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/55">
      <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
        <Icon className={cn("size-3.5", statusColor)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</p>
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-text-primary">{value}{suffix}</span>
          {trend && trend !== "neutral" && (
            <span className={cn("text-[10px] font-bold", trend === "up" ? "text-danger" : "text-success")}>
              {trend === "up" ? "\u2191" : "\u2193"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricBar({
  icon: Icon, label, value, color, trend,
}: {
  icon: LucideIcon; label: string; value: number; color: string;
  trend?: "up" | "down" | "neutral";
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="size-3.5 text-text-tertiary" />
          <span className="text-[11px] font-medium text-text-secondary">{label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-text-primary">{pct(value)}</span>
          {trend && trend !== "neutral" && (
            <span className={cn("text-[10px] font-bold", trend === "up" ? "text-danger" : "text-success")}>
              {trend === "up" ? "\u2191" : "\u2193"}
            </span>
          )}
        </div>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function InsightPill({
  icon: Icon, label, value, color,
}: {
  icon: LucideIcon; label: string; value: string; color: "primary" | "warning" | "info";
}) {
  const colorMap = {
    primary: "bg-primary/10 text-primary",
    warning: "bg-warning/10 text-warning",
    info: "bg-info/10 text-info",
  };
  return (
    <div className="rounded-lg border border-border/20 bg-surface/40 p-3">
      <div className="flex items-center gap-2 mb-1">
        <div className={cn("grid size-5 place-items-center rounded", colorMap[color])}>
          <Icon className="size-2.5" />
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">{label}</span>
      </div>
      <p className="text-[12px] leading-relaxed text-text-primary pl-7">{value}</p>
    </div>
  );
}

function IncidentRowCompact({ incident }: { incident: IncidentRow }) {
  const isCritical = incident.severity === "critical" || incident.severity === "high";
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 transition-colors hover:bg-surface-elevated/60">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className={cn("size-1.5 shrink-0 rounded-full", isCritical ? "bg-danger animate-pulse" : "bg-warning")} />
        <div className="min-w-0">
          <p className="truncate text-[12px] font-medium text-text-primary">{incident.service_name}</p>
          <p className="truncate text-[10px] text-text-tertiary">{formatTimestamp(incident.timestamp)}</p>
        </div>
      </div>
      <Badge variant={isCritical ? "danger-subtle" : "warning-subtle"} size="sm">
        {incident.severity}
      </Badge>
    </div>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const config: Record<string, { icon: LucideIcon; bg: string; color: string }> = {
    incident: { icon: ShieldAlert, bg: "bg-danger/10", color: "text-danger" },
    remediation: { icon: Zap, bg: "bg-info/10", color: "text-info" },
    container: { icon: Container, bg: "bg-primary/10", color: "text-primary" },
    alert: { icon: AlertTriangle, bg: "bg-warning/10", color: "text-warning" },
  };
  const c = config[item.type] ?? { icon: Activity, bg: "bg-surface-elevated", color: "text-text-tertiary" };
  const Icon = c.icon;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/15 last:border-0">
      <div className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg", c.bg, c.color)}>
        <Icon className="size-3" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-medium text-text-primary">{item.message}</p>
        <p className="text-[11px] text-text-tertiary mt-0.5 line-clamp-1">{item.detail}</p>
      </div>
      <span className="shrink-0 text-[10px] text-text-tertiary pt-0.5 whitespace-nowrap">{formatTimestamp(item.timestamp)}</span>
    </div>
  );
}

function QuickActionCard({ icon: Icon, label, href }: { icon: LucideIcon; label: string; href: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 rounded-lg border border-border/30 bg-surface/40 px-3 py-2.5 text-left transition-all duration-200 hover:border-border/50 hover:bg-surface-elevated/50 active:scale-[0.98]"
    >
      <Icon className="size-3.5 text-primary" />
      <span className="text-[11px] font-medium text-text-secondary">{label}</span>
    </Link>
  );
}

function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  const Icon = status === "Connected" ? Wifi : WifiOff;
  const color = status === "Connected" ? "text-success" : status === "Reconnecting" ? "text-warning" : "text-danger";
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-semibold", color)}>
      <Icon className="size-3" />
      {status}
    </span>
  );
}

function PlatformHealthBannerInline({ health }: { health: PlatformHealth | null }) {
  if (!health) return null;
  const config = health.status === "healthy"
    ? { icon: CheckCircle2, label: "Healthy", color: "text-success", bg: "bg-success/8 border-success/20" }
    : health.status === "degraded"
      ? { icon: AlertTriangle, label: "Degraded", color: "text-warning", bg: "bg-warning/8 border-warning/20" }
      : { icon: XCircle, label: "Critical", color: "text-danger", bg: "bg-danger/8 border-danger/20" };
  const StatusIcon = config.icon;
  return (
    <div className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium", config.bg, config.color)}>
      <StatusIcon className="size-3" />
      {config.label}
      <span className="text-text-tertiary">
        {health.required_healthy}/{health.required_total}
      </span>
    </div>
  );
}

function Sparkles(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
      <path d="M20 3v4" /><path d="M22 5h-4" />
    </svg>
  );
}
