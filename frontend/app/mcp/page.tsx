"use client";

import { useEffect, useState } from "react";
import { Bot, CheckCircle2, Copy, Terminal } from "lucide-react";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { SkeletonCard } from "@/components/common/Skeleton";
import { getMCPTools, type MCPResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function McpPage() {
  const [data, setData] = useState<MCPResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMCPTools()
      .then((res) => { if (!cancelled) { setData(res); setLoading(false); } })
      .catch((err) => { if (!cancelled) { setError(err instanceof Error ? err.message : "Failed to load MCP tools"); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  const parsedConfig = (() => {
    try { return data ? JSON.parse(data.claude_config) : null; }
    catch { return null; }
  })();

  const handleCopy = () => {
    if (data?.claude_config) {
      navigator.clipboard.writeText(data.claude_config);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <RouteScaffold title="MCP Workspace" description="AI operations control center for AegisNex tools." icon={Bot}>
      {loading ? (
        <div className="space-y-4">
          <SkeletonCard className="h-64" />
          <SkeletonCard className="h-48" />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-danger/20 bg-danger/10 p-4 text-sm text-danger">{error}</div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/70 bg-surface-elevated/80 shadow-sm">
            <div className="flex items-center justify-between border-b border-border/50 px-5 py-3.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Terminal className="size-4 text-primary" />
                Available tools
              </div>
              <StatusBadge status={data && data.mcp_tools.length > 0 ? "healthy" : "critical"} label={data && data.mcp_tools.length > 0 ? "ready" : "unavailable"} pulse />
            </div>
            {data && data.mcp_tools.length > 0 ? (
              <div className="grid divide-y divide-border/50 md:grid-cols-2 md:divide-x md:divide-y-0">
                {data.mcp_tools.map((tool) => (
                  <div key={tool.name} className="flex flex-col gap-2 px-5 py-4">
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm font-medium text-text-primary">{tool.name}</p>
                      <CheckCircle2 className="size-3.5 text-success" />
                    </div>
                    <p className="text-xs text-text-secondary">{tool.description}</p>
                    <code className="mt-1 block rounded-lg bg-surface px-3 py-2 font-mono text-[11px] text-text-tertiary leading-relaxed">{tool.example}</code>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 px-5 py-8 text-sm text-text-tertiary">
                <CheckCircle2 className="size-4 text-text-tertiary" />
                No tools registered on the connected MCP server.
              </div>
            )}
          </div>

          <div className="rounded-xl border border-border/70 bg-surface-elevated/80 shadow-sm">
            <div className="flex items-center justify-between border-b border-border/50 px-5 py-3.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Terminal className="size-4 text-primary" />
                Claude Desktop config
              </div>
              <Button variant="ghost" size="icon-sm" onClick={handleCopy} aria-label="Copy config">
                <Copy className="size-3.5" />
              </Button>
            </div>
            <pre className="overflow-x-auto px-5 py-4 font-mono text-xs leading-relaxed text-text-secondary">
              {copied ? "Copied!" : (() => {
                if (!parsedConfig) return data?.claude_config ?? "{}";
                return JSON.stringify(parsedConfig, null, 2);
              })()}
            </pre>
          </div>
        </div>
      )}
    </RouteScaffold>
  );
}
