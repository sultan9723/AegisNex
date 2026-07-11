"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Cloud,
  Code2,
  Container,
  Database,
  Gauge,
  Github,
  GitPullRequest,
  Globe2,
  HardDrive,
  Loader2,
  Mail,
  MessageSquare,
  Plug,
  PlugZap,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { SkeletonCard } from "@/components/common/Skeleton";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  getIntegrationCatalog,
  getIntegrationStatus,
  getInstalledIntegrations,
  installIntegration,
  testIntegrationConnection,
  uninstallIntegration,
  type IntegrationCatalogItem,
  type IntegrationHealth,
  type IntegrationInstalledRow,
  type IntegrationStatusResponse,
  type IntegrationStatusRow,
  type PlatformHealth,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { publish } from "@/lib/workflow";

const categoryIcons: Record<string, typeof Activity> = {
  "AI Providers": Sparkles,
  Infrastructure: Container,
  Notifications: MessageSquare,
  "Developer Tools": Code2,
  Cloud,
  MCP: TerminalSquare,
};

const integrationIcons: Record<string, typeof Activity> = {
  openai: Sparkles,
  anthropic: Bot,
  gemini: Sparkles,
  ollama: Bot,
  docker: Container,
  prometheus: Gauge,
  grafana: Activity,
  redis: Database,
  postgresql: Database,
  sqlite: HardDrive,
  slack: MessageSquare,
  discord: MessageSquare,
  email: Mail,
  teams: MessageSquare,
  pagerduty: AlertTriangle,
  github: Github,
  gitlab: GitPullRequest,
  jira: ShieldCheck,
  aws: Cloud,
  azure: Cloud,
  gcp: Globe2,
  "mcp-filesystem": HardDrive,
  "mcp-github": Github,
  "mcp-browser": Globe2,
  "mcp-custom": TerminalSquare,
};

const healthStyles: Record<IntegrationHealth, { badge: "success-subtle" | "warning-subtle" | "danger-subtle" | "secondary"; dot: string; icon: typeof Activity }> = {
  healthy: { badge: "success-subtle", dot: "bg-success", icon: CheckCircle2 },
  warning: { badge: "warning-subtle", dot: "bg-warning", icon: AlertTriangle },
  offline: { badge: "danger-subtle", dot: "bg-danger", icon: XCircle },
  unknown: { badge: "secondary", dot: "bg-text-tertiary", icon: WifiOff },
};

const detailLabels: Record<string, string> = {
  configured_model: "Model",
  api_status: "API Status",
  last_sync: "Last Sync",
  available_tools: "Tools",
};

function formatDetailKey(key: string) {
  return detailLabels[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatTimestamp(value: string) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function isConfigured(row: IntegrationStatusRow) {
  return row.status !== "Not Configured" && row.status !== "Unavailable";
}

export default function IntegrationsPage() {
  const [status, setStatus] = useState<IntegrationStatusResponse | null>(null);
  const [catalog, setCatalog] = useState<IntegrationCatalogItem[]>([]);
  const [installed, setInstalled] = useState<IntegrationInstalledRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [installDialog, setInstallDialog] = useState<IntegrationCatalogItem | null>(null);
  const [installCreds, setInstallCreds] = useState<Record<string, string>>({});
  const [installSettings, setInstallSettings] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      getIntegrationStatus(),
      getIntegrationCatalog().then((res) => res.catalog).catch(() => []),
      getInstalledIntegrations().then((res) => res.integrations).catch(() => []),
    ]).then(([nextStatus, nextCatalog, nextInstalled]) => {
      if (cancelled) return;
      setStatus(nextStatus);
      setCatalog(nextCatalog);
      setInstalled(nextInstalled);
    }).catch((err) => {
      if (cancelled) return;
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(load, [load]);

  const installedIds = useMemo(() => new Set(installed.map((item) => item.integration_id)), [installed]);
  const marketplace = useMemo(() => catalog.filter((item) => !installedIds.has(item.integration_id)), [catalog, installedIds]);
  const configuredCount = status?.integrations.filter(isConfigured).length ?? 0;

  const handleConnect = (item: IntegrationCatalogItem) => {
    setInstallDialog(item);
    setInstallCreds({});
    setInstallSettings({});
  };

  const handleReconnect = (item: IntegrationInstalledRow) => {
    setInstallDialog(catalog.find((candidate) => candidate.integration_id === item.integration_id) ?? null);
    setInstallCreds(item.credentials ?? {});
    setInstallSettings(Object.fromEntries(Object.entries(item.settings ?? {}).map(([key, value]) => [key, String(value)])));
  };

  const handleInstallConfirm = async () => {
    if (!installDialog) return;
    setActionLoading(installDialog.integration_id);
    try {
      await installIntegration(installDialog.integration_id, {
        credentials: installCreds,
        settings: Object.fromEntries(Object.entries(installSettings).filter(([, value]) => value)),
      });
      publish("IntegrationConnected", { id: installDialog.integration_id });
      toast.success(`${installDialog.name} configuration saved`);
      setInstallDialog(null);
      load();
    } catch {
      toast.error(`Failed to configure ${installDialog.name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDisconnect = async (name: string) => {
    setActionLoading(name);
    try {
      await uninstallIntegration(name);
      publish("IntegrationDisconnected", { id: name });
      toast.success("Integration disconnected");
      load();
    } catch {
      toast.error(`Failed to disconnect ${name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTest = async (row: IntegrationStatusRow) => {
    setActionLoading(`test-${row.id}`);
    try {
      const result = await testIntegrationConnection(row.id);
      setTestResults((previous) => ({ ...previous, [row.id]: result.outcome }));
      if (result.integration) {
        setStatus((previous) => previous ? {
          ...previous,
          integrations: previous.integrations.map((item) => item.id === row.id ? result.integration! : item),
          categories: previous.categories.map((category) => ({
            ...category,
            integrations: category.integrations.map((item) => item.id === row.id ? result.integration! : item),
          })),
        } : previous);
      }
      if (result.status === "ok") toast.success(`${row.name}: ${result.outcome}`);
      else toast.error(`${row.name}: ${result.outcome}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection test failed";
      setTestResults((previous) => ({ ...previous, [row.id]: message }));
      toast.error(`${row.name}: ${message}`);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <RouteScaffold title="Integrations" description="Enterprise Integrations Center for AI providers, infrastructure, notifications, developer tools, cloud, and MCP." icon={Plug}>
      {loading ? (
        <div className="space-y-5">
          <SkeletonCard className="h-28" />
          <div className="grid gap-4 xl:grid-cols-3">
            {Array.from({ length: 9 }).map((_, index) => <SkeletonCard key={index} className="h-44" />)}
          </div>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-danger/20 bg-danger/10 p-4 text-sm text-danger">{error}</div>
      ) : status ? (
        <div className="space-y-8">
          <section className="overflow-hidden rounded-2xl border border-border/50 bg-surface-elevated/60 p-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20">
                    <PlugZap className="size-4" />
                  </span>
                  <Badge variant="secondary" size="sm">Backend verified</Badge>
                </div>
                <h2 className="text-lg font-semibold text-text-primary">Enterprise Integrations Center</h2>
                <p className="mt-1 max-w-3xl text-sm text-text-secondary">
                  Status is derived from backend configuration, installed providers, repository checks, and live health probes. Unconfigured services are shown as unavailable instead of connected.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <PlatformStatusBadge health={status.platform_health} />
                <SummaryMetric label="Core Services" value={`${status.platform_health.required_healthy}/${status.platform_health.required_total}`} />
                <SummaryMetric label="Optional Configured" value={`${status.platform_health.optional_configured}/${status.platform_health.optional_total}`} />
              </div>
            </div>
          </section>

          {configuredCount === 0 && (
            <section className="rounded-2xl border border-dashed border-border/60 bg-surface-elevated/35 p-8 text-center">
              <PlugZap className="mx-auto mb-3 size-9 text-text-tertiary" />
              <h3 className="text-sm font-semibold text-text-primary">No integrations configured.</h3>
              <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">Connect your first AI provider or infrastructure service to enable live health verification.</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <Button asChild>
                  <Link href="/settings">Open Settings</Link>
                </Button>
                {marketplace[0] && (
                  <Button variant="outline" onClick={() => handleConnect(marketplace[0])}>Connect Integration</Button>
                )}
              </div>
            </section>
          )}

          <div className="space-y-7">
            {status.categories.map((category) => {
              const CategoryIcon = categoryIcons[category.name] ?? Activity;
              return (
                <section key={category.name} className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="grid size-8 place-items-center rounded-lg bg-surface-subtle text-text-secondary ring-1 ring-border/40">
                        <CategoryIcon className="size-4" />
                      </span>
                      <div>
                        <h2 className="text-sm font-semibold text-text-primary">{category.name}</h2>
                        <p className="text-xs text-text-tertiary">{category.count} integrations</p>
                      </div>
                    </div>
                  </div>
                  <div className="grid gap-4 xl:grid-cols-3 2xl:grid-cols-4">
                    {category.integrations.map((row) => (
                      <IntegrationCard
                        key={row.id}
                        row={row}
                        installed={installed.find((item) => item.integration_id === row.id)}
                        testResult={testResults[row.id]}
                        loading={actionLoading === `test-${row.id}` || actionLoading === row.id}
                        onTest={() => handleTest(row)}
                        onConfigure={() => {
                          const item = installed.find((candidate) => candidate.integration_id === row.id);
                          if (item) handleReconnect(item);
                        }}
                        onDisconnect={() => handleDisconnect(row.id)}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>

          {marketplace.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">Available Marketplace Integrations</h2>
                  <p className="text-xs text-text-tertiary">Configure credentials once, then verify health from the cards above.</p>
                </div>
                <Badge variant="secondary" size="sm">{marketplace.length} available</Badge>
              </div>
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {marketplace.map((item) => (
                  <div key={item.integration_id} className="rounded-xl border border-border/40 bg-surface-elevated/35 p-4 transition-all duration-200 hover:border-border/70 hover:bg-surface-elevated/60">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-text-primary">{item.name}</h3>
                        <p className="mt-1 text-xs text-text-secondary">{item.description}</p>
                      </div>
                      <Badge variant="secondary">{item.category}</Badge>
                    </div>
                    <Button size="sm" variant="outline" className="mt-4" onClick={() => handleConnect(item)} disabled={actionLoading === item.integration_id}>
                      {actionLoading === item.integration_id ? <Loader2 className="size-3 animate-spin" /> : <Wifi className="size-3" />}
                      Configure
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      ) : null}

      <Dialog open={installDialog !== null} onOpenChange={(open) => { if (!open) setInstallDialog(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Configure {installDialog?.name}</DialogTitle>
            <DialogDescription>Credentials are stored by the existing integrations backend and used for health checks.</DialogDescription>
          </DialogHeader>
          {installDialog && (
            <div className="space-y-4">
              {Object.entries(installDialog.config_schema?.credentials ?? {}).map(([key, field]) => {
                const config = field as { required?: boolean; label?: string };
                return (
                  <div key={key} className="space-y-1.5">
                    <label className="text-xs font-medium text-text-primary">{config.label ?? key}{config.required ? " *" : ""}</label>
                    <Input
                      type={key.toLowerCase().includes("token") || key.toLowerCase().includes("password") || key.toLowerCase().includes("secret") ? "password" : "text"}
                      value={installCreds[key] ?? ""}
                      onChange={(event) => setInstallCreds((previous) => ({ ...previous, [key]: event.target.value }))}
                      placeholder={config.label ?? key}
                    />
                  </div>
                );
              })}
              {Object.entries(installDialog.config_schema?.settings ?? {}).map(([key, field]) => {
                const config = field as { default?: string; label?: string };
                return (
                  <div key={key} className="space-y-1.5">
                    <label className="text-xs font-medium text-text-primary">{config.label ?? key}</label>
                    <Input
                      value={installSettings[key] ?? config.default ?? ""}
                      onChange={(event) => setInstallSettings((previous) => ({ ...previous, [key]: event.target.value }))}
                      placeholder={config.label ?? key}
                    />
                  </div>
                );
              })}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setInstallDialog(null)}>Cancel</Button>
            <Button onClick={handleInstallConfirm} disabled={actionLoading === installDialog?.integration_id}>
              {actionLoading === installDialog?.integration_id ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
              Save Configuration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </RouteScaffold>
  );
}

function PlatformStatusBadge({ health }: { health: PlatformHealth }) {
  const config = health.status === "healthy"
    ? { icon: CheckCircle2, label: "Platform Healthy", color: "text-success", bg: "bg-success/10" }
    : health.status === "degraded"
      ? { icon: AlertTriangle, label: "Platform Degraded", color: "text-warning", bg: "bg-warning/10" }
      : { icon: XCircle, label: "Platform Critical", color: "text-danger", bg: "bg-danger/10" };
  const Icon = config.icon;
  return (
    <div className={`flex min-w-32 items-center gap-2 rounded-xl border border-border/40 ${config.bg} px-4 py-3`}>
      <Icon className={`size-4 ${config.color}`} />
      <span className={`text-xs font-semibold ${config.color}`}>{config.label}</span>
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-24 rounded-xl border border-border/40 bg-background/25 px-4 py-3">
      <div className="text-lg font-semibold text-text-primary">{value}</div>
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-tertiary">{label}</div>
    </div>
  );
}

function IntegrationCard({
  row,
  installed,
  testResult,
  loading,
  onTest,
  onConfigure,
  onDisconnect,
}: {
  row: IntegrationStatusRow;
  installed?: IntegrationInstalledRow;
  testResult?: string;
  loading: boolean;
  onTest: () => void;
  onConfigure: () => void;
  onDisconnect: () => void;
}) {
  const Icon = integrationIcons[row.id] ?? Activity;
  const style = healthStyles[row.health] ?? healthStyles.unknown;
  const HealthIcon = style.icon;
  const details = Object.entries(row.details ?? {}).filter(([, value]) => value !== "" && value !== null && value !== undefined).slice(0, 4);

  return (
    <article className="group rounded-2xl border border-border/45 bg-surface-elevated/55 p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-border/80 hover:bg-surface-elevated/75 hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/8 text-primary ring-1 ring-primary/15 transition-transform duration-200 group-hover:scale-105">
            <Icon className="size-4.5" />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-text-primary">{row.name}</h3>
            <p className="mt-0.5 line-clamp-2 text-xs text-text-secondary">{row.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {row.required && <Badge variant="info-subtle" size="sm">Required</Badge>}
          <Badge variant={style.badge} dot pulse={row.health === "offline"}>{row.status}</Badge>
        </div>
      </div>

      <div className="mt-4 flex items-start gap-2 rounded-xl bg-background/25 p-3">
        <span className={cn("mt-1 size-2 rounded-full", style.dot)} />
        <div>
          <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
            <HealthIcon className="size-3.5" />
            {row.message}
          </div>
          <p className="mt-1 text-[11px] text-text-tertiary">Last verification: {formatTimestamp(row.last_verification)}</p>
          {testResult && <p className="mt-1 text-[11px] text-text-secondary">Latest test: {testResult}</p>}
        </div>
      </div>

      {details.length > 0 && (
        <dl className="mt-4 grid grid-cols-2 gap-2">
          {details.map(([key, value]) => (
            <div key={key} className="rounded-lg border border-border/30 bg-background/20 p-2">
              <dt className="text-[10px] font-medium uppercase tracking-[0.12em] text-text-tertiary">{formatDetailKey(key)}</dt>
              <dd className="mt-1 truncate text-xs font-medium text-text-primary">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {row.testable && (
          <Button size="sm" variant="outline" onClick={onTest} disabled={loading}>
            {loading ? <Loader2 className="size-3 animate-spin" /> : <RefreshCw className="size-3" />}
            Test Connection
          </Button>
        )}
        {installed ? (
          <>
            <Button size="sm" variant="ghost" onClick={onConfigure}>
              <Settings className="size-3" />
              Configure
            </Button>
            <Button size="sm" variant="ghost" className="text-danger" onClick={onDisconnect} disabled={loading}>
              <WifiOff className="size-3" />
              Disconnect
            </Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" asChild>
            <Link href={row.configure_href || "/settings"}>
              <Settings className="size-3" />
              Configure
            </Link>
          </Button>
        )}
      </div>
    </article>
  );
}
