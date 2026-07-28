"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, Bot, CheckCircle2, ChevronRight, Clock,
  Download, ExternalLink, Filter, History, Layers, Loader2, Search,
  Shield, XCircle, Zap, Brain, Play, Pause, RotateCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { EmptyState } from "@/components/common/EmptyState";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  getMissionControlExecutions,
  getMissionControlExecution,
  getMissionControlStats,
  exportMissionControlExecution,
  getMissionControlWebSocketUrl,
  type Execution,
  type ExecutionStats,
  type StageResult,
} from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const STAGE_ICONS: Record<string, typeof Brain> = {
  planner: Brain,
  knowledge: Layers,
  metrics: Activity,
  docker: Bot,
  policy: Shield,
  risk: AlertTriangle,
  verifier: CheckCircle2,
  executor: Zap,
};

const STAGE_LABELS: Record<string, string> = {
  planner: "Planner",
  knowledge: "Knowledge",
  metrics: "Metrics",
  docker: "Docker",
  policy: "Policy",
  risk: "Risk",
  verifier: "Verifier",
  executor: "Executor",
};

const STATUS_COLORS: Record<string, string> = {
  queued: "bg-text-tertiary/20 text-text-tertiary",
  running: "bg-primary/20 text-primary animate-pulse",
  completed: "bg-success/20 text-success",
  failed: "bg-danger/20 text-danger",
  skipped: "bg-text-tertiary/10 text-text-tertiary",
};

function relative(ts: string): string {
  if (!ts) return "";
  const diff = Date.now() - new Date(ts.replace("Z", "+00:00")).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(cost: number): string {
  if (cost < 0.01) return `$${(cost * 1000).toFixed(2)}m`;
  return `$${cost.toFixed(4)}`;
}

export default function MissionControlPage() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [stats, setStats] = useState<ExecutionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<"Connected" | "Disconnected">("Disconnected");
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef(0);

  const loadExecutions = useCallback(async () => {
    try {
      const [execRes, statsRes] = await Promise.all([
        getMissionControlExecutions({ limit: 20, offset: page * 20, status: statusFilter || undefined, search: search || undefined }),
        getMissionControlStats(),
      ]);
      setExecutions(execRes.executions);
      setTotal(execRes.total);
      setStats(statsRes);
    } catch {
      toast.error("Failed to load executions");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, search]);

  useEffect(() => {
    void loadExecutions();
  }, [loadExecutions]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(getMissionControlWebSocketUrl());
      socket.onopen = () => {
        reconnectRef.current = 0;
        setConnectionStatus("Connected");
      };
      socket.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data);
          if (event.type === "execution_list" || event.type === "execution_update") {
            void loadExecutions();
          }
        } catch {}
      };
      socket.onclose = () => {
        if (closed) return;
        setConnectionStatus("Disconnected");
        reconnectRef.current += 1;
        const delay = Math.min(10000, 1000 * 2 ** Math.min(reconnectRef.current, 4));
        reconnectTimer = window.setTimeout(connect, delay);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
      setConnectionStatus("Disconnected");
    };
  }, [loadExecutions]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(0);
  };

  const handleStatusFilter = (status: string) => {
    setStatusFilter(status === statusFilter ? "" : status);
    setPage(0);
  };

  const openDetail = async (execution: Execution) => {
    setSelectedExecution(execution);
    setDetailOpen(true);
    if (execution.stages.every((s) => s.status === "queued")) {
      setDetailLoading(true);
      try {
        const res = await getMissionControlExecution(execution.execution_id);
        setSelectedExecution(res.execution);
      } catch {} finally {
        setDetailLoading(false);
      }
    }
  };

  const handleExport = async (executionId: string) => {
    try {
      const data = await exportMissionControlExecution(executionId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `execution-${executionId}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Execution exported");
    } catch {
      toast.error("Failed to export execution");
    }
  };

  const totalPages = Math.ceil(total / 20);

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-3rem)] items-center justify-center">
        <Loader2 className="size-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary">
            <Activity className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-primary">Mission Control</h1>
            <p className="text-xs text-text-tertiary">AI execution visualization and monitoring</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={cn("flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium", connectionStatus === "Connected" ? "bg-success/10 text-success" : "bg-text-tertiary/10 text-text-tertiary")}>
            <div className={cn("size-2 rounded-full", connectionStatus === "Connected" ? "bg-success animate-pulse" : "bg-text-tertiary")} />
            {connectionStatus}
          </div>
          <Button variant="outline" size="sm" onClick={() => void loadExecutions()}>
            <RotateCcw className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard label="Total Executions" value={String(stats.total)} icon={Layers} color="primary" />
          <StatCard label="Completed" value={String(stats.completed)} icon={CheckCircle2} color="success" />
          <StatCard label="Failed" value={String(stats.failed)} icon={XCircle} color="danger" />
          <StatCard label="Avg Latency" value={formatLatency(stats.avg_latency)} icon={Clock} color="warning" />
          <StatCard label="Avg Confidence" value={`${(stats.avg_confidence * 100).toFixed(0)}%`} icon={Brain} color="primary" />
        </div>
      )}

      {/* Search and Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-text-tertiary" />
          <Input
            placeholder="Search executions..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {["queued", "running", "completed", "failed"].map((s) => (
            <Button
              key={s}
              variant={statusFilter === s ? "default" : "outline"}
              size="sm"
              onClick={() => handleStatusFilter(s)}
              className="text-xs capitalize"
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      {/* Execution List */}
      {executions.length === 0 ? (
        <EmptyState icon={Activity} title="No executions found" description="AI executions will appear here as they run." />
      ) : (
        <div className="space-y-2">
          {executions.map((exec) => (
            <ExecutionRow key={exec.execution_id} execution={exec} onClick={() => openDetail(exec)} onExport={() => handleExport(exec.execution_id)} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="text-xs text-text-tertiary">Page {page + 1} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}

      {/* Detail Drawer */}
      <ExecutionDetailDrawer
        execution={selectedExecution}
        open={detailOpen}
        loading={detailLoading}
        onClose={() => { setDetailOpen(false); setSelectedExecution(null); }}
        onExport={handleExport}
      />
    </div>
  );
}

// ── Sub-components ──

function StatCard({ label, value, icon: Icon, color }: { label: string; value: string; icon: typeof Brain; color: string }) {
  const colorMap: Record<string, string> = {
    primary: "bg-primary/10 text-primary",
    success: "bg-success/10 text-success",
    danger: "bg-danger/10 text-danger",
    warning: "bg-warning/10 text-warning",
  };
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={cn("grid size-7 place-items-center rounded-lg", colorMap[color] || colorMap.primary)}>
          <Icon className="size-3.5" />
        </div>
        <span className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">{label}</span>
      </div>
      <p className="text-lg font-bold text-text-primary">{value}</p>
    </div>
  );
}

function ExecutionRow({ execution, onClick, onExport }: { execution: Execution; onClick: () => void; onExport: () => void }) {
  const completedStages = execution.stages.filter((s) => s.status === "completed").length;
  const totalStages = execution.stages.length;
  const progress = totalStages > 0 ? (completedStages / totalStages) * 100 : 0;

  return (
    <div
      className="group flex items-center gap-4 rounded-xl border border-border/40 bg-surface-elevated/40 p-4 cursor-pointer transition-all hover:border-border/60 hover:bg-surface-elevated/55"
      onClick={onClick}
    >
      {/* Status indicator */}
      <div className={cn("size-3 shrink-0 rounded-full", STATUS_COLORS[execution.current_status])} />

      {/* Main info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-text-primary truncate max-w-md">{execution.request}</p>
          <Badge variant={execution.current_status === "completed" ? "success-subtle" : execution.current_status === "failed" ? "danger-subtle" : "secondary"} size="sm">
            {execution.current_status}
          </Badge>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-[10px] text-text-tertiary">{execution.execution_id.slice(0, 8)}</span>
          {execution.user && <span className="text-[10px] text-text-tertiary">by {execution.user}</span>}
          <span className="text-[10px] text-text-tertiary">{relative(execution.timestamp)}</span>
          {execution.confidence > 0 && (
            <span className="text-[10px] text-text-tertiary">{(execution.confidence * 100).toFixed(0)}% confidence</span>
          )}
        </div>
      </div>

      {/* Stage pipeline */}
      <div className="hidden lg:flex items-center gap-1">
        {execution.stages.map((stage) => (
          <div key={stage.stage_id} className={cn("size-6 rounded-md flex items-center justify-center text-[9px] font-bold transition-all", STATUS_COLORS[stage.status])}>
            {stage.stage_id.charAt(0).toUpperCase()}
          </div>
        ))}
      </div>

      {/* Metrics */}
      <div className="flex items-center gap-4 text-xs text-text-tertiary">
        {execution.total_latency_ms > 0 && <span>{formatLatency(execution.total_latency_ms)}</span>}
        {execution.total_cost > 0 && <span>{formatCost(execution.total_cost)}</span>}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button variant="ghost" size="icon" className="size-7" onClick={(e) => { e.stopPropagation(); onExport(); }}>
          <Download className="size-3.5" />
        </Button>
        <ChevronRight className="size-4 text-text-tertiary" />
      </div>
    </div>
  );
}

function ExecutionDetailDrawer({ execution, open, loading, onClose, onExport }: { execution: Execution | null; open: boolean; loading: boolean; onClose: () => void; onExport: (id: string) => void }) {
  const [activeStage, setActiveStage] = useState<string | null>(null);
  const activeStageData = execution?.stages.find((s) => s.stage_id === activeStage);

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Execution Details</SheetTitle>
          <SheetDescription>{execution?.execution_id.slice(0, 12) ?? ""}</SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="size-6 animate-spin text-text-tertiary" /></div>
        ) : execution ? (
          <div className="space-y-6 mt-4">
            {/* Request */}
            <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4 space-y-2">
              <h3 className="text-xs font-medium text-text-secondary">Request</h3>
              <p className="text-sm text-text-primary">{execution.request}</p>
              <div className="flex items-center gap-3 text-[10px] text-text-tertiary">
                <span>Status: <Badge variant={execution.current_status === "completed" ? "success-subtle" : "danger-subtle"} size="sm">{execution.current_status}</Badge></span>
                {execution.user && <span>User: {execution.user}</span>}
                <span>{relative(execution.timestamp)}</span>
              </div>
            </div>

            {/* Execution Pipeline */}
            <div>
              <h3 className="text-xs font-medium text-text-secondary mb-3">Execution Pipeline</h3>
              <div className="flex items-center gap-1 overflow-x-auto pb-2">
                {execution.stages.map((stage, idx) => {
                  const Icon = STAGE_ICONS[stage.stage_id] || Zap;
                  const isActive = activeStage === stage.stage_id;
                  return (
                    <div key={stage.stage_id} className="flex items-center gap-1">
                      <button
                        onClick={() => setActiveStage(isActive ? null : stage.stage_id)}
                        className={cn(
                          "flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all border",
                          isActive ? "border-primary bg-primary/10 text-primary" : "border-border/30 bg-surface-elevated/30 text-text-secondary hover:border-border/50"
                        )}
                      >
                        <Icon className="size-3.5" />
                        <span>{STAGE_LABELS[stage.stage_id]}</span>
                        <div className={cn("size-2 rounded-full ml-1", STATUS_COLORS[stage.status].split(" ")[0])} />
                      </button>
                      {idx < execution.stages.length - 1 && (
                        <ChevronRight className="size-3 text-text-tertiary shrink-0" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Active Stage Detail */}
            {activeStageData && (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text-primary">{STAGE_LABELS[activeStageData.stage_id]}</h3>
                  <Badge variant={activeStageData.status === "completed" ? "success-subtle" : activeStageData.status === "failed" ? "danger-subtle" : "secondary"} size="sm">
                    {activeStageData.status}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Latency</span>
                    <p className="text-xs text-text-primary">{activeStageData.latency_ms > 0 ? formatLatency(activeStageData.latency_ms) : "—"}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Confidence</span>
                    <p className="text-xs text-text-primary">{activeStageData.confidence > 0 ? `${(activeStageData.confidence * 100).toFixed(0)}%` : "—"}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Model</span>
                    <p className="text-xs text-text-primary">{activeStageData.model || "—"}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Tokens</span>
                    <p className="text-xs text-text-primary">{activeStageData.tokens > 0 ? String(activeStageData.tokens) : "—"}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Cost</span>
                    <p className="text-xs text-text-primary">{activeStageData.estimated_cost > 0 ? formatCost(activeStageData.estimated_cost) : "—"}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Provider</span>
                    <p className="text-xs text-text-primary">{activeStageData.provider || "—"}</p>
                  </div>
                </div>

                {activeStageData.summary && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Summary</span>
                    <p className="text-xs text-text-secondary">{activeStageData.summary}</p>
                  </div>
                )}

                {activeStageData.connected_tools.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Connected Tools</span>
                    <div className="flex flex-wrap gap-1">
                      {activeStageData.connected_tools.map((tool) => (
                        <Badge key={tool} variant="outline" size="sm">{tool}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {activeStageData.evidence.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Evidence</span>
                    <div className="space-y-1">
                      {activeStageData.evidence.map((ev, i) => (
                        <div key={i} className="text-[10px] text-text-secondary pl-2 border-l border-border/30">{ev}</div>
                      ))}
                    </div>
                  </div>
                )}

                {activeStageData.policy_decisions.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Policy Decisions</span>
                    <div className="space-y-1">
                      {activeStageData.policy_decisions.map((pd, i) => (
                        <div key={i} className="flex items-center gap-2 text-[10px]">
                          <Badge variant={pd.effect === "allow" ? "success-subtle" : pd.effect === "deny" ? "danger-subtle" : "warning-subtle"} size="sm">{pd.effect}</Badge>
                          <span className="text-text-secondary">{pd.policy}</span>
                          {pd.reason && <span className="text-text-tertiary">— {pd.reason}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Object.keys(activeStageData.inputs).length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Inputs</span>
                    <pre className="text-[10px] text-text-secondary bg-surface p-2 rounded overflow-auto max-h-32">{JSON.stringify(activeStageData.inputs, null, 2)}</pre>
                  </div>
                )}

                {Object.keys(activeStageData.outputs).length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-medium text-text-tertiary">Outputs</span>
                    <pre className="text-[10px] text-text-secondary bg-surface p-2 rounded overflow-auto max-h-32">{JSON.stringify(activeStageData.outputs, null, 2)}</pre>
                  </div>
                )}
              </div>
            )}

            {/* Overall Result */}
            {execution.overall_result && (
              <div className="rounded-lg border border-border/50 bg-surface-elevated/50 p-4 space-y-2">
                <h3 className="text-xs font-medium text-text-secondary">Overall Result</h3>
                <p className="text-xs text-text-primary whitespace-pre-wrap">{execution.overall_result}</p>
              </div>
            )}

            {/* Error */}
            {execution.error && (
              <div className="rounded-lg border border-danger/30 bg-danger/5 p-4 space-y-2">
                <h3 className="text-xs font-medium text-danger">Error</h3>
                <p className="text-xs text-danger whitespace-pre-wrap">{execution.error}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => onExport(execution.execution_id)}>
                <Download className="size-3.5 mr-1.5" />
                Export JSON
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-text-tertiary text-center py-8">No execution selected.</p>
        )}
      </SheetContent>
    </Sheet>
  );
}
