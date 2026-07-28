"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, Plus, RefreshCw, Network, AlertCircle, FileText } from "lucide-react";
import {
  createClientOrganization,
  getClientOrganizations,
  getClientOrgStats,
  getIncidents,
  type ClientOrganization,
  type ClientOrgStats,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState, EmptyStateError } from "@/components/common/EmptyState";

function formatDate(value: string) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function StatTile({ label, value, icon: Icon }: { label: string; value: number | string; icon: React.ElementType }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-2xl font-bold text-text-primary">{value}</p>
          <p className="mt-1 text-xs text-text-tertiary">{label}</p>
        </div>
        <div className="grid size-9 place-items-center rounded-lg bg-muted">
          <Icon className="size-4 text-text-secondary" />
        </div>
      </div>
    </div>
  );
}

export default function ClientsPage() {
  const [clients, setClients] = useState<ClientOrganization[]>([]);
  const [stats, setStats] = useState<Record<number, ClientOrgStats>>({});
  const [incidentCounts, setIncidentCounts] = useState<Record<number, { active: number; total: number }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");

  const loadClients = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getClientOrganizations();
      setClients(response.organizations ?? []);
      const statEntries = await Promise.allSettled(
        (response.organizations ?? []).map(async (client) => [client.id, await getClientOrgStats(client.id)] as const),
      );
      const incidentEntries = await Promise.allSettled(
        (response.organizations ?? []).map(async (client) => [client.id, await getIncidents(1000, undefined, client.id)] as const),
      );
      const nextStats: Record<number, ClientOrgStats> = {};
      statEntries.forEach((entry) => {
        if (entry.status === "fulfilled") {
          nextStats[entry.value[0]] = entry.value[1];
        }
      });
      const nextIncidentCounts: Record<number, { active: number; total: number }> = {};
      incidentEntries.forEach((entry) => {
        if (entry.status === "fulfilled") {
          nextIncidentCounts[entry.value[0]] = {
            active: Number(entry.value[1].active_count ?? 0),
            total: Number(entry.value[1].count ?? 0),
          };
        }
      });
      setStats(nextStats);
      setIncidentCounts(nextIncidentCounts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load clients");
      setClients([]);
      setStats({});
      setIncidentCounts({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  const totals = useMemo(() => {
    return Object.values(stats).reduce(
      (acc, item) => ({
        teams: acc.teams + Number(item.team_count ?? 0),
        projects: acc.projects + Number(item.project_count ?? 0),
        users: acc.users + Number(item.user_count ?? 0),
      }),
      { teams: 0, projects: 0, users: 0 },
    );
  }, [stats]);

  const incidentTotals = useMemo(() => {
    return Object.values(incidentCounts).reduce(
      (acc, item) => ({
        active: acc.active + item.active,
        total: acc.total + item.total,
      }),
      { active: 0, total: 0 },
    );
  }, [incidentCounts]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    setSaving(true);
    setNotice("");
    setError("");
    try {
      await createClientOrganization({ name: trimmedName, domain: domain.trim() || undefined });
      setName("");
      setDomain("");
      setNotice("Client created");
      await loadClients();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create client");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" size="sm">MSP workspace</Badge>
            <Badge variant="info-subtle" size="sm">real data only</Badge>
          </div>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-text-primary">Clients</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            Organizations managed by this AegisNex workspace. Use this as the client boundary for incidents,
            approvals, execution evidence, and future runbook policies.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadClients} disabled={loading}>
          <RefreshCw className={loading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Clients" value={clients.length} icon={Building2} />
        <StatTile label="Active incidents" value={incidentTotals.active} icon={AlertCircle} />
        <StatTile label="Total incidents" value={incidentTotals.total} icon={Network} />
        <StatTile label="Assigned users" value={totals.users} icon={Network} />
      </div>

      {(error || notice) && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${error ? "border-danger-border bg-danger-bg text-danger-subtle" : "border-success-border bg-success-bg text-success-subtle"}`}>
          {error || notice}
        </div>
      )}

      <form onSubmit={handleCreate} className="rounded-xl border border-border bg-surface p-5">
        <div className="mb-4">
          <h2 className="text-sm font-semibold text-text-primary">Add a real client</h2>
          <p className="mt-1 text-xs text-text-tertiary">
            This creates an organization record through the existing tenant API. It does not seed demo content.
          </p>
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Client name" />
          <Input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="Domain, optional" />
          <Button type="submit" disabled={saving || !name.trim()}>
            <Plus />
            Add client
          </Button>
        </div>
      </form>

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1].map((item) => (
            <div key={item} className="h-40 rounded-xl border border-border bg-surface p-5">
              <div className="skeleton h-4 w-40" />
              <div className="skeleton mt-4 h-3 w-64" />
              <div className="skeleton mt-8 h-12 w-full" />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyStateError message={error} onRetry={loadClients} />
      ) : clients.length === 0 ? (
        <div className="space-y-4">
          <EmptyState
            icon={Building2}
            title="No clients yet"
            description="Create a real client organization when you are ready to attach incidents, approvals, and evidence to a managed customer."
          />
          <div className="rounded-xl border border-border bg-surface p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-3">
                <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
                  <FileText className="size-4 text-text-secondary" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">Work without a client first</h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    Review real incidents, approvals, and evidence that are not assigned to a client yet.
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" asChild>
                <Link href="/clients/unassigned">Open unassigned evidence</Link>
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {clients.map((client) => {
            const clientStats = stats[client.id];
            const clientIncidents = incidentCounts[client.id];
            return (
              <section key={client.id} className="rounded-xl border border-border bg-surface p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h2 className="truncate text-base font-semibold text-text-primary">{client.name}</h2>
                      <Badge variant={client.is_active ? "success-subtle" : "secondary"} size="sm">
                        {client.is_active ? "active" : "inactive"}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-text-tertiary">{client.domain || "No domain recorded"}</p>
                  </div>
                  <span className="rounded-md border border-border bg-background px-2 py-1 font-mono text-[10px] text-text-tertiary">
                    {client.slug}
                  </span>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-2">
                  <div className="rounded-lg bg-muted/40 p-3">
                    <p className="text-lg font-bold text-text-primary">{clientIncidents?.active ?? 0}</p>
                    <p className="text-[10px] text-text-tertiary">active incidents</p>
                  </div>
                  <div className="rounded-lg bg-muted/40 p-3">
                    <p className="text-lg font-bold text-text-primary">{clientIncidents?.total ?? 0}</p>
                    <p className="text-[10px] text-text-tertiary">total incidents</p>
                  </div>
                  <div className="rounded-lg bg-muted/40 p-3">
                    <p className="text-lg font-bold text-text-primary">{clientStats?.user_count ?? 0}</p>
                    <p className="text-[10px] text-text-tertiary">users</p>
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-2 text-xs text-text-tertiary">
                  <AlertCircle className="size-3.5" />
                  Created {formatDate(client.created_at)}
                </div>
                <div className="mt-4">
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/clients/${client.id}`}>Open evidence view</Link>
                  </Button>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
