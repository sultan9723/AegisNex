"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlarmClock,
  AlertCircle,
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FlaskConical,
  History,
  Library,
  Loader2,
  MessageSquare,
  ScrollText,
  Send,
  Shield,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, EmptyStateError } from "@/components/common/EmptyState";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { SkeletonList, SkeletonCard } from "@/components/common/Skeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  postAiChat,
  getAiHistory,
  getAiExecutions,
  getAiMemory,
  getAiTools,
  getAiWorkflows,
  getRunbooks,
  getAiTimeline,
  getAiPolicies,
  type AiChatResponse,
  type AiHistoryItem,
  type AiExecutionsResponse,
  type AiMemoryResponse,
  type AiToolsResponse,
  type AiWorkflowResponse,
  type RunbooksResponse,
  type TimelineResponse,
  type PoliciesResponse,
} from "@/lib/api";

type DashboardTab = "query" | "history" | "executions" | "memory" | "tools" | "workflows" | "timeline" | "runbooks" | "policies";

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

  const handleHistoryClick = (item: AiHistoryItem) => {
    setQuery(item.request);
    setResult({
      answer: item.result_text,
      goal_achieved: item.goal_achieved,
      confidence: item.confidence,
      steps: [],
      observations: [],
      corrections: [],
      errors: [],
      evidence: [],
      reasoning_summary: "",
      remaining_uncertainty: "",
      execution_duration_ms: 0,
      provider_used: "",
      model_used: "",
    });
    setError(null);
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

  const tabs: { key: DashboardTab; label: string; icon: React.ElementType }[] = [
    { key: "query", label: "Query", icon: Sparkles },
    { key: "history", label: "History", icon: History },
    { key: "executions", label: "Executions", icon: AlarmClock },
    { key: "memory", label: "Memory", icon: Library },
    { key: "tools", label: "Tools", icon: Braces },
    { key: "workflows", label: "Workflows", icon: FlaskConical },
    { key: "timeline", label: "Timeline", icon: Activity },
    { key: "runbooks", label: "Runbooks", icon: ScrollText },
    { key: "policies", label: "Policies", icon: Shield },
  ];

  return (
    <RouteScaffold title="AI Operations" description="Natural language interface for AegisNex operational intelligence." icon={Sparkles}>
      <div className="flex flex-wrap gap-1 border-b border-border/50 pb-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => loadTab(t.key)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === t.key ? "bg-primary/10 text-primary" : "text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <t.icon className="size-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "query" && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Query</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="flex gap-2">
                <Input
                  placeholder="Ask anything... e.g. 'Show system health' or 'Analyze recent incidents'"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={loading}
                />
                <Button type="submit" size="icon" disabled={loading || !query.trim()} aria-label="Send">
                  {loading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                </Button>
              </form>
            </CardContent>
          </Card>

          {error && <EmptyStateError message={error} onRetry={() => handleSubmit()} />}

          {loading && !result && (
            <div className="space-y-4">
              <SkeletonCard className="h-32" />
              <SkeletonList count={3} />
            </div>
          )}

            {result && !error && (
            <div ref={resultsRef} className="space-y-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle>Response</CardTitle>
                      <StatusBadge
                        status={result.goal_achieved ? "success" : "warning"}
                        label={result.goal_achieved ? "Goal achieved" : "Partial"}
                      />
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {!!(result as Record<string, unknown>).workflow && (
                        <Badge variant="outline" size="sm">WF: {(result as Record<string, unknown>).workflow as string}</Badge>
                      )}
                      {!!(result as Record<string, unknown>).runbook && (
                        <Badge variant="outline" size="sm">RB: {(result as Record<string, unknown>).runbook as string}</Badge>
                      )}
                      {(result as Record<string, unknown>).risk_score !== undefined && (result as Record<string, unknown>).risk_score !== 0 && (
                        <Badge variant={String((result as Record<string, unknown>).risk_level) === "high" || String((result as Record<string, unknown>).risk_level) === "critical" ? "danger-subtle" : "warning-subtle"} size="sm">
                          Risk: {(Number((result as Record<string, unknown>).risk_score) * 100).toFixed(0)}%
                        </Badge>
                      )}
                      {result.provider_used && (
                        <Badge variant="outline" size="sm">{result.provider_used}{result.model_used ? `/${result.model_used}` : ""}</Badge>
                      )}
                      <Badge variant="secondary">
                        {(result.confidence * 100).toFixed(0)}%
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
                    {result.answer || "No response generated."}
                  </p>
                  {result.execution_duration_ms > 0 && (
                    <p className="mt-3 text-[11px] text-text-tertiary">Completed in {result.execution_duration_ms.toFixed(0)}ms</p>
                  )}
                </CardContent>
              </Card>

              {result.evidence.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Evidence Used</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-1">
                      {result.evidence.map((e, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                          <span className="mt-1 size-1.5 shrink-0 rounded-full bg-info" />
                          {e}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {result.reasoning_summary && (
                <Card>
                  <CardHeader><CardTitle>Reasoning</CardTitle></CardHeader>
                  <CardContent>
                    <p className="text-sm text-text-primary">{result.reasoning_summary}</p>
                  </CardContent>
                </Card>
              )}

              {result.remaining_uncertainty && result.confidence < 0.6 && (
                <Card>
                  <CardHeader><CardTitle>Remaining Uncertainty</CardTitle></CardHeader>
                  <CardContent>
                    <p className="text-sm text-warning">{result.remaining_uncertainty}</p>
                  </CardContent>
                </Card>
              )}

              {result.steps.length > 0 && (
                <Card>
                  <CardHeader>
                    <button
                      type="button"
                      onClick={() => setShowDetails((v) => !v)}
                      className="flex items-center gap-2 text-left"
                    >
                      {showDetails ? <ChevronDown className="size-4 text-text-tertiary" /> : <ChevronRight className="size-4 text-text-tertiary" />}
                      <CardTitle>Execution steps</CardTitle>
                      <Badge variant="secondary" size="sm">{result.steps.length}</Badge>
                    </button>
                  </CardHeader>
                  {showDetails && (
                    <CardContent>
                      <div className="space-y-1">
                        {result.steps.map((step, i) => (
                          <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm">
                            {step.status === "ok" || step.status === "completed" ? (
                              <CheckCircle2 className="size-3.5 shrink-0 text-success" />
                            ) : step.status === "error" ? (
                              <AlertCircle className="size-3.5 shrink-0 text-danger" />
                            ) : (
                              <Clock className="size-3.5 shrink-0 text-text-tertiary" />
                            )}
                            <span className="font-mono text-xs text-text-secondary">{step.node}</span>
                            <span className="text-text-primary">{step.summary}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  )}
                </Card>
              )}

              {result.observations.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Observations</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-1">
                      {result.observations.map((obs, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                          <span className="mt-1 size-1.5 shrink-0 rounded-full bg-info" />
                          {obs}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {result.corrections.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Corrections applied</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-1">
                      {result.corrections.map((cor, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                          <span className="mt-1 size-1.5 shrink-0 rounded-full bg-warning" />
                          {cor}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {result.errors.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Errors</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-1">
                      {result.errors.map((err, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-danger">
                          <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                          {err}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {Array.isArray((result as Record<string, unknown>).policy_violations) && ((result as Record<string, unknown>).policy_violations as string[]).length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Policy Violations</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-1">
                      {((result as Record<string, unknown>).policy_violations as string[]).map((v, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-warning">
                          <Shield className="mt-0.5 size-3.5 shrink-0" />
                          {v}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {!loading && !result && !error && (
            <EmptyState
              icon={Sparkles}
              title="Ask anything about your infrastructure"
              description="Try queries like 'Show system overview', 'List running containers', 'Analyze recent incidents', or 'Check monitoring targets'."
            />
          )}
        </>
      )}

      {activeTab === "history" && (
        <Card>
          <CardHeader><CardTitle>Recent queries</CardTitle></CardHeader>
          <CardContent>
            {historyLoading ? (
              <SkeletonList count={5} />
            ) : history.length === 0 ? (
              <div className="py-8 text-center text-sm text-text-tertiary">No history yet.</div>
            ) : (
              <div className="space-y-1">
                {history.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => { setQuery(item.request); setActiveTab("query"); }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-surface-elevated"
                  >
                    <MessageSquare className="size-3.5 shrink-0 text-text-tertiary" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text-primary">{item.request}</p>
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
          </CardContent>
        </Card>
      )}

      {activeTab === "executions" && (
        <Card>
          <CardHeader><CardTitle>Execution history</CardTitle></CardHeader>
          <CardContent>
            {execLoading ? (
              <SkeletonList count={5} />
            ) : !executions ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load execution data.</div>
            ) : (
              <div className="space-y-4">
                {executions.stats && executions.stats.total > 0 && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div className="rounded-lg bg-surface-elevated px-3 py-2">
                      <p className="text-[11px] text-text-tertiary">Total</p>
                      <p className="text-lg font-semibold text-text-primary">{executions.stats.total}</p>
                    </div>
                    <div className="rounded-lg bg-surface-elevated px-3 py-2">
                      <p className="text-[11px] text-text-tertiary">Success rate</p>
                      <p className="text-lg font-semibold text-success">{(executions.stats.success_rate * 100).toFixed(0)}%</p>
                    </div>
                    <div className="rounded-lg bg-surface-elevated px-3 py-2">
                      <p className="text-[11px] text-text-tertiary">Avg confidence</p>
                      <p className="text-lg font-semibold text-text-primary">{(executions.stats.avg_confidence * 100).toFixed(0)}%</p>
                    </div>
                    <div className="rounded-lg bg-surface-elevated px-3 py-2">
                      <p className="text-[11px] text-text-tertiary">Avg duration</p>
                      <p className="text-lg font-semibold text-text-primary">{executions.stats.avg_execution_duration_ms.toFixed(0)}ms</p>
                    </div>
                  </div>
                )}
                <div className="space-y-1">
                  {executions.executions.slice(0, 10).map((ex: Record<string, unknown>, i: number) => (
                    <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm">
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
          </CardContent>
        </Card>
      )}

      {activeTab === "memory" && (
        <Card>
          <CardHeader><CardTitle>AI Memory</CardTitle></CardHeader>
          <CardContent>
            {memLoading ? (
              <SkeletonList count={5} />
            ) : !memoryData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Memory database not available.</div>
            ) : (
              <div className="space-y-1">
                {memoryData.entries.length === 0 ? (
                  <div className="py-8 text-center text-sm text-text-tertiary">No memory entries yet.</div>
                ) : (
                  memoryData.entries.slice(0, 10).map((entry: Record<string, unknown>, i: number) => (
                    <div key={i} className="rounded-lg px-3 py-2 text-sm text-text-primary">
                      <p className="truncate font-medium">{(entry.request as string) || (entry.action as string) || (entry.tool_name as string) || "-"}</p>
                      <p className="truncate text-[11px] text-text-tertiary">{entry.created_at as string}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "tools" && (
        <Card>
          <CardHeader><CardTitle>Registered Tools</CardTitle></CardHeader>
          <CardContent>
            {toolsLoading ? (
              <SkeletonList count={8} />
            ) : !toolsData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load tools.</div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {toolsData.tools.map((tool) => (
                  <div key={tool.name} className="rounded-lg border border-border/50 bg-surface-elevated/50 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-mono text-sm font-medium text-text-primary">{tool.name}</p>
                      <div className="flex items-center gap-1.5">
                        <Badge variant={tool.access_mode === "write" ? "warning" : "secondary"} size="sm">{tool.access_mode}</Badge>
                        <Badge variant={tool.risk_level === "none" ? "success-subtle" : tool.risk_level === "high" ? "danger-subtle" : "warning-subtle"} size="sm">{tool.risk_level}</Badge>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-text-secondary">{tool.description}</p>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">{tool.category} · {tool.permission_level}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "timeline" && (
        <Card>
          <CardHeader><CardTitle>AI Reasoning Timeline</CardTitle></CardHeader>
          <CardContent>
            {timelineLoading ? (
              <SkeletonList count={8} />
            ) : !timelineData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load timeline.</div>
            ) : timelineData.timeline.length === 0 ? (
              <div className="py-8 text-center text-sm text-text-tertiary">No timeline entries yet.</div>
            ) : (
              <div className="space-y-2">
                {timelineData.timeline.map((entry, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-border/50 px-3 py-2.5">
                    {entry.type === "conversation" ? (
                      <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-info" />
                    ) : (
                      <Library className="mt-0.5 size-3.5 shrink-0 text-warning" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-text-secondary">{entry.type}</span>
                        {entry.goal_achieved !== undefined && (
                          entry.goal_achieved ? <CheckCircle2 className="size-3 text-success" /> : <XCircle className="size-3 text-danger" />
                        )}
                        {entry.severity && (
                          <span className={`text-[10px] ${entry.severity === "error" ? "text-danger" : entry.severity === "warning" ? "text-warning" : "text-text-tertiary"}`}>{entry.severity}</span>
                        )}
                      </div>
                      <p className="text-sm text-text-primary">{entry.summary}</p>
                      <p className="text-[10px] text-text-tertiary">{entry.timestamp}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "runbooks" && (
        <Card>
          <CardHeader><CardTitle>Defined Runbooks</CardTitle></CardHeader>
          <CardContent>
            {runbooksLoading ? (
              <SkeletonList count={5} />
            ) : !runbooksData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load runbooks.</div>
            ) : runbooksData.runbooks.length === 0 ? (
              <div className="py-8 text-center text-sm text-text-tertiary">No runbooks defined.</div>
            ) : (
              <div className="space-y-3">
                {runbooksData.runbooks.map((rb, i) => (
                  <div key={i} className="rounded-lg border border-border/50 bg-surface-elevated/50 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-mono text-sm font-medium text-text-primary">{rb.name}</p>
                      {rb.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {rb.tags.map((tag, j) => <Badge key={j} variant="outline" size="sm">{tag}</Badge>)}
                        </div>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-text-secondary">{rb.description}</p>
                    <p className="mt-1 text-[11px] text-text-tertiary">{rb.steps.length} step{rb.steps.length !== 1 ? "s" : ""}</p>
                    <div className="mt-2 space-y-1">
                      {rb.steps.map((step, j) => (
                        <div key={j} className="flex items-center gap-2 rounded bg-surface/50 px-2 py-1 text-xs">
                          <span className="font-mono text-text-secondary">{step.name}</span>
                          <span className="text-text-tertiary">→</span>
                          <span className="text-text-primary">{step.action}{step.tool ? ` (${step.tool})` : ""}</span>
                          {step.requires_approval && <Badge variant="warning" size="sm">approval</Badge>}
                          {step.retry_count > 0 && <Badge variant="secondary" size="sm">retry:{step.retry_count}</Badge>}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "policies" && (
        <Card>
          <CardHeader><CardTitle>Organizational Policies</CardTitle></CardHeader>
          <CardContent>
            {policiesLoading ? (
              <SkeletonList count={5} />
            ) : !policiesData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load policies.</div>
            ) : policiesData.policies.length === 0 ? (
              <div className="py-8 text-center text-sm text-text-tertiary">No policies defined.</div>
            ) : (
              <div className="space-y-3">
                {policiesData.policies.map((policy, i) => (
                  <div key={i} className="rounded-lg border border-border/50 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-text-primary">{policy.name}</p>
                      <Badge variant={policy.effect === "deny" ? "destructive" : policy.effect === "require_approval" ? "warning" : "success"} size="sm">
                        {policy.effect}
                      </Badge>
                    </div>
                    <p className="text-xs text-text-secondary">{policy.description}</p>
                    <div className="mt-1 flex gap-2 text-[10px] text-text-tertiary">
                      <span>Pattern: <code className="text-text-secondary">{policy.action_pattern}</code></span>
                      <span>Condition: <code className="text-text-secondary">{policy.condition}</code></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "workflows" && (
        <Card>
          <CardHeader><CardTitle>Workflow Definition</CardTitle></CardHeader>
          <CardContent>
            {wfLoading ? (
              <SkeletonList count={5} />
            ) : !workflowsData ? (
              <div className="py-8 text-center text-sm text-text-tertiary">Unable to load workflow definition.</div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  {workflowsData.nodes.map((node) => (
                    <Badge key={node} variant="outline" size="lg">{node}</Badge>
                  ))}
                </div>
                <div className="space-y-1">
                  {workflowsData.edges.map((edge, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="font-mono text-xs text-text-secondary">{edge.from}</span>
                      <span className="text-text-tertiary">→</span>
                      <span className="font-mono text-xs text-text-secondary">{edge.to}</span>
                      {edge.condition && (
                        <span className="text-[11px] text-text-tertiary">({edge.condition})</span>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-text-tertiary">Max retries: {workflowsData.max_retries}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </RouteScaffold>
  );
}
