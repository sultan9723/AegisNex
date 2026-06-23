"use client";

import { useEffect, useState } from "react";
import { Bot, CheckCircle2, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getMCPTools, type MCPResponse } from "@/lib/api";

export default function McpPage() {
  const [data, setData] = useState<MCPResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMCPTools()
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load MCP tools");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const parsedConfig = (() => {
    try {
      return data ? JSON.parse(data.claude_config) : null;
    } catch {
      return null;
    }
  })();

  return (
    <RouteScaffold
      title="MCP Workspace"
      description="AI operations control center for AegisNex tools."
      icon={Bot}
    >
      {loading ? (
        <div className="grid gap-3">
          <div className="rounded-lg border border-[#1F2937] bg-[#111827] p-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] px-4 py-3">
              <div className="h-4 w-32 animate-pulse rounded bg-[#1F2937]" />
              <div className="h-5 w-20 animate-pulse rounded-full bg-[#1F2937]" />
            </div>
            <div className="grid divide-y divide-[#1F2937] md:grid-cols-2 md:divide-x md:divide-y-0">
              {Array.from({ length: 6 }).map((_, idx) => (
                <div key={idx} className="px-4 py-3">
                  <div className="h-4 w-40 animate-pulse rounded bg-[#1F2937]" />
                  <div className="mt-2 h-3 w-64 animate-pulse rounded bg-[#1F2937]" />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : (
        <div className="grid gap-3">
          <div className="rounded-lg border border-[#1F2937] bg-[#111827]">
            <div className="flex items-center justify-between border-b border-[#1F2937] px-4 py-3 text-sm font-semibold text-white">
              Available tools
              <StatusBadge status={data && data.mcp_tools.length > 0 ? "healthy" : "critical"} label={data && data.mcp_tools.length > 0 ? "ready" : "unavailable"} />
            </div>
            {data && data.mcp_tools.length > 0 ? (
              <div className="grid divide-y divide-[#1F2937] md:grid-cols-2 md:divide-x md:divide-y-0">
                {data.mcp_tools.map((tool) => (
                  <div key={tool.name} className="flex items-start justify-between px-4 py-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-mono text-sm text-white">{tool.name}</p>
                        <CheckCircle2 className="size-3.5 text-emerald-400" />
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{tool.description}</p>
                      <code className="mt-2 block rounded bg-[#0B1020] px-2 py-1 text-[10px] text-slate-300">{tool.example}</code>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 px-4 py-6 text-sm text-slate-400">
                <XCircle className="size-4 text-red-400" />
                No tools registered on the connected MCP server.
              </div>
            )}
          </div>

          <div className="rounded-lg border border-[#1F2937] bg-[#111827]">
            <div className="border-b border-[#1F2937] px-4 py-3 text-sm font-semibold text-white">Claude Desktop config</div>
            <pre className="overflow-x-auto px-4 py-3 text-xs leading-relaxed text-slate-300">
              {(() => {
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