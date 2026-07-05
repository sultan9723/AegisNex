"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Bot, Container, Database, ExternalLink, Plug, PlugZap, Loader2, RefreshCw, Wifi, WifiOff, CheckCircle2, XCircle, AlertTriangle, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { SkeletonCard } from "@/components/common/Skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { getIntegrations, installIntegration, uninstallIntegration, updateIntegration, testIntegrationHealth, getInstalledIntegrations, getIntegrationCatalog, type IntegrationRow, type IntegrationCatalogItem, type IntegrationInstalledRow } from "@/lib/api";
import { toast } from "sonner";
import { publish } from "@/lib/workflow";

const iconMap: Record<string, typeof Activity> = {
  Grafana: Activity, Prometheus: Activity, Docker: Container, MCP: Bot, SQLite: Database,
};

function getStatusVariant(status: string): "success-subtle" | "danger-subtle" | "warning-subtle" {
  if (status === "connected" || status === "healthy") return "success-subtle";
  if (status === "disconnected" || status === "error") return "danger-subtle";
  return "warning-subtle";
}

export default function IntegrationsPage() {
  const [rows, setRows] = useState<IntegrationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<IntegrationCatalogItem[]>([]);
  const [installed, setInstalled] = useState<IntegrationInstalledRow[]>([]);
  const [installDialog, setInstallDialog] = useState<IntegrationCatalogItem | null>(null);
  const [installCreds, setInstallCreds] = useState<Record<string, string>>({});
  const [installSettings, setInstallSettings] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [healthResults, setHealthResults] = useState<Record<string, { ok: boolean; error?: string }>>({});

  const load = useCallback(() => {
    let cancelled = false;
    Promise.all([
      getIntegrations(),
      getIntegrationCatalog().then((r) => r.catalog).catch(() => []),
      getInstalledIntegrations().then((r) => r.integrations).catch(() => []),
    ]).then(([integrations, cat, inst]) => {
      if (cancelled) return;
      setRows(integrations.integrations);
      setCatalog(cat);
      setInstalled(inst);
      setLoading(false);
    }).catch((err) => {
      if (cancelled) return;
      setError(err instanceof Error ? err.message : "Failed to load integrations");
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(load, [load]);

  const installedIds = new Set(installed.map((i) => i.integration_id));

  const handleConnect = async (item: IntegrationCatalogItem) => {
    setInstallDialog(item);
    setInstallCreds({});
    setInstallSettings({});
  };

  const handleInstallConfirm = async () => {
    if (!installDialog) return;
    setActionLoading(installDialog.integration_id);
    try {
      const config = {
        credentials: installCreds,
        settings: Object.fromEntries(Object.entries(installSettings).filter(([, v]) => v)),
      };
      await installIntegration(installDialog.integration_id, config);
      publish("IntegrationConnected", { id: installDialog.integration_id });
      toast.success(`${installDialog.name} connected`);
      setInstallDialog(null);
      load();
    } catch {
      toast.error(`Failed to connect ${installDialog.name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDisconnect = async (name: string) => {
    setActionLoading(name);
    try {
      await uninstallIntegration(name);
      publish("IntegrationDisconnected", { id: name });
      toast.success(`Integration disconnected`, {
        action: {
          label: "Undo",
          onClick: async () => {
            const cfg = installed.find((i) => i.integration_id === name);
            if (cfg) {
              await installIntegration(name, { credentials: cfg.credentials, settings: cfg.settings });
              publish("IntegrationConnected", { id: name });
              toast.success("Integration restored");
              load();
            }
          },
        },
        duration: 10000,
      });
      load();
    } catch {
      toast.error(`Failed to disconnect ${name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReconnect = async (item: IntegrationInstalledRow) => {
    setInstallDialog(catalog.find((c) => c.integration_id === item.integration_id) ?? null);
    setInstallCreds(item.credentials ?? {});
    setInstallSettings(Object.fromEntries(Object.entries(item.settings ?? {}).map(([k, v]) => [k, String(v)])));
  };

  const handleTest = async (name: string) => {
    setActionLoading(`test-${name}`);
    try {
      const res = await testIntegrationHealth(name);
      if (res.status === "ok") {
        setHealthResults((p) => ({ ...p, [name]: { ok: true } }));
        toast.success(`${name} health check passed`);
      } else {
        setHealthResults((p) => ({ ...p, [name]: { ok: false, error: res.error } }));
        toast.error(`${name} health check failed: ${res.error}`);
      }
    } catch (err) {
      setHealthResults((p) => ({ ...p, [name]: { ok: false, error: String(err) } }));
      toast.error(`Health check failed for ${name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const marketplace = catalog.filter((item) => !installedIds.has(item.integration_id));

  return (
    <RouteScaffold title="Integrations" description="Connected observability, metrics, and AI control-plane systems." icon={Plug}>
      {loading ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} className="h-28" />)}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-danger/20 bg-danger/10 p-4 text-sm text-danger">{error}</div>
      ) : (
        <div className="space-y-8">
          <div>
            <h2 className="text-sm font-semibold text-text-primary mb-3">System Integrations</h2>
            <div className="grid gap-4 lg:grid-cols-3">
              {rows.map((row) => {
                const Icon = iconMap[row.name] ?? Activity;
                return (
                  <div key={row.name} className="rounded-xl border border-border/60 bg-surface-elevated/70 p-5 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2.5">
                        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
                          <Icon className="size-4" />
                        </div>
                        <h3 className="text-sm font-semibold text-text-primary">{row.name}</h3>
                      </div>
                      <Badge variant={row.reachable ? "success-subtle" : "danger-subtle"} dot pulse={!row.reachable}>{row.status}</Badge>
                    </div>
                    <p className="text-xs text-text-secondary">{row.description}</p>
                    {row.url && row.reachable && (
                      <Button className="mt-3" size="sm" variant="outline" asChild>
                        <a href={row.url} target="_blank" rel="noreferrer">
                          Open {row.name}
                          <ExternalLink className="size-3.5" />
                        </a>
                      </Button>
                    )}
                    {!row.reachable && row.status === "configured" && (
                      <p className="mt-3 text-xs text-text-tertiary">Service not reachable.</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-primary">Installed Marketplace Integrations</h2>
              <Badge variant="secondary" size="sm">{installed.length}</Badge>
            </div>
            {installed.length === 0 ? (
              <div className="rounded-xl border border-border/40 bg-surface-elevated/30 p-8 text-center">
                <PlugZap className="mx-auto size-8 text-text-tertiary mb-2" />
                <p className="text-sm text-text-secondary">No integrations installed yet.</p>
                <p className="text-xs text-text-tertiary mt-1">Connect your tools and services below.</p>
              </div>
            ) : (
              <div className="grid gap-4 lg:grid-cols-3">
                {installed.map((item) => {
                  const health = healthResults[item.integration_id];
                  return (
                    <div key={item.integration_id} className="rounded-xl border border-border/60 bg-surface-elevated/70 p-5 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2.5">
                          <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
                            <Activity className="size-4" />
                          </div>
                          <div>
                            <h3 className="text-sm font-semibold text-text-primary">{item.name}</h3>
                            <p className="text-[10px] text-text-tertiary">{item.category}</p>
                          </div>
                        </div>
                        <Badge variant={item.enabled ? "success-subtle" : "secondary"} dot>{item.enabled ? "Connected" : "Disabled"}</Badge>
                      </div>
                      <p className="text-xs text-text-secondary mb-2">{item.description}</p>
                      {health && (
                        <div className={`flex items-center gap-1.5 mb-2 text-xs ${health.ok ? "text-success" : "text-danger"}`}>
                          {health.ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
                          {health.ok ? "Health OK" : health.error ?? "Unreachable"}
                        </div>
                      )}
                      <div className="flex items-center gap-1.5 mt-2">
                        <Button size="sm" variant="outline" onClick={() => handleTest(item.integration_id)} disabled={actionLoading === `test-${item.integration_id}`}>
                          {actionLoading === `test-${item.integration_id}` ? <Loader2 className="size-3 animate-spin" /> : <Activity className="size-3" />}
                          Test
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleReconnect(item)} disabled={actionLoading === item.integration_id}>
                          <Settings className="size-3" />
                          Configure
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDisconnect(item.integration_id)} disabled={actionLoading === item.integration_id} className="text-danger">
                          {actionLoading === item.integration_id ? <Loader2 className="size-3 animate-spin" /> : <WifiOff className="size-3" />}
                          Disconnect
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {marketplace.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-text-primary">Marketplace</h2>
                <Badge variant="secondary" size="sm">{marketplace.length} available</Badge>
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                {marketplace.map((item) => (
                  <div key={item.integration_id} className="rounded-xl border border-border/40 bg-surface-elevated/30 p-5 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2.5">
                        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/5 text-text-secondary ring-1 ring-border/30">
                          <Activity className="size-4" />
                        </div>
                        <div>
                          <h3 className="text-sm font-semibold text-text-primary">{item.name}</h3>
                          <p className="text-[10px] text-text-tertiary">{item.category}</p>
                        </div>
                      </div>
                      <Badge variant="secondary">Available</Badge>
                    </div>
                    <p className="text-xs text-text-secondary mb-2">{item.description}</p>
                    <Button size="sm" variant="outline" onClick={() => handleConnect(item)} disabled={actionLoading === item.integration_id}>
                      {actionLoading === item.integration_id ? <Loader2 className="size-3 animate-spin" /> : <Wifi className="size-3" />}
                      Connect
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <Dialog open={installDialog !== null} onOpenChange={(o) => { if (!o) setInstallDialog(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect {installDialog?.name}</DialogTitle>
            <DialogDescription>Enter connection details for {installDialog?.name}.</DialogDescription>
          </DialogHeader>
          {installDialog && (
            <div className="space-y-4">
              {Object.entries(installDialog.config_schema?.credentials ?? {}).map(([key, field]) => {
                const f = field as { type?: string; required?: boolean; label?: string };
                return (
                  <div key={key}>
                    <label className="text-xs font-medium text-text-primary">{f.label ?? key}{f.required ? " *" : ""}</label>
                    <Input
                      type={key.toLowerCase().includes("token") || key.toLowerCase().includes("password") || key.toLowerCase().includes("secret") ? "password" : "text"}
                      value={installCreds[key] ?? ""}
                      onChange={(e) => setInstallCreds((p) => ({ ...p, [key]: e.target.value }))}
                      placeholder={f.label ?? key}
                    />
                  </div>
                );
              })}
              {Object.entries(installDialog.config_schema?.settings ?? {}).map(([key, field]) => {
                const f = field as { type?: string; required?: boolean; label?: string; default?: string };
                return (
                  <div key={key}>
                    <label className="text-xs font-medium text-text-primary">{f.label ?? key}</label>
                    <Input
                      value={installSettings[key] ?? f.default ?? ""}
                      onChange={(e) => setInstallSettings((p) => ({ ...p, [key]: e.target.value }))}
                      placeholder={f.label ?? key}
                    />
                  </div>
                );
              })}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setInstallDialog(null)}>Cancel</Button>
            <Button onClick={handleInstallConfirm} disabled={actionLoading === installDialog?.integration_id}>
              {actionLoading === installDialog?.integration_id ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : null}
              Connect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </RouteScaffold>
  );
}
