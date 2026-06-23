export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export type SystemMetrics = {
  status?: string;
  cpu_percent?: number;
  ram_percent?: number;
  disk_percent?: number;
};

export type HealthScore = {
  score: number;
  status: string;
  indicator: string;
};

export type SystemHealthResponse = {
  timestamp: string;
  health_score: HealthScore;
  metrics: SystemMetrics;
  active_incident_count: number;
  running_container_count: number;
};

export type ContainerRow = {
  name: string;
  status: string;
  health_status: string;
  restart_count: number;
  last_check_timestamp: string;
  image?: string;
  cpu_percent?: number;
  memory_percent?: number;
};

export type ContainersResponse = {
  timestamp: string;
  containers: ContainerRow[];
  running_containers: unknown[];
  count: number;
};

export type IncidentRow = {
  incident_id: string;
  timestamp: string;
  severity: string;
  service_name: string;
  incident_type?: string;
  description?: string;
  status: string;
  incident_status?: string;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolved_timestamp?: string | null;
  resolution_notes?: string | null;
};

export type IncidentTransitionRow = {
  id: number;
  incident_id: string;
  timestamp: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  details: Record<string, unknown>;
};

export type IncidentDetailResponse = {
  incident: IncidentRow;
  timeline: IncidentTransitionRow[];
  count: number;
};

export type IncidentsResponse = {
  active_incidents: IncidentRow[];
  resolved_incidents: IncidentRow[];
  recent_incidents: IncidentRow[];
  incidents: IncidentRow[];
  active_count: number;
  resolved_count: number;
  count: number;
};

export type MetricTrend = {
  labels: string[];
  values: number[];
};

export type MetricsResponse = {
  timestamp: string;
  metrics: SystemMetrics;
  network: Record<string, unknown>;
  chart_data: {
    cpu?: MetricTrend;
    memory?: MetricTrend;
  };
};

export type RemediationRow = {
  timestamp: string;
  service_name: string;
  action: string;
  successful: boolean | null;
  incident_id?: string;
  source?: string;
};

export type RemediationsResponse = {
  actions: RemediationRow[];
  recent_remediations: RemediationRow[];
  count: number;
};

export type NotificationsResponse = {
  notification_stats: {
    email_count: number;
    slack_count: number;
    discord_count: number;
    failed_notifications: number;
  };
  notifications: Record<string, unknown>[];
  count: number;
};

export type HttpEndpointCheck = {
  name: string;
  url: string;
  timestamp: string;
  status: string;
  available: boolean;
  expected_status: number;
  status_code: number | null;
  latency_ms: number | null;
  error: string;
  availability_percent: number;
};

export type HttpMonitoringResponse = {
  status: string;
  timestamp: string;
  availability_percent: number;
  available_count: number;
  total_count: number;
  checks: HttpEndpointCheck[];
  error?: string;
};

export type SslCertificateCheck = {
  name: string;
  target: string;
  host: string;
  port: number;
  timestamp: string;
  status: string;
  valid: boolean;
  issuer: string;
  expires_at: string | null;
  days_remaining: number | null;
  warning_days: number;
  error: string;
};

export type SslMonitoringResponse = {
  status: string;
  timestamp: string;
  warning_count: number;
  total_count: number;
  checks: SslCertificateCheck[];
  error?: string;
};

export type TcpTargetCheck = {
  name: string;
  target: string;
  host: string;
  port: number;
  timestamp: string;
  status: string;
  reachable: boolean;
  latency_ms: number | null;
  error: string;
};

export type TcpMonitoringResponse = {
  status: string;
  timestamp: string;
  availability_percent: number;
  reachable_count: number;
  total_count: number;
  checks: TcpTargetCheck[];
  error?: string;
};

export type MonitoringTarget = {
  id: number;
  name: string;
  target_type: "http" | "tcp" | "ssl";
  address: string;
  expected_status: number | null;
  timeout_seconds: number;
  warning_days: number;
  is_active: boolean;
  last_error: string | null;
  last_status_code: number | null;
  last_response_time_ms: number | null;
  last_successful_check_at: string | null;
  created_at: string;
  updated_at: string;
  latest_result?: Record<string, unknown> | null;
  last_checked_at?: string | null;
};

export type CheckHistoryRow = {
  id: number;
  target_id: number;
  target_name: string;
  target_type: string;
  timestamp: string;
  status: string;
  latency_ms: number | null;
  details: Record<string, unknown>;
};

export type CheckHistoryResponse = {
  history: CheckHistoryRow[];
  count: number;
};

export type IntegrationRow = {
  name: string;
  status: string;
  description: string;
  url?: string;
  reachable?: boolean;
};

export type IntegrationsResponse = {
  integrations: IntegrationRow[];
};

export type MCPToolDescription = {
  name: string;
  description: string;
  example: string;
};

export type MCPResponse = {
  mcp_tools: MCPToolDescription[];
  claude_config: string;
};

export type MonitoringTargetsResponse = {
  targets: MonitoringTarget[];
  count: number;
};

export type MonitoringTargetPayload = {
  name: string;
  target_type: "http" | "tcp" | "ssl";
  address: string;
  expected_status?: number | null;
  timeout_seconds: number;
  warning_days: number;
  is_active: boolean;
};

export type DashboardSnapshot = {
  system: SystemHealthResponse;
  containers: ContainersResponse;
  incidents: IncidentsResponse;
  metrics: MetricsResponse;
  notifications: NotificationsResponse;
  remediations: RemediationsResponse;
  http_monitoring: HttpMonitoringResponse;
  ssl_monitoring: SslMonitoringResponse;
  tcp_monitoring: TcpMonitoringResponse;
};

export type DashboardRealtimeEventType =
  | "metric_update"
  | "incident_created"
  | "incident_resolved"
  | "remediation_executed"
  | "container_status_changed";

export type DashboardRealtimeEvent = {
  type: DashboardRealtimeEventType;
  timestamp: string;
  payload:
    | DashboardSnapshot
    | IncidentRow
    | RemediationRow
    | ContainerRow;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`AegisNex API ${path} returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getSystemHealth() {
  return fetchJson<SystemHealthResponse>("/api/system-health");
}

export function getContainers() {
  return fetchJson<ContainersResponse>("/api/containers");
}

export function getIncidents() {
  return fetchJson<IncidentsResponse>("/api/incidents");
}

export function getIncidentDetail(incidentId: string) {
  return fetchJson<IncidentDetailResponse>(`/api/incidents/${incidentId}`);
}

export async function acknowledgeIncident(incidentId: string) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/acknowledge`, "POST");
}

export async function resolveIncident(incidentId: string, resolutionNotes: string) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/resolve`, "POST", {
    resolution_notes: resolutionNotes,
  });
}

export function getMetrics() {
  return fetchJson<MetricsResponse>("/api/metrics");
}

export function getNotifications() {
  return fetchJson<NotificationsResponse>("/api/notifications");
}

export function getRemediations() {
  return fetchJson<RemediationsResponse>("/api/remediations");
}

export function getHttpMonitoring() {
  return fetchJson<HttpMonitoringResponse>("/api/http-monitoring");
}

export function getSslMonitoring() {
  return fetchJson<SslMonitoringResponse>("/api/ssl-monitoring");
}

export function getTcpMonitoring() {
  return fetchJson<TcpMonitoringResponse>("/api/tcp-monitoring");
}

export function getMonitoringTargets() {
  return fetchJson<MonitoringTargetsResponse>("/api/monitoring-targets");
}

export async function createMonitoringTarget(payload: MonitoringTargetPayload) {
  return writeJson<MonitoringTarget>("/api/monitoring-targets", "POST", payload);
}

export async function updateMonitoringTarget(id: number, payload: MonitoringTargetPayload) {
  return writeJson<MonitoringTarget>(`/api/monitoring-targets/${id}`, "PUT", payload);
}

export async function deleteMonitoringTarget(id: number) {
  return writeJson<{ status: string }>(`/api/monitoring-targets/${id}`, "DELETE");
}

export async function runMonitoringTarget(id: number) {
  return writeJson<Record<string, unknown>>(`/api/monitoring-targets/${id}/run`, "POST");
}

export function getMonitoringTargetHistory(id: number) {
  return fetchJson<CheckHistoryResponse>(`/api/monitoring-targets/${id}/history`);
}

async function writeJson<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  payload?: unknown,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    cache: "no-store",
    credentials: "include",
    headers: payload ? { "content-type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });

  if (!response.ok) {
    throw new Error(`AegisNex API ${path} returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getDashboardWebSocketUrl() {
  const configured = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (configured) return `${configured}/ws/dashboard`;

  const url = new URL(API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/dashboard";
  url.search = "";
  url.hash = "";
  return url.toString();
}

export function getIntegrations() {
  return fetchJson<IntegrationsResponse>("/api/integrations");
}

export function getMCPTools() {
  return fetchJson<MCPResponse>("/api/mcp");
}
