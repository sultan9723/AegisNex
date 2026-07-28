import { getAccessToken, setAccessToken } from "./auth";

function normalizeApiBaseUrl(value: string | undefined): string {
  const base = (value || "").replace(/\/$/, "");
  if (!base) return "";
  return base.endsWith("/api") ? base.slice(0, -4) : base;
}

export const API_BASE_URL = normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_URL);

function normalizeApiPath(path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  if (cleanPath === "/api" || cleanPath.startsWith("/api/")) {
    return cleanPath;
  }
  return `/api${cleanPath}`;
}

export function buildApiUrl(path: string): string {
  const base = API_BASE_URL;
  const apiPath = normalizeApiPath(path);
  return base ? `${base}${apiPath}` : apiPath;
}

export function buildWebSocketUrl(path: string): string {
  const token = getAccessToken();
  const configured = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (configured) return `${configured}${path}${token ? `?token=${encodeURIComponent(token)}` : ""}`;

  if (API_BASE_URL.startsWith("http")) {
    try {
      const url = new URL(API_BASE_URL);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = path;
      url.search = "";
      url.hash = "";
      if (token) url.searchParams.set("token", token);
      return url.toString();
    } catch {
      // Fall through to window.location fallback
    }
  }

  if (typeof window === "undefined") return "";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export const DEFAULT_TIMEOUT_MS = 15_000;
export const MAX_RETRIES = 2;

export type SystemMetrics = {
  status?: string;
  cpu_percent?: number;
  cpu_load_1m?: number | null;
  cpu_load_5m?: number | null;
  cpu_load_15m?: number | null;
  ram_percent?: number;
  ram_used_gb?: number;
  ram_total_gb?: number;
  disk_percent?: number;
  disk_free_gb?: number;
  disk_total_gb?: number;
  network_bytes_sent?: number;
  network_bytes_recv?: number;
  uptime_seconds?: number;
  process_count?: number;
  warnings?: string[];
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

export type ContainerPort = {
  container_port: string;
  host_port: string | null;
  host_ip: string | null;
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
  started_at?: string | null;
  ports?: ContainerPort[];
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
  org_id?: number | null;
  org_name?: string | null;
  status: string;
  incident_status?: string;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolved_timestamp?: string | null;
  resolution_notes?: string | null;
  proposed_remediation?: Record<string, unknown> | null;
  remediation_proposed_by?: string | null;
  remediation_proposed_at?: string | null;
  remediation_approval_status?: string | null;
  remediation_plan_confidence?: number | null;
  remediation_history?: Array<Record<string, unknown>> | null;
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

export type IncidentAnalysis = {
  summary?: string;
  severity_assessment?: string;
  suggested_remediation?: string;
  root_cause?: string;
  impact_assessment?: string;
  confidence?: number;
};

export type IncidentDetailResponse = {
  incident: IncidentRow;
  timeline: IncidentTransitionRow[];
  transitions?: IncidentTransitionRow[];
  count: number;
  analysis?: IncidentAnalysis;
  description?: string;
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
    disk?: MetricTrend;
    labels?: string[];
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

export type IntegrationHealth = "healthy" | "warning" | "offline" | "unknown";

export type PlatformHealth = {
  status: "healthy" | "degraded" | "critical";
  required_healthy: number;
  required_total: number;
  optional_configured: number;
  optional_total: number;
};

export type IntegrationStatusRow = {
  id: string;
  name: string;
  category: string;
  description: string;
  health: IntegrationHealth;
  status: string;
  message: string;
  details: Record<string, string | number | boolean | null>;
  last_verification: string;
  configure_href: string;
  testable: boolean;
  configurable: boolean;
  required: boolean;
};

export type IntegrationStatusCategory = {
  name: string;
  count: number;
  integrations: IntegrationStatusRow[];
};

export type IntegrationStatusResponse = {
  categories: IntegrationStatusCategory[];
  integrations: IntegrationStatusRow[];
  configured_count: number;
  count: number;
  timestamp: string;
  platform_health: PlatformHealth;
};

export type IntegrationTestResponse = {
  status: "ok" | "error";
  outcome: string;
  error?: string;
  integration?: IntegrationStatusRow;
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
  target_type: "http" | "tcp" | "ssl" | "dns" | "container";
  address: string;
  expected_status?: number | null;
  timeout_seconds: number;
  warning_days: number;
  is_active: boolean;
};

export type AgentActivity = {
  recent_actions: Array<{
    action_id: string;
    agent_id: string;
    action_type: string;
    action_summary: string;
    reasoning: string;
    confidence_score: number;
    policy_verdict: string;
    status: string;
    duration_ms: number;
    created_at: string;
  }>;
  active_agents: Array<{
    agent_id: string;
    name: string;
    status: string;
    success_rate: number;
  }>;
  stats: {
    total_actions: number;
    success_rate: number;
    pending_approvals: number;
  };
  timestamp: string;
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
  agent_activity: AgentActivity;
};

export type DashboardRealtimeEventType =
  | "metric_update"
  | "incident_created"
  | "incident_resolved"
  | "incident_explained"
  | "remediation_executed"
  | "container_status_changed"
  | "agent_activity";

export type DashboardRealtimeEvent = {
  type: DashboardRealtimeEventType;
  timestamp: string;
  payload:
    | DashboardSnapshot
    | IncidentRow
    | RemediationRow
    | ContainerRow
    | AgentActivity;
};

function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timeoutId));
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

let isRefreshing = false;
let pendingRefresh: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (pendingRefresh) return pendingRefresh;
  isRefreshing = true;
  pendingRefresh = (async () => {
    try {
      const res = await fetch(buildApiUrl("/auth/refresh"), {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (!data.access_token) return false;
      setAccessToken(data.access_token);
      return true;
    } catch {
      return false;
    } finally {
      isRefreshing = false;
      pendingRefresh = null;
    }
  })();
  return pendingRefresh;
}

async function fetchJsonWithRetry<T>(path: string, retries: number = MAX_RETRIES): Promise<T> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetchWithTimeout(buildApiUrl(path), {
        cache: "no-store",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...authHeaders() },
      });

      if (response.status === 401) {
        const refreshed = await tryRefreshToken();
        if (refreshed) {
          const retryResponse = await fetchWithTimeout(buildApiUrl(path), {
            cache: "no-store",
            credentials: "include",
            headers: { "Content-Type": "application/json", ...authHeaders() },
          });
          if (retryResponse.ok) return retryResponse.json() as Promise<T>;
        }
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        throw new Error("Authentication required");
      }

      if (!response.ok) {
        throw new Error(`AegisNex API ${path} returned ${response.status}`);
      }

      return response.json() as Promise<T>;
    } catch (err) {
      if (attempt < retries && err instanceof Error && err.name !== "AbortError") {
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }
      throw err;
    }
  }
  throw new Error(`Failed to fetch ${path} after ${retries + 1} attempts`);
}

export function getSystemHealth() {
  return fetchJsonWithRetry<SystemHealthResponse>("/api/system-health");
}

export function getContainers() {
  return fetchJsonWithRetry<ContainersResponse>("/api/containers");
}

export function getIncidents(limit?: number, offset?: number, orgId?: number) {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  if (orgId !== undefined) params.set("org_id", String(orgId));
  const qs = params.toString();
  return fetchJsonWithRetry<IncidentsResponse>(`/api/incidents${qs ? `?${qs}` : ""}`);
}

export function getIncidentDetail(incidentId: string) {
  return fetchJsonWithRetry<IncidentDetailResponse>(`/api/incidents/${incidentId}`);
}

export function assignIncidentClient(incidentId: string, orgId: number | null) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/client`, "POST", { org_id: orgId });
}

export async function acknowledgeIncident(incidentId: string) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/acknowledge`, "POST");
}

export async function resolveIncident(incidentId: string, resolutionNotes: string) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/resolve`, "POST", {
    resolution_notes: resolutionNotes,
  });
}

export interface IncidentExplanation {
  incident_id: string;
  analysis: string;
  similar_incidents: Array<{ source: string; content: string; relevance: number }>;
  runbooks: Array<{ source: string; title: string; content: string }>;
  audit_context: Array<{ content: string; timestamp: string }>;
  confidence: number;
  timestamp: string;
}

export function explainIncident(incidentId: string) {
  return writeJson<IncidentExplanation>(`/api/incidents/${incidentId}/explain`, "POST");
}

export function proposeIncidentRemediation(incidentId: string, plan: Record<string, unknown>, proposedBy: string = "system", confidence: number = 0.0) {
  return writeJson<{ incident: IncidentRow; message: string }>(`/api/incidents/${incidentId}/propose-remediation`, "POST", { plan, proposed_by: proposedBy, confidence });
}

export function approveIncidentRemediation(incidentId: string, actor: string = "system") {
  return writeJson<{ incident: IncidentRow; message: string }>(`/api/incidents/${incidentId}/approve-remediation`, "POST", { actor });
}

export function rejectIncidentRemediation(incidentId: string, actor: string = "system", reason: string = "") {
  return writeJson<{ incident: IncidentRow; message: string }>(`/api/incidents/${incidentId}/reject-remediation`, "POST", { actor, reason });
}

export function executeIncidentRemediation(incidentId: string, correlationId?: string) {
  return writeJson<{ incident: IncidentRow; execution_result: Record<string, unknown>; successful: boolean }>(`/api/incidents/${incidentId}/execute-remediation`, "POST", { correlation_id: correlationId });
}

export interface LearningEntry {
  service?: string;
  incident_type?: string;
  root_cause?: string;
  remediation?: Record<string, unknown>;
  verification?: Record<string, unknown>;
  timestamp?: string;
  confidence?: number;
}

export function getLearningEntries() {
  return fetchJsonWithRetry<{ entries: LearningEntry[]; count: number; timestamp: string }>("/api/learning/entries");
}

export function getLearningStats() {
  return fetchJsonWithRetry<{ stats: Record<string, number>; timestamp: string }>("/api/learning/stats");
}

export function getMetrics() {
  return fetchJsonWithRetry<MetricsResponse>("/api/metrics");
}

export function getNotifications() {
  return fetchJsonWithRetry<NotificationsResponse>("/api/notifications");
}

export function getRemediations() {
  return fetchJsonWithRetry<RemediationsResponse>("/api/remediations");
}

export function getHttpMonitoring() {
  return fetchJsonWithRetry<HttpMonitoringResponse>("/api/http-monitoring");
}

export function getSslMonitoring() {
  return fetchJsonWithRetry<SslMonitoringResponse>("/api/ssl-monitoring");
}

export function getTcpMonitoring() {
  return fetchJsonWithRetry<TcpMonitoringResponse>("/api/tcp-monitoring");
}

export function getMonitoringTargets() {
  return fetchJsonWithRetry<MonitoringTargetsResponse>("/api/monitoring-targets");
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
  return fetchJsonWithRetry<CheckHistoryResponse>(`/api/monitoring-targets/${id}/history`);
}

async function writeJson<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  payload?: unknown,
): Promise<T> {
  const response = await fetchWithTimeout(buildApiUrl(path), {
    method,
    cache: "no-store",
    credentials: "include",
    headers: {
      ...(payload ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  if (response.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      const retryResponse = await fetchWithTimeout(buildApiUrl(path), {
        method,
        cache: "no-store",
        credentials: "include",
        headers: {
          ...(payload ? { "Content-Type": "application/json" } : {}),
          ...authHeaders(),
        },
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (retryResponse.ok) return retryResponse.json() as Promise<T>;
    }
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    throw new Error(`AegisNex API ${path} returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getDashboardWebSocketUrl() {
  return buildWebSocketUrl("/ws/dashboard");
}

export function getDashboardSnapshot() {
  return fetchJsonWithRetry<DashboardSnapshot>("/api/dashboard");
}

export function getIntegrations() {
  return fetchJsonWithRetry<IntegrationsResponse>("/api/integrations");
}

export function getIntegrationStatus() {
  return fetchJsonWithRetry<IntegrationStatusResponse>("/api/integrations/status");
}

export type IntegrationCatalogItem = {
  integration_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  config_schema: { credentials: Record<string, unknown>; settings: Record<string, unknown> };
};

export type IntegrationInstalledRow = {
  integration_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  enabled: boolean;
  credentials: Record<string, string>;
  settings: Record<string, unknown>;
  created_at: string;
};

export function getIntegrationCatalog() {
  return fetchJsonWithRetry<{ catalog: IntegrationCatalogItem[]; count: number }>("/api/integrations/catalog");
}

export function getInstalledIntegrations() {
  return fetchJsonWithRetry<{ integrations: IntegrationInstalledRow[]; count: number }>("/api/integrations/installed");
}

export function installIntegration(name: string, config: { credentials?: Record<string, string>; settings?: Record<string, unknown> }) {
  return writeJson<{ status: string; name: string }>("/api/integrations/install", "POST", { name, config });
}

export function uninstallIntegration(name: string) {
  return writeJson<{ status: string; name: string }>(`/api/integrations/${name}/uninstall`, "POST");
}

export function updateIntegration(name: string, config: { credentials?: Record<string, string>; settings?: Record<string, unknown> }) {
  return writeJson<{ status: string; name: string }>(`/api/integrations/${name}`, "PUT", { config });
}

export function testIntegrationHealth(name: string) {
  return writeJson<{ status: string; name: string; health?: unknown; error?: string }>(`/api/integrations/${name}/health`, "POST");
}

export function testIntegrationConnection(name: string) {
  return writeJson<IntegrationTestResponse>(`/api/integrations/${name}/test`, "POST");
}

export type PlatformHealthResponse = {
  platform_health: PlatformHealth;
  integrations: IntegrationStatusRow[];
  timestamp: string;
};

export function getPlatformHealth() {
  return fetchJsonWithRetry<PlatformHealthResponse>("/api/platform/health");
}

export type SystemInfoResponse = {
  os: string;
  hostname: string;
  uptime_seconds: number | null;
  docker_version: string | null;
  platform?: string;
  python_version?: string;
};

export type AppSettings = {
  session_timeout?: string;
  workspace_name?: string;
  email_notifications?: string;
  notification_frequency?: string;
  timezone?: string;
  theme?: string;
  accent_color?: string;
};

export type AppSettingsResponse = {
  settings: AppSettings;
  status?: string;
};

export type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
};

export type ApiKeysResponse = {
  keys: ApiKeyRow[];
};

export type KnowledgeUploadResponse = {
  status: string;
  document: string;
  chunks_indexed: number;
  path: string;
};

export function getSystemInfo() {
  return fetchJsonWithRetry<SystemInfoResponse>("/api/system-info");
}

export function getAppSettings() {
  return fetchJsonWithRetry<AppSettingsResponse>("/api/settings");
}

export async function saveAppSettings(payload: Partial<AppSettings>) {
  return writeJson<AppSettingsResponse>("/api/settings", "PUT", payload);
}

export function getApiKeys() {
  return fetchJsonWithRetry<ApiKeysResponse>("/api/api-keys");
}

export async function createApiKey(name: string) {
  return writeJson<{ key: string; status?: string }>("/api/api-keys", "POST", { name });
}

export async function revokeApiKey(keyId: string) {
  return writeJson<{ status?: string }>(`/api/api-keys/${keyId}`, "DELETE");
}

export function uploadKnowledgeDocument(file: File, onProgress?: (progress: number) => void) {
  return new Promise<KnowledgeUploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", buildApiUrl("/knowledge/upload"));
    xhr.withCredentials = true;
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      const response = xhr.response as KnowledgeUploadResponse | null;
      if (xhr.status >= 200 && xhr.status < 300 && response) {
        resolve(response);
        return;
      }
      reject(new Error(`AegisNex API /api/knowledge/upload returned ${xhr.status}`));
    };

    xhr.onerror = () => reject(new Error("Failed to upload knowledge document"));
    xhr.onabort = () => reject(new Error("Upload aborted"));

    const formData = new FormData();
    formData.append("file", file, file.name);
    xhr.send(formData);
  });
}

export async function startContainer(name: string) {
  return writeJson<Record<string, unknown>>(`/api/containers/${encodeURIComponent(name)}/start`, "POST");
}

export async function stopContainer(name: string) {
  return writeJson<Record<string, unknown>>(`/api/containers/${encodeURIComponent(name)}/stop`, "POST");
}

export async function restartContainer(name: string) {
  return writeJson<Record<string, unknown>>(`/api/containers/${encodeURIComponent(name)}/restart`, "POST");
}

export function getContainerLogs(name: string, tail: number = 100) {
  return fetchJsonWithRetry<{ status: string; container: string; logs: string[]; count: number }>(
    `/api/containers/${encodeURIComponent(name)}/logs?tail=${tail}`,
  );
}

export async function reopenIncident(incidentId: string) {
  return writeJson<IncidentRow>(`/api/incidents/${incidentId}/reopen`, "POST");
}

export async function deleteIncident(incidentId: string) {
  return writeJson<{ status: string }>(`/api/incidents/${incidentId}`, "DELETE");
}

export function getMCPTools() {
  return fetchJsonWithRetry<MCPResponse>("/api/mcp");
}

// ---- AI Intelligence ----

export type AiChatStep = {
  node: string;
  status: string;
  summary: string;
};

export type AiChatResponse = {
  answer: string;
  technical_details: string;
  goal_achieved: boolean;
  confidence: number;
  steps: AiChatStep[];
  observations: string[];
  corrections: string[];
  errors: string[];
  evidence: string[];
  reasoning_summary: string;
  remaining_uncertainty: string;
  execution_duration_ms: number;
  provider_used: string;
  model_used: string;
};

export type AiPlanResponse = {
  objective: string;
  plan: Record<string, unknown>;
  current_plan: string[];
  parallel_batches: string[][];
  missing_info: string[];
};

export type AiAnalyzeResponse = {
  objective: string;
  final_answer: string;
  goal_achieved: boolean;
  confidence: number;
  plan: Record<string, unknown>;
  executed_steps: string[];
  observations: string[];
  corrections: string[];
  errors: string[];
};

export type AiHistoryItem = {
  id: number;
  request: string;
  objective: string;
  result_text: string;
  confidence: number;
  goal_achieved: boolean;
  executed_at: string;
};

export type AiHistoryResponse = {
  history: AiHistoryItem[];
  count: number;
  total?: number;
};

export async function postAiChat(request: string) {
  return writeJson<AiChatResponse>("/api/ai/chat", "POST", { request });
}

export async function postAiPlan(request: string) {
  return writeJson<AiPlanResponse>("/api/ai/plan", "POST", { request });
}

export async function postAiAnalyze(request: string) {
  return writeJson<AiAnalyzeResponse>("/api/ai/analyze", "POST", { request });
}

export function getAiHistory(limit?: number, offset?: number) {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const qs = params.toString();
  return fetchJsonWithRetry<AiHistoryResponse>(`/api/ai/history${qs ? `?${qs}` : ""}`);
}

export type AiWorkflowResponse = {
  nodes: string[];
  edges: { from: string; to: string; condition?: string }[];
  max_retries: number;
};

export type AiExecutionsResponse = {
  executions: Record<string, unknown>[];
  count: number;
  total: number;
  stats: {
    total: number;
    successful: number;
    failed: number;
    success_rate: number;
    avg_confidence: number;
    avg_execution_duration_ms: number;
  };
};

export type AiMemoryEntry = Record<string, unknown>;

export type AiMemoryResponse = {
  entries: AiMemoryEntry[];
  count: number;
  total?: number;
  query?: string;
  type?: string;
};

export type AiToolDef = {
  name: string;
  description: string;
  category: string;
  parameters: { name: string; type: string; description: string; required: boolean }[];
  permission_level: string;
  access_mode: string;
  risk_level: string;
  requires_approval: boolean;
  destructive: boolean;
};

export type AiToolsResponse = {
  tools: AiToolDef[];
  count: number;
};

export type AiApprovalResponse = {
  status: string;
  approval_id: string;
};

export function getAiWorkflows() {
  return fetchJsonWithRetry<AiWorkflowResponse>("/api/ai/workflows");
}

export function getAiExecutions(limit?: number, offset?: number) {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const qs = params.toString();
  return fetchJsonWithRetry<AiExecutionsResponse>(`/api/ai/executions${qs ? `?${qs}` : ""}`);
}

export function getAiMemory(query?: string, type?: string, limit?: number) {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (type) params.set("type", type);
  if (limit !== undefined) params.set("limit", String(limit));
  const qs = params.toString();
  return fetchJsonWithRetry<AiMemoryResponse>(`/api/ai/memory${qs ? `?${qs}` : ""}`);
}

export function getAiTools() {
  return fetchJsonWithRetry<AiToolsResponse>("/api/ai/tools");
}

export async function postAiApprove(approvalId: string) {
  return writeJson<AiApprovalResponse>("/api/ai/approve", "POST", { approval_id: approvalId });
}

export async function postAiReject(approvalId: string) {
  return writeJson<AiApprovalResponse>("/api/ai/reject", "POST", { approval_id: approvalId });
}

// ---- Sprint 9: Runbooks, Workflows, Timeline, Policies, Risk ----

export type RunbookStepDef = {
  name: string;
  action: string;
  tool: string;
  params: Record<string, unknown>;
  description: string;
  condition: string;
  on_failure: string;
  retry_count: number;
  requires_approval: boolean;
  parallel: boolean;
};

export type RunbookDef = {
  name: string;
  description: string;
  tags: string[];
  steps: RunbookStepDef[];
};

export type RunbooksResponse = {
  runbooks: RunbookDef[];
  count: number;
};

export type RunbookExecuteResponse = {
  status: string;
  runbook_status: string;
  step_results: Record<string, unknown>[];
  error: string;
};

export type WorkflowStartResponse = {
  status: string;
  confidence: number;
  goal_achieved: boolean;
  workflow_triggered: string;
  runbook: string;
};

export type WorkflowHistoryResponse = {
  history: Record<string, unknown>[];
  count: number;
};

export type TimelineEntry = {
  type: string;
  timestamp: string;
  summary: string;
  confidence?: number;
  goal_achieved?: boolean;
  category?: string;
  severity?: string;
};

export type TimelineResponse = {
  timeline: TimelineEntry[];
  count: number;
};

export type PolicyDef = {
  name: string;
  description: string;
  action_pattern: string;
  condition: string;
  effect: string;
  priority: number;
  enabled: boolean;
};

export type PoliciesResponse = {
  policies: PolicyDef[];
  count: number;
};

export type RiskAssessmentResponse = {
  assessment: {
    score: number;
    level: string;
    confidence: number;
    requires_approval: boolean;
    impact_estimate: string;
    factors: string[];
    auto_execute_allowed: boolean;
  };
};

export type ApprovalRespondResponse = {
  status: string;
  approval_id: string;
};

export function getRunbooks() {
  return fetchJsonWithRetry<RunbooksResponse>("/api/runbooks");
}

export async function executeRunbook(runbook: string) {
  return writeJson<RunbookExecuteResponse>("/api/runbooks/execute", "POST", { runbook });
}

export async function startWorkflow(workflow: string) {
  return writeJson<WorkflowStartResponse>("/api/workflows/start", "POST", { workflow });
}

export function getWorkflowHistory(limit?: number) {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  return fetchJsonWithRetry<WorkflowHistoryResponse>(`/api/workflows/history${params.toString() ? `?${params}` : ""}`);
}

export function getAiTimeline() {
  return fetchJsonWithRetry<TimelineResponse>("/api/ai/timeline");
}

export function getAiPolicies() {
  return fetchJsonWithRetry<PoliciesResponse>("/api/ai/policies");
}

export function getAiRisk(tool: string) {
  const params = new URLSearchParams({ tool });
  return fetchJsonWithRetry<RiskAssessmentResponse>(`/api/ai/risk?${params}`);
}

export async function respondApproval(approvalId: string, decision: "approve" | "reject") {
  return writeJson<ApprovalRespondResponse>("/api/approval/respond", "POST", { approval_id: approvalId, decision });
}

// ---- MSP Clients / Tenant Organizations ----

export type ClientOrganization = {
  id: number;
  name: string;
  slug: string;
  domain: string;
  settings: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
};

export type ClientTeam = {
  id: number;
  org_id: number;
  name: string;
  slug: string;
  description: string;
  settings?: Record<string, unknown>;
  created_at: string;
};

export type ClientProject = {
  id: number;
  org_id: number;
  team_id: number;
  name: string;
  slug: string;
  description: string;
  created_at: string;
};

export type ClientOrgStats = {
  user_count: number;
  team_count: number;
  project_count: number;
};

export type ClientOrganizationsResponse = {
  organizations: ClientOrganization[];
  count: number;
  error?: string;
};

export type ClientTeamsResponse = {
  teams: ClientTeam[];
  count: number;
};

export type ClientProjectsResponse = {
  projects: ClientProject[];
  count: number;
};

export function getClientOrganizations() {
  return fetchJsonWithRetry<ClientOrganizationsResponse>("/api/orgs");
}

export function getClientOrganization(orgId: number) {
  return fetchJsonWithRetry<ClientOrganization>(`/api/orgs/${orgId}`);
}

export function getClientOrgStats(orgId: number) {
  return fetchJsonWithRetry<ClientOrgStats>(`/api/orgs/${orgId}/stats`);
}

export function getClientTeams(orgId: number) {
  return fetchJsonWithRetry<ClientTeamsResponse>(`/api/orgs/${orgId}/teams`);
}

export function getClientProjects(orgId: number) {
  return fetchJsonWithRetry<ClientProjectsResponse>(`/api/orgs/${orgId}/projects`);
}

export function createClientOrganization(payload: { name: string; domain?: string }) {
  return writeJson<ClientOrganization>("/api/orgs", "POST", payload);
}

// ---- Approval Queue ----

export type ApprovalRequest = {
  approval_id: string;
  request_type: string;
  requester: string;
  summary: string;
  details: Record<string, unknown> | string;
  status: string;
  created_at: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  comment?: string | null;
};

export type ApprovalsResponse = {
  approvals: ApprovalRequest[];
  count: number;
};

export function getApprovals(params?: { status?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return fetchJsonWithRetry<ApprovalsResponse>(`/api/approvals${q ? `?${q}` : ""}`);
}

export function respondQueuedApproval(approvalId: string, decision: "approved" | "rejected", comment?: string) {
  return writeJson<ApprovalRequest>(`/api/approvals/${encodeURIComponent(approvalId)}/respond`, "POST", { decision, comment });
}

// ---- Enterprise Search ----

export type SearchResult = {
  domain: string;
  id: string;
  title: string;
  snippet: string;
  url: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type SearchResponse = {
  results: SearchResult[];
  total: number;
  domains: Record<string, number>;
  query: string;
  duration_ms: number;
};

export type SearchDomainsResponse = {
  domains: Record<string, number>;
  total: number;
};

export type SearchStatsResponse = {
  index_size: number;
  domains: Record<string, number>;
  last_indexed: string | null;
};

export function searchEnterprise(query: string, domain?: string, limit?: number) {
  const params = new URLSearchParams({ q: query });
  if (domain) params.set("domain", domain);
  if (limit) params.set("limit", String(limit));
  return fetchJsonWithRetry<SearchResponse>(`/api/search?${params}`);
}

export function getSearchDomains() {
  return fetchJsonWithRetry<SearchDomainsResponse>("/api/search/domains");
}

export function getSearchStats() {
  return fetchJsonWithRetry<SearchStatsResponse>("/api/search/stats");
}

export async function reindexSearch(domains?: string[]) {
  return writeJson<{ status: string }>("/api/search/reindex", "POST", domains ? { domains } : undefined);
}

// ---- AI Governance ----

export type GovernanceAgent = {
  agent_id: string;
  name: string;
  agent_type: string;
  description: string;
  owner: string;
  team: string;
  status: string;
  risk_level: string;
  trust_score: number;
  allowed_tools: string[];
  allowed_resources: string[];
  max_actions_per_hour: number;
  total_actions: number;
  total_denied: number;
  total_anomalies: number;
  created_at: string;
  updated_at: string;
  last_active_at: string | null;
};

export type GovernanceAction = {
  action_id: string;
  agent_id: string;
  action_type: string;
  action_summary: string;
  target_resource: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  reasoning: string;
  confidence_score: number;
  policy_verdict: string;
  status: string;
  duration_ms: number;
  created_at: string;
};

export type GovernancePolicy = {
  policy_id: number;
  name: string;
  description: string;
  policy_type: string;
  target_agents: string[];
  conditions: Record<string, unknown>;
  effect: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type GovernanceAnomaly = {
  anomaly_id: number;
  agent_id: string;
  anomaly_type: string;
  description: string;
  severity: string;
  evidence: Record<string, unknown>;
  status: string;
  detected_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
};

export type GovernanceStats = {
  total_agents: number;
  active_agents: number;
  by_risk: Record<string, number>;
  by_type: Record<string, number>;
  total_actions: number;
  total_denied: number;
  open_anomalies: number;
  avg_trust_score: number;
};

export function getGovernanceStats() {
  return fetchJsonWithRetry<GovernanceStats>("/api/governance/stats");
}

export function listGovernanceAgents(params?: { status?: string; risk_level?: string; team?: string }) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.risk_level) qs.set("risk_level", params.risk_level);
  if (params?.team) qs.set("team", params.team);
  const q = qs.toString();
  return fetchJsonWithRetry<GovernanceAgent[]>(`/api/governance/agents${q ? `?${q}` : ""}`);
}

export function getGovernanceAgent(agentId: string) {
  return fetchJsonWithRetry<GovernanceAgent>(`/api/governance/agents/${encodeURIComponent(agentId)}`);
}

export function listGovernanceActions(params?: { agent_id?: string; action_type?: string; verdict?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.agent_id) qs.set("agent_id", params.agent_id);
  if (params?.action_type) qs.set("action_type", params.action_type);
  if (params?.verdict) qs.set("verdict", params.verdict);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return fetchJsonWithRetry<GovernanceAction[]>(`/api/governance/actions${q ? `?${q}` : ""}`);
}

export function getGovernanceActionStats(agentId?: string) {
  const qs = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  return fetchJsonWithRetry<Record<string, unknown>>(`/api/governance/actions/stats${qs}`);
}

export function listGovernancePolicies() {
  return fetchJsonWithRetry<GovernancePolicy[]>("/api/governance/policies");
}

export function listGovernanceAnomalies(params?: { agent_id?: string; status?: string; severity?: string }) {
  const qs = new URLSearchParams();
  if (params?.agent_id) qs.set("agent_id", params.agent_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.severity) qs.set("severity", params.severity);
  const q = qs.toString();
  return fetchJsonWithRetry<GovernanceAnomaly[]>(`/api/governance/anomalies${q ? `?${q}` : ""}`);
}

// ── Mission Control Types ──

export type StageResult = {
  stage_id: string;
  start_time: string | null;
  finish_time: string | null;
  latency_ms: number;
  status: "queued" | "running" | "completed" | "failed" | "skipped";
  confidence: number;
  model: string;
  provider: string;
  tokens: number;
  estimated_cost: number;
  summary: string;
  connected_tools: string[];
  evidence: string[];
  policy_decisions: Array<{ policy: string; effect: string; reason: string }>;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
};

export type Execution = {
  execution_id: string;
  request: string;
  user: string;
  timestamp: string;
  current_status: "queued" | "running" | "completed" | "failed";
  total_latency_ms: number;
  total_cost: number;
  confidence: number;
  overall_result: string;
  stages: StageResult[];
  error: string;
  metadata: Record<string, unknown>;
};

export type ExecutionStats = {
  total: number;
  completed: number;
  failed: number;
  running: number;
  queued: number;
  avg_latency: number;
  avg_cost: number;
  avg_confidence: number;
  total_cost: number;
};

export type ExecutionsResponse = {
  executions: Execution[];
  count: number;
  total: number;
  limit: number;
  offset: number;
};

export type ExecutionDetailResponse = {
  execution: Execution;
  stats: ExecutionStats;
};

// ── Mission Control API ──

export function getMissionControlExecutions(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  search?: string;
  user?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  if (params?.status) qs.set("status", params.status);
  if (params?.search) qs.set("search", params.search);
  if (params?.user) qs.set("user", params.user);
  const q = qs.toString();
  return fetchJsonWithRetry<ExecutionsResponse>(`/api/mission-control/executions${q ? `?${q}` : ""}`);
}

export function getMissionControlExecution(executionId: string) {
  return fetchJsonWithRetry<ExecutionDetailResponse>(`/api/mission-control/executions/${encodeURIComponent(executionId)}`);
}

export function getMissionControlStats() {
  return fetchJsonWithRetry<ExecutionStats>("/api/mission-control/stats");
}

export function exportMissionControlExecution(executionId: string) {
  return fetchJsonWithRetry<Execution>(`/api/mission-control/executions/${encodeURIComponent(executionId)}/export`);
}

export function getMissionControlWebSocketUrl(): string {
  return buildWebSocketUrl("/ws/mission-control");
}
