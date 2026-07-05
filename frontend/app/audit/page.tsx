"use client";

import { useCallback, useEffect, useState } from "react";
import { History, ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/common/LoadingState";
import { EmptyState } from "@/components/common/EmptyState";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { formatTimestamp } from "@/lib/format";
import { API_BASE_URL } from "@/lib/api";

type AuditLog = {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  details: string;
};

type AuditLogsResponse = {
  logs: AuditLog[];
  count: number;
  total: number;
  limit: number;
  offset: number;
};

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const load = useCallback(async (currentOffset: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/audit-logs?limit=${limit}&offset=${currentOffset}`, {
        credentials: "include",
      });
      if (res.status === 401) { window.location.href = "/login"; return; }
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const data: AuditLogsResponse = await res.json();
      setLogs(data.logs);
      setTotal(data.total);
      setOffset(data.offset);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(0); }, [load]);

  const totalPages = Math.ceil(total / limit);
  const currentPage = offset / limit;

  return (
    <RouteScaffold title="Audit Logs" description="Chronological record of all system operations and configuration changes." icon={History}>
      {loading ? (
        <LoadingState message="Loading audit trail..." />
      ) : error ? (
        <EmptyState title="Failed to load audit logs" description={error} actionLabel="Retry" onAction={() => void load(offset)} />
      ) : logs.length === 0 ? (
        <EmptyState title="No audit logs found" description="System operations will appear here as they occur." />
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-border/70">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface/40">
                  <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Timestamp</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Actor</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Action</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Resource</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-border/50 last:border-0 transition-colors hover:bg-white/[0.02] even:bg-white/[0.015]">
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-text-secondary">{formatTimestamp(log.timestamp)}</td>
                    <td className="px-4 py-3">
                      <Badge variant="secondary" size="sm">{log.actor}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <code className="rounded bg-surface-elevated px-1.5 py-0.5 font-mono text-[11px] text-text-primary">{log.action}</code>
                    </td>
                    <td className="px-4 py-3 text-xs text-text-secondary">
                      {log.resource_type}:<span className="ml-1 font-mono text-[11px]">{log.resource_id}</span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 font-mono text-[11px] text-text-tertiary">{log.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              Page {currentPage + 1} of {totalPages} ({total} total)
            </p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => void load(Math.max(0, offset - limit))}>
                <ArrowLeft className="size-3.5 mr-1" />
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={offset + limit >= total} onClick={() => void load(offset + limit)}>
                Next
                <ArrowRight className="size-3.5 ml-1" />
              </Button>
            </div>
          </div>
        </>
      )}
    </RouteScaffold>
  );
}
