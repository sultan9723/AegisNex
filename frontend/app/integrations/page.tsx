"use client";

import { useEffect, useState } from "react";
import { Activity, Bot, Container, Database, ExternalLink, Plug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getIntegrations, type IntegrationRow } from "@/lib/api";

const iconMap: Record<string, typeof Activity> = {
  Grafana: Activity,
  Prometheus: Activity,
  Docker: Container,
  MCP: Bot,
  SQLite: Database,
};

export default function IntegrationsPage() {
  const [rows, setRows] = useState<IntegrationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getIntegrations()
      .then((res) => {
        if (!cancelled) {
          setRows(res.integrations);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load integrations");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <RouteScaffold
      title="Integrations"
      description="Connected observability, metrics, and AI control-plane systems."
      icon={Plug}
    >
      {loading ? (
        <div className="grid gap-3 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="rounded-lg border border-[#1F2937] bg-[#111827] p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="size-4 animate-pulse rounded-full bg-[#1F2937]" />
                  <div className="h-4 w-24 animate-pulse rounded bg-[#1F2937]" />
                </div>
                <div className="h-5 w-16 animate-pulse rounded-full bg-[#1F2937]" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            {rows.map((row) => {
              const Icon = iconMap[row.name] ?? Activity;
              return (
                <div key={row.name} className="rounded-lg border border-[#1F2937] bg-[#111827] p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className="size-4 text-[#00E5FF]" />
                      <h2 className="text-sm font-semibold text-white">{row.name}</h2>
                    </div>
                    <StatusBadge status={row.reachable ? "healthy" : "critical"} label={row.status} />
                  </div>
                  <p className="mt-2 text-xs text-slate-400">{row.description}</p>
                  {row.url && row.reachable && (
                    <Button className="mt-3 gap-2" size="sm" variant="outline" asChild>
                      <a href={row.url} target="_blank" rel="noreferrer">
                        Open {row.name}
                        <ExternalLink className="size-3.5" />
                      </a>
                    </Button>
                  )}
                  {!row.reachable && row.status === "configured" && (
                    <p className="mt-3 text-xs text-slate-500">Service not reachable.</p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </RouteScaffold>
  );
}