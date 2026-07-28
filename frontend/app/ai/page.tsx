"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity, AlertCircle, Braces, CheckCircle2, ChevronDown, ChevronRight,
  Clock, FlaskConical, History, Library, Loader2, MessageSquare, ScrollText,
  Send, Shield, Sparkles, XCircle, Zap, Brain,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, EmptyStateError } from "@/components/common/EmptyState";
import { SkeletonList, SkeletonCard } from "@/components/common/Skeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  postAiChat, getAiHistory, getAiExecutions, getAiMemory, getAiTools,
  getAiWorkflows, getRunbooks, getAiTimeline, getAiPolicies,
  type AiChatResponse, type AiHistoryItem, type AiExecutionsResponse,
  type AiMemoryResponse, type AiToolsResponse, type AiWorkflowResponse,
  type RunbooksResponse, type TimelineResponse, type PoliciesResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type DashboardTab = "query" | "history" | "executions" | "memory" | "tools" | "workflows" | "timeline" | "runbooks" | "policies";

const SUGGESTED_PROMPTS = [
  "Show me the current system health overview",
  "List all active incidents and their severity",
  "Analyze recent container restart patterns",
  "Check SSL certificate expiration status",
  "Review HTTP endpoint availability",
];

export default function AiPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AiChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AiHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [showDetails, setShowDetails] = useState(true);
  const [activeTab, setActiveTab] = useState<DashboardTab>("query");
  const resultsRef = useRef<HTMLDivElement>(null);

  const [executions, setExecutions] = useState<AiExecutionsResponse | null>(null);
  const [execLoading, setExecLoading] = useState(false);
  const [memoryData, setMemoryData] = useState<AiMemoryResponse | null>(null);
  const [memLoading, setMemLoading] = useState(false);
  const [toolsData, setToolsData] = useState<AiToolsResponse | null>(null);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [workflowsData, setWorkflowsData] = useState<AiWorkflowResponse | null>(null);
  const [wfLoading, setWfLoading] = useState(false);
  const [runbooksData, setRunbooksData] = useState<RunbooksResponse | null>(null);
  const [runbooksLoading, setRunbooksLoading] = useState(false);
  const [timelineData, setTimelineData] = useState<TimelineResponse | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [policiesData, setPoliciesData] = useState<PoliciesResponse | null>(null);
  const [policiesLoading, setPoliciesLoading] = useState(false);

  const loadHistory = useCallback(() => {
    setHistoryLoading(true);
    getAiHistory(10)
      .then((res) => setHistory(res.history))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, []);

  useEffect(loadHistory, [loadHistory]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await postAiChat(q);
      setResult(res);
      loadHistory();
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const handlePromptClick = (prompt: string) => {
    setQuery(prompt);
    setActiveTab("query");
  };

  const loadTab = (tab: DashboardTab) => {
    setActiveTab(tab);
    if (tab === "history" && !history.length) loadHistory();
    if (tab === "executions" && !executions && !execLoading) {
      setExecLoading(true);
      getAiExecutions(10).then(setExecutions).catch(() => setExecutions(null)).finally(() => setExecLoading(false));
    }
    if (tab === "memory" && !memoryData && !memLoading) {
      setMemLoading(true);
      getAiMemory().then(setMemoryData).catch(() => setMemoryData(null)).finally(() => setMemLoading(false));
    }
    if (tab === "tools" && !toolsData && !toolsLoading) {
      setToolsLoading(true);
      getAiTools().then(setToolsData).catch(() => setToolsData(null)).finally(() => setToolsLoading(false));
    }
    if (tab === "workflows" && !workflowsData && !wfLoading) {
      setWfLoading(true);
      getAiWorkflows().then(setWorkflowsData).catch(() => setWorkflowsData(null)).finally(() => setWfLoading(false));
    }
    if (tab === "runbooks" && !runbooksData && !runbooksLoading) {
      setRunbooksLoading(true);
      getRunbooks().then(setRunbooksData).catch(() => setRunbooksData(null)).finally(() => setRunbooksLoading(false));
    }
    if (tab === "timeline" && !timelineData && !timelineLoading) {
      setTimelineLoading(true);
      getAiTimeline().then(setTimelineData).catch(() => setTimelineData(null)).finally(() => setTimelineLoading(false));
    }
    if (tab === "policies" && !policiesData && !policiesLoading) {
      setPoliciesLoading(true);
      getAiPolicies().then(setPoliciesData).catch(() => setPoliciesData(null)).finally(() => setPoliciesLoading(false));
    }
  };

  const sidebarTabs: { key: DashboardTab; label: string; icon: React.ElementType }[] = [
    { key: "query", label: "Chat", icon: MessageSquare },
    { key: "history", label: "History", icon: History },
    { key: "executions", label: "Executions", icon: Activity },
    { key: "memory", label: "Memory", icon: Library },
    { key: "tools", label: "Tools", icon: Braces },
    { key: "workflows", label: "Workflows", icon: FlaskConical },
    { key: "timeline", label: "Timeline", icon: Clock },
    { key: "runbooks", label: "Runbooks", icon: ScrollText },
    { key: "policies", label: "Policies", icon: Shield },
  ];

  return (
    <div className="flex h-[calc(100vh-3rem)] animate-fade-in-up">
      {/* Sidebar tabs */}
      <div className="hidden w-48 shrink-0 border-r border-border/40 bg-surface/30 lg:flex lg:flex-col">
        <div className="border-b border-border/30 px-3 py-3">
          <div className="flex items-center gap-2">
            <div className="grid size-7 place-items-center rounded-lg bg-primary/10 text-primary">
              <Brain className="size-3.5" />
            </div>
            <div>
              <h2 className="text-xs font-bold text-text-primary">AI Workspace</h2>
              <p className="text-[10px] text-text-tertiary">Intelligence engine</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-2 custom-scrollbar">
          <div className="space-y-0.5">
            {sidebarTabs.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => loadTab(t.key)}
                  className={cn(
                    "flex h-8 w-full items-center gap-2 rounded-lg px-2.5 text-[12px] font-medium transition-all",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-text-secondary hover:bg-surface-elevated hover:text-text-primary",
                  )}
                >
                  <Icon className="size-3.5 shrink-0" />
                  <span className="truncate">{t.label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      </div>

      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile tabs */}
        <div className="flex gap-1 overflow-x-auto border-b border-border/40 px-3 py-2 lg:hidden">
          {sidebarTabs.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => loadTab(t.key)}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors",
                  activeTab === t.key
                    ? "bg-primary/10 text-primary"
                    : "text-text-secondary hover:bg-surface-elevated",
                )}
              >
                <Icon className="size-3" />
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {/* Chat tab */}
          {activeTab === "query" && (
            <div className="mx-auto max-w-3xl px-4 py-6">
              {!result && !loading && !error && (
                <div className="mb-8 text-center">
                  <div className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-primary/10 text-primary">
                    <Sparkles className="size-6" />
                  </div>
                  <h2 className="text-lg font-bold text-text-primary">What can I help you with?</h2>
                  <p className="mt-1 text-sm text-text-tertiary">
                    Ask anything about your infrastructure, incidents, or metrics.
                  </p>
                  <div className="mt-6 grid gap-2 sm:grid-cols-2">
                    {SUGGESTED_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => handlePromptClick(prompt)}
                        className="rounded-lg border border-border/40 bg-surface-elevated/40 px-3.5 py-2.5 text-left text-[12px] text-text-secondary transition-all hover:border-border/60 hover:bg-surface-elevated/60 hover:text-text-primary"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {error && <EmptyStateError message={error} onRetry={() => handleSubmit()} />}

              {loading && !result && (
                <div className="space-y-4">
                  <SkeletonCard className="h-32" />
                  <SkeletonList count={3} />
                </div>
              )}

              {result && !error && (
                <div ref={resultsRef} className="space-y-4">
                  {/* Response card */}
                  <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-5 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="grid size-7 place-items-center rounded-lg bg-primary/10 text-primary">
                          <Sparkles className="size-3.5" />
                        </div>
                        <h3 className="text-sm font-semibold text-text-primary">Response</h3>
                        <StatusBadge
                          status={result.goal_achieved ? "success" : "warning"}
                          label={result.goal_achieved ? "Goal achieved" : "Partial"}
                        />
                      </div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {result.provider_used && (
                          <Badge variant="outline" size="sm">{result.provider_used}{result.model_used ? `/${result.model_used}` : ""}</Badge>
                        )}
                        <Badge variant="secondary" size="sm">{(result.confidence * 100).toFixed(0)}%</Badge>
                      </div>
                    </div>
                    <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-text-primary">
                      {result.answer || "No response generated."}
                    </p>
                    {result.execution_duration_ms > 0 && (
                      <p className="mt-3 text-[11px] text-text-tertiary">Completed in {result.execution_duration_ms.toFixed(0)}ms</p>
                    )}
                  </div>

                  {/* Evidence */}
                  {result.evidence.length > 0 && (
                    <CollapsibleSection title="Evidence Used" count={result.evidence.length} icon={Library} color="info">
                      <ul className="space-y-1.5">
                        {result.evidence.map((e, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-text-primary">
                            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-info" />
                            {e}
                          </li>
                        ))}
                      </ul>
                    </CollapsibleSection>
                  )}

                  {/* Reasoning */}
                  {result.reasoning_summary && (
                    <CollapsibleSection title="Reasoning" icon={Brain} color="primary">
                      <p className="text-[12px] text-text-primary">{result.reasoning_summary}</p>
                    </CollapsibleSection>
                  )}

                  {/* Steps */}
                  {result.steps.length > 0 && (
                    <CollapsibleSection title="Execution Steps" count={result.steps.length} icon={Activity} color="primary" defaultOpen>
                      <div className="space-y-1">
                        {result.steps.map((step, i) => (
                          <div key={i} className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[12px]">
                            {step.status === "ok" || step.status === "completed" ? (
                              <CheckCircle2 className="size-3 shrink-0 text-success" />
                            ) : step.status === "error" ? (
                              <AlertCircle className="size-3 shrink-0 text-danger" />
                            ) : (
                              <Clock className="size-3 shrink-0 text-text-tertiary" />
                            )}
                            <span className="font-mono text-[11px] text-text-tertiary">{step.node}</span>
                            <span className="text-text-primary">{step.summary}</span>
                          </div>
                        ))}
                      </div>
                    </CollapsibleSection>
                  )}

                  {/* Observations */}
                  {result.observations.length > 0 && (
                    <CollapsibleSection title="Observations" count={result.observations.length} icon={CheckCircle2} color="info">
                      <ul className="space-y-1.5">
                        {result.observations.map((obs, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-text-primary">
                            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-info" />
                            {obs}
                          </li>
                        ))}
                      </ul>
                    </CollapsibleSection>
                  )}

                  {/* Corrections */}
                  {result.corrections.length > 0 && (
                    <CollapsibleSection title="Corrections Applied" count={result.corrections.length} icon={Zap} color="warning">
                      <ul className="space-y-1.5">
                        {result.corrections.map((cor, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-text-primary">
                            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-warning" />
                            {cor}
                          </li>
                        ))}
                      </ul>
                    </CollapsibleSection>
                  )}

                  {/* Errors */}
                  {result.errors.length > 0 && (
                    <CollapsibleSection title="Errors" count={result.errors.length} icon={AlertCircle} color="danger">
                      <ul className="space-y-1.5">
                        {result.errors.map((err, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-danger">
                            <AlertCircle className="mt-0.5 size-3 shrink-0" />
                            {err}
                          </li>
                        ))}
                      </ul>
                    </CollapsibleSection>
                  )}
                </div>
              )}

              {!loading && !result && !error && <div />}
            </div>
          )}

          {/* Chat input - fixed at bottom */}
          {activeTab === "query" && (
            <div className="sticky bottom-0 border-t border-border/40 bg-background/80 backdrop-blur-xl px-4 py-3">
              <form onSubmit={handleSubmit} className="mx-auto max-w-3xl flex gap-2">
                <Input
                  placeholder="Ask anything about your infrastructure..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={loading}
                  className="h-10 text-[13px]"
                />
                <Button type="submit" size="icon" disabled={loading || !query.trim()} className="h-10 w-10 shrink-0" aria-label="Send">
                  {loading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                </Button>
              </form>
            </div>
          )}

          {/* History tab */}
          {activeTab === "history" && (
            <TabContent title="Query History" description="Previously executed AI queries">
              {historyLoading ? (
                <SkeletonList count={5} />
              ) : history.length === 0 ? (
                <EmptyState title="No history yet" description="Execute a query to see it here." icon={History} />
              ) : (
                <div className="space-y-1">
                  {history.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => { setQuery(item.request); setActiveTab("query"); }}
                      className="flex w-full items-center gap-3 rounded-lg border border-border/20 px-3 py-2.5 text-left transition-colors hover:bg-surface-elevated/60"
                    >
                      <MessageSquare className="size-3.5 shrink-0 text-text-tertiary" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-text-primary">{item.request}</p>
                        <p className="truncate text-[11px] text-text-tertiary">{item.objective}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {item.goal_achieved ? (
                          <CheckCircle2 className="size-3.5 text-success" />
                        ) : (
                          <XCircle className="size-3.5 text-danger" />
                        )}
                        <span className="text-[11px] text-text-tertiary">{Math.round(item.confidence * 100)}%</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </TabContent>
          )}

          {/* Executions tab */}
          {activeTab === "executions" && (
            <TabContent title="Execution History" description="AI execution statistics and recent runs">
              {execLoading ? (
                <SkeletonList count={5} />
              ) : !executions ? (
                <EmptyState title="Unable to load executions" description="Execution data not available." icon={Activity} />
              ) : (
                <div className="space-y-4">
                  {executions.stats && executions.stats.total > 0 && (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <StatCard label="Total" value={String(executions.stats.total)} />
                      <StatCard label="Success Rate" value={`${(executions.stats.success_rate * 100).toFixed(0)}%`} color="text-success" />
                      <StatCard label="Avg Confidence" value={`${(executions.stats.avg_confidence * 100).toFixed(0)}%`} />
                      <StatCard label="Avg Duration" value={`${executions.stats.avg_execution_duration_ms.toFixed(0)}ms`} />
                    </div>
                  )}
                  <div className="space-y-1">
                    {executions.executions.slice(0, 10).map((ex: Record<string, unknown>, i: number) => (
                      <div key={i} className="flex items-center gap-3 rounded-lg border border-border/20 px-3 py-2 text-[12px]">
                        {ex.goal_achieved ? (
                          <CheckCircle2 className="size-3.5 shrink-0 text-success" />
                        ) : (
                          <XCircle className="size-3.5 shrink-0 text-danger" />
                        )}
                        <span className="min-w-0 flex-1 truncate text-text-primary">{(ex.request as string) || ""}</span>
                        <span className="shrink-0 text-text-tertiary">{((ex.confidence as number) * 100 || 0).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </TabContent>
          )}

          {/* Memory tab */}
          {activeTab === "memory" && (
            <TabContent title="AI Memory" description="Stored knowledge from past interactions">
              {memLoading ? (
                <SkeletonList count={5} />
              ) : !memoryData ? (
                <EmptyState title="Memory not available" description="Memory database not available." icon={Library} />
              ) : memoryData.entries.length === 0 ? (
                <EmptyState title="No memory entries" description="Entries will appear as the AI learns." icon={Library} />
              ) : (
                <div className="space-y-1">
                  {memoryData.entries.slice(0, 10).map((entry: Record<string, unknown>, i: number) => (
                    <div key={i} className="rounded-lg border border-border/20 px-3 py-2.5">
                      <p className="truncate text-[13px] font-medium text-text-primary">{(entry.request as string) || (entry.action as string) || (entry.tool_name as string) || "-"}</p>
                      <p className="truncate text-[10px] text-text-tertiary">{entry.created_at as string}</p>
                    </div>
                  ))}
                </div>
              )}
            </TabContent>
          )}

          {/* Tools tab */}
          {activeTab === "tools" && (
            <TabContent title="Registered Tools" description="Available AI tools and their capabilities">
              {toolsLoading ? (
                <SkeletonList count={8} />
              ) : !toolsData ? (
                <EmptyState title="Unable to load tools" description="Tool registry not available." icon={Braces} />
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {toolsData.tools.map((tool) => (
                    <div key={tool.name} className="rounded-xl border border-border/40 bg-surface-elevated/40 px-4 py-3 transition-all hover:border-border/60">
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-mono text-[13px] font-semibold text-text-primary">{tool.name}</p>
                        <div className="flex items-center gap-1">
                          <Badge variant={tool.access_mode === "write" ? "warning-subtle" : "secondary"} size="sm">{tool.access_mode}</Badge>
                          <Badge variant={tool.risk_level === "none" ? "success-subtle" : tool.risk_level === "high" ? "danger-subtle" : "warning-subtle"} size="sm">{tool.risk_level}</Badge>
                        </div>
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary">{tool.description}</p>
                      <p className="mt-1 text-[10px] text-text-tertiary">{tool.category} \u00b7 {tool.permission_level}</p>
                    </div>
                  ))}
                </div>
              )}
            </TabContent>
          )}

          {/* Workflows tab */}
          {activeTab === "workflows" && (
            <TabContent title="Workflow Definition" description="AI orchestration workflow graph">
              {wfLoading ? (
                <SkeletonList count={5} />
              ) : !workflowsData ? (
                <EmptyState title="Unable to load workflows" description="Workflow definition not available." icon={FlaskConical} />
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {workflowsData.nodes.map((node) => (
                      <Badge key={node} variant="outline" size="lg">{node}</Badge>
                    ))}
                  </div>
                  <div className="space-y-1">
                    {workflowsData.edges.map((edge, i) => (
                      <div key={i} className="flex items-center gap-2 rounded-lg border border-border/20 px-3 py-2 text-[12px]">
                        <span className="font-mono text-text-secondary">{edge.from}</span>
                        <span className="text-text-tertiary">\u2192</span>
                        <span className="font-mono text-text-secondary">{edge.to}</span>
                        {edge.condition && (
                          <span className="text-[11px] text-text-tertiary">({edge.condition})</span>
                        )}
                      </div>
                    ))}
                  </div>
                  <p className="text-[11px] text-text-tertiary">Max retries: {workflowsData.max_retries}</p>
                </div>
              )}
            </TabContent>
          )}

          {/* Timeline tab */}
          {activeTab === "timeline" && (
            <TabContent title="Reasoning Timeline" description="AI decision-making audit trail">
              {timelineLoading ? (
                <SkeletonList count={8} />
              ) : !timelineData ? (
                <EmptyState title="Unable to load timeline" description="Timeline data not available." icon={Clock} />
              ) : timelineData.timeline.length === 0 ? (
                <EmptyState title="No timeline entries" description="Entries will appear as the AI processes requests." icon={Clock} />
              ) : (
                <div className="space-y-2">
                  {timelineData.timeline.map((entry, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-xl border border-border/30 bg-surface-elevated/30 px-4 py-3">
                      {entry.type === "conversation" ? (
                        <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-info" />
                      ) : (
                        <Library className="mt-0.5 size-3.5 shrink-0 text-warning" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-semibold text-text-secondary">{entry.type}</span>
                          {entry.goal_achieved !== undefined && (
                            entry.goal_achieved ? <CheckCircle2 className="size-3 text-success" /> : <XCircle className="size-3 text-danger" />
                          )}
                        </div>
                        <p className="text-[13px] text-text-primary">{entry.summary}</p>
                        <p className="text-[10px] text-text-tertiary">{entry.timestamp}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabContent>
          )}

          {/* Runbooks tab */}
          {activeTab === "runbooks" && (
            <TabContent title="Runbooks" description="Predefined operational playbooks">
              {runbooksLoading ? (
                <SkeletonList count={5} />
              ) : !runbooksData ? (
                <EmptyState title="Unable to load runbooks" description="Runbook data not available." icon={ScrollText} />
              ) : runbooksData.runbooks.length === 0 ? (
                <EmptyState title="No runbooks defined" description="Create runbooks to automate operational workflows." icon={ScrollText} />
              ) : (
                <div className="space-y-3">
                  {runbooksData.runbooks.map((rb, i) => (
                    <div key={i} className="rounded-xl border border-border/40 bg-surface-elevated/40 px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-mono text-[13px] font-semibold text-text-primary">{rb.name}</p>
                        {rb.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {rb.tags.map((tag, j) => <Badge key={j} variant="outline" size="sm">{tag}</Badge>)}
                          </div>
                        )}
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary">{rb.description}</p>
                      <p className="mt-1 text-[10px] text-text-tertiary">{rb.steps.length} step{rb.steps.length !== 1 ? "s" : ""}</p>
                      <div className="mt-2 space-y-1">
                        {rb.steps.map((step, j) => (
                          <div key={j} className="flex items-center gap-2 rounded-lg bg-surface/50 px-2.5 py-1.5 text-[11px]">
                            <span className="font-mono text-text-secondary">{step.name}</span>
                            <span className="text-text-tertiary">\u2192</span>
                            <span className="text-text-primary">{step.action}{step.tool ? ` (${step.tool})` : ""}</span>
                            {step.requires_approval && <Badge variant="warning-subtle" size="sm">approval</Badge>}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabContent>
          )}

          {/* Policies tab */}
          {activeTab === "policies" && (
            <TabContent title="Policies" description="Organizational guardrails and constraints">
              {policiesLoading ? (
                <SkeletonList count={5} />
              ) : !policiesData ? (
                <EmptyState title="Unable to load policies" description="Policy data not available." icon={Shield} />
              ) : policiesData.policies.length === 0 ? (
                <EmptyState title="No policies defined" description="Define policies to enforce organizational guardrails." icon={Shield} />
              ) : (
                <div className="space-y-3">
                  {policiesData.policies.map((policy, i) => (
                    <div key={i} className="rounded-xl border border-border/40 bg-surface-elevated/40 px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[13px] font-semibold text-text-primary">{policy.name}</p>
                        <Badge variant={policy.effect === "deny" ? "danger-subtle" : policy.effect === "require_approval" ? "warning-subtle" : "success-subtle"} size="sm">
                          {policy.effect}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary">{policy.description}</p>
                      <div className="mt-2 flex gap-3 text-[10px] text-text-tertiary">
                        <span>Pattern: <code className="text-text-secondary">{policy.action_pattern}</code></span>
                        <span>Condition: <code className="text-text-secondary">{policy.condition}</code></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabContent>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Shared presentational components ── */

function CollapsibleSection({
  title, count, icon: Icon, color, defaultOpen = false, children,
}: {
  title: string; count?: number; icon: React.ElementType;
  color: "primary" | "info" | "warning" | "danger"; defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const colorMap = {
    primary: "bg-primary/10 text-primary",
    info: "bg-info/10 text-info",
    warning: "bg-warning/10 text-warning",
    danger: "bg-danger/10 text-danger",
  };
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-surface-elevated/40"
      >
        <div className={cn("grid size-6 place-items-center rounded-lg", colorMap[color])}>
          <Icon className="size-3" />
        </div>
        <span className="text-[13px] font-semibold text-text-primary">{title}</span>
        {count !== undefined && (
          <Badge variant="secondary" size="sm">{count}</Badge>
        )}
        {open ? <ChevronDown className="ml-auto size-3.5 text-text-tertiary" /> : <ChevronRight className="ml-auto size-3.5 text-text-tertiary" />}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

function TabContent({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-5">
        <h2 className="text-base font-bold text-text-primary">{title}</h2>
        <p className="mt-0.5 text-xs text-text-tertiary">{description}</p>
      </div>
      {children}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl border border-border/30 bg-surface-elevated/40 px-3.5 py-2.5">
      <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</p>
      <p className={cn("mt-0.5 text-lg font-bold text-text-primary", color)}>{value}</p>
    </div>
  );
}
