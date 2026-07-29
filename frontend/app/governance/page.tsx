"use client";

import { useCallback, useEffect, useState } from "react";
import { buildApiUrl } from "@/lib/api";
import {
  Activity, AlertTriangle, Eye, Ban, CheckCircle,
  Clock, ShieldCheck, Bot, RefreshCw, Plus, Lock,
  X,
} from "lucide-react";

type Agent = {
  agent_id: string;
  id?: string;
  name: string;
  agent_type: string;
  description: string;
  owner: string;
  team: string;
  department: string;
  purpose: string;
  provider: string;
  model: string;
  version: string;
  status: string;
  risk_level: string;
  trust_score: number;
  daily_budget: number;
  monthly_budget: number;
  average_cost: number;
  average_latency: number;
  success_rate: number;
  permissions: string[];
  connected_tools: string[];
  policies: string[];
  approval_required: boolean;
  allowed_tools: string[];
  allowed_resources: string[];
  max_actions_per_hour: number;
  total_actions: number;
  execution_count?: number;
  total_denied: number;
  total_anomalies: number;
  created_at: string;
  last_active_at: string | null;
  last_execution?: string | null;
};

type AgentAction = {
  action_id: string;
  agent_id: string;
  action_type: string;
  action_summary: string;
  target_resource: string;
  reasoning: string;
  confidence_score: number;
  policy_verdict: string;
  status: string;
  duration_ms: number;
  created_at: string;
};

type Policy = {
  policy_id: number;
  name: string;
  description: string;
  policy_type: string;
  target_agents: string[];
  conditions: Record<string, unknown>;
  effect: string;
  priority: number;
  enabled: boolean;
  created_at: string;
};

type Anomaly = {
  anomaly_id: number;
  agent_id: string;
  anomaly_type: string;
  description: string;
  severity: string;
  evidence: Record<string, unknown>;
  status: string;
  detected_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
};

type Approval = {
  approval_id: string;
  request_type: string;
  requester: string;
  summary: string;
  details: Record<string, unknown> | string;
  status: string;
  created_at: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
};

type Stats = {
  total_agents: number;
  active_agents: number;
  by_risk: Record<string, number>;
  by_type: Record<string, number>;
  total_actions: number;
  total_denied: number;
  open_anomalies: number;
  avg_trust_score: number;
};

type AgentMetrics = {
  agent_id: string;
  execution_count: number;
  history_count: number;
  success_rate: number;
  average_cost: number;
  average_latency: number;
  average_confidence: number;
  denied_count: number;
  trust_score: number;
  daily_budget: number;
  monthly_budget: number;
  last_execution: string | null;
};

type AgentTools = {
  agent_id: string;
  tools: string[];
  permissions: string[];
  resources: string[];
};

type Tab = "overview" | "agents" | "actions" | "policies" | "approvals" | "anomalies";

type PolicyDraft = {
  name: string;
  description: string;
  policy_type: string;
  target_agents: string;
  conditions: string;
  effect: string;
  priority: string;
};

const RISK_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
  low: "bg-green-50 text-green-700 border-green-200",
  unknown: "bg-gray-50 text-gray-500 border-gray-200",
};

const VERDICT_COLORS: Record<string, string> = {
  allowed: "bg-green-50 text-green-700 border-green-200",
  denied: "bg-red-50 text-red-700 border-red-200",
  pending_approval: "bg-amber-50 text-amber-700 border-amber-200",
  anomalous: "bg-purple-50 text-purple-700 border-purple-200",
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-50 text-orange-700",
  medium: "bg-yellow-50 text-yellow-700",
  low: "bg-blue-50 text-blue-700",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-50 text-green-700 border-green-200",
  inactive: "bg-gray-50 text-gray-500 border-gray-200",
  suspended: "bg-red-50 text-red-700 border-red-200",
  decommissioned: "bg-gray-50 text-gray-400 border-gray-200",
  open: "bg-red-50 text-red-700 border-red-200",
  investigating: "bg-amber-50 text-amber-700 border-amber-200",
  resolved: "bg-green-50 text-green-700 border-green-200",
  false_positive: "bg-gray-50 text-gray-500 border-gray-200",
};

function Badge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${className}`}>
      {children}
    </span>
  );
}

function StatCard({ label, value, icon: Icon, color = "text-blue-600", sub }: {
  label: string; value: string | number; icon: React.ElementType; color?: string; sub?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`grid size-9 place-items-center rounded-lg bg-muted/50`}>
            <Icon className={`size-4 ${color}`} />
          </div>
          <div>
            <p className="text-[22px] font-bold tracking-tight text-text-primary">{value}</p>
            <p className="text-[11px] text-text-tertiary">{label}</p>
          </div>
        </div>
        {sub && <p className="text-[10px] text-text-tertiary">{sub}</p>}
      </div>
    </div>
  );
}

function TrustBar({ score }: { score: number }) {
  const color = score >= 70 ? "bg-green-500" : score >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-muted">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
      <span className="text-[10px] text-text-tertiary">{score.toFixed(0)}</span>
    </div>
  );
}

function TimeAgo({ date }: { date: string | null }) {
  if (!date) return <span className="text-text-disabled">Never</span>;
  const d = new Date(date);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return <span className="text-text-tertiary">Just now</span>;
  if (diffMin < 60) return <span className="text-text-tertiary">{diffMin}m ago</span>;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return <span className="text-text-tertiary">{diffH}h ago</span>;
  return <span className="text-text-tertiary">{Math.floor(diffH / 24)}d ago</span>;
}

export default function GovernancePage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<Stats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState<string>("all");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedAgentHistory, setSelectedAgentHistory] = useState<AgentAction[]>([]);
  const [selectedAgentPolicies, setSelectedAgentPolicies] = useState<Policy[]>([]);
  const [selectedAgentTools, setSelectedAgentTools] = useState<AgentTools | null>(null);
  const [selectedAgentMetrics, setSelectedAgentMetrics] = useState<AgentMetrics | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [editingPolicyName, setEditingPolicyName] = useState<string | null>(null);
  const [policyDraft, setPolicyDraft] = useState<PolicyDraft>({
    name: "",
    description: "",
    policy_type: "access_control",
    target_agents: "*",
    conditions: "{}",
    effect: "approve",
    priority: "50",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, agentsRes, actionsRes, policiesRes, approvalsRes, anomaliesRes] = await Promise.allSettled([
        fetch(buildApiUrl("/governance/stats")).then((r) => r.json()),
        fetch(buildApiUrl("/governance/agents")).then((r) => r.json()),
        fetch(buildApiUrl("/governance/actions?limit=200")).then((r) => r.json()),
        fetch(buildApiUrl("/governance/policies")).then((r) => r.json()),
        fetch(buildApiUrl("/approvals?status=pending&limit=25")).then((r) => r.json()),
        fetch(buildApiUrl("/governance/anomalies?limit=100")).then((r) => r.json()),
      ]);
      if (statsRes.status === "fulfilled") setStats(statsRes.value);
      if (agentsRes.status === "fulfilled") setAgents(agentsRes.value.agents || []);
      if (actionsRes.status === "fulfilled") setActions(actionsRes.value.actions || []);
      if (policiesRes.status === "fulfilled") setPolicies(policiesRes.value.policies || []);
      if (approvalsRes.status === "fulfilled") setApprovals(approvalsRes.value.approvals || []);
      if (anomaliesRes.status === "fulfilled") setAnomalies(anomaliesRes.value.anomalies || []);
    } catch {
      // Network error — show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openAgentDrawer = useCallback(async (agentId: string) => {
    setSelectedAgentId(agentId);
    setDrawerLoading(true);
    const fallbackAgent = agents.find((agent) => agent.agent_id === agentId) || null;
    setSelectedAgent(fallbackAgent);
    try {
      const [detailRes, historyRes, policiesRes, toolsRes, metricsRes] = await Promise.all([
        fetch(buildApiUrl(`/governance/agents/${encodeURIComponent(agentId)}`)).then((r) => r.json()),
        fetch(buildApiUrl(`/governance/agents/${encodeURIComponent(agentId)}/history?limit=8`)).then((r) => r.json()),
        fetch(buildApiUrl(`/governance/agents/${encodeURIComponent(agentId)}/policies`)).then((r) => r.json()),
        fetch(buildApiUrl(`/governance/agents/${encodeURIComponent(agentId)}/tools`)).then((r) => r.json()),
        fetch(buildApiUrl(`/governance/agents/${encodeURIComponent(agentId)}/metrics`)).then((r) => r.json()),
      ]);
      setSelectedAgent(detailRes);
      setSelectedAgentHistory(historyRes.history || []);
      setSelectedAgentPolicies(policiesRes.policies || []);
      setSelectedAgentTools(toolsRes);
      setSelectedAgentMetrics(metricsRes);
    } catch {
      setNotice("Failed to load agent details");
    } finally {
      setDrawerLoading(false);
    }
  }, [agents]);

  const closeAgentDrawer = () => {
    setSelectedAgentId(null);
    setSelectedAgent(null);
    setSelectedAgentHistory([]);
    setSelectedAgentPolicies([]);
    setSelectedAgentTools(null);
    setSelectedAgentMetrics(null);
  };

  const postJson = async (path: string, method: "POST" | "PUT" | "DELETE", body?: unknown) => {
    const response = await fetch(buildApiUrl(path), {
      method,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    return response.json();
  };

  const resetPolicyDraft = () => {
    setEditingPolicyName(null);
    setPolicyDraft({ name: "", description: "", policy_type: "access_control", target_agents: "*", conditions: "{}", effect: "approve", priority: "50" });
  };

  const editPolicy = (policy: Policy) => {
    setEditingPolicyName(policy.name);
    setPolicyDraft({
      name: policy.name,
      description: policy.description,
      policy_type: policy.policy_type,
      target_agents: (policy.target_agents || ["*"]).join(", "),
      conditions: JSON.stringify(policy.conditions || {}),
      effect: policy.effect,
      priority: String(policy.priority),
    });
  };

  const handleSavePolicy = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const conditions = JSON.parse(policyDraft.conditions || "{}");
      const target_agents = policyDraft.target_agents
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
      const payload = {
        name: policyDraft.name.trim(),
        description: policyDraft.description.trim(),
        policy_type: policyDraft.policy_type,
        target_agents: target_agents.length ? target_agents : ["*"],
        conditions,
        effect: policyDraft.effect,
        priority: Number(policyDraft.priority || 50),
        enabled: true,
      };
      if (editingPolicyName) {
        await postJson(`/governance/policies/${encodeURIComponent(editingPolicyName)}`, "PUT", payload);
        setNotice("Policy updated");
      } else {
        await postJson("/governance/policies", "POST", payload);
        setNotice("Policy created");
      }
      resetPolicyDraft();
      await fetchData();
    } catch (error) {
      setNotice(error instanceof SyntaxError ? "Conditions must be valid JSON" : "Failed to create policy");
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePolicy = async (name: string) => {
    setSaving(true);
    setNotice(null);
    try {
      await postJson(`/governance/policies/${encodeURIComponent(name)}`, "DELETE");
      if (editingPolicyName === name) resetPolicyDraft();
      setNotice("Policy deleted");
      await fetchData();
    } catch {
      setNotice("Failed to delete policy");
    } finally {
      setSaving(false);
    }
  };

  const handleApproval = async (approvalId: string, decision: "approved" | "rejected") => {
    setSaving(true);
    setNotice(null);
    try {
      await postJson(`/approvals/${encodeURIComponent(approvalId)}/respond`, "POST", { decision });
      setNotice(decision === "approved" ? "Approval accepted" : "Approval rejected");
      await fetchData();
    } catch {
      setNotice("Failed to update approval");
    } finally {
      setSaving(false);
    }
  };

  const handleResolveAnomaly = async (anomalyId: number, status: "resolved" | "false_positive" = "resolved") => {
    setSaving(true);
    setNotice(null);
    try {
      await postJson(`/governance/anomalies/${anomalyId}/resolve`, "PUT", { status });
      setNotice(status === "resolved" ? "Anomaly resolved" : "Anomaly marked false positive");
      await fetchData();
    } catch {
      setNotice("Failed to update anomaly");
    } finally {
      setSaving(false);
    }
  };

  const filteredActions = actionFilter === "all" ? actions : actions.filter((a) => a.policy_verdict === actionFilter);

  const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
    { key: "overview", label: "Overview", icon: Eye },
    { key: "agents", label: "Agent Registry", icon: Bot },
    { key: "actions", label: "Action Audit", icon: Activity },
    { key: "policies", label: "Policies", icon: Lock },
    { key: "approvals", label: "Approvals", icon: Clock },
    { key: "anomalies", label: "Anomalies", icon: AlertTriangle },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-text-primary">AI Governance</h1>
          <p className="mt-1 text-[13px] text-text-secondary">
            Registry, audit trail, and policy enforcement for all AI agents
          </p>
        </div>
        <button
          onClick={fetchData}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-[12px] font-medium text-text-secondary transition-colors hover:bg-surface-elevated hover:text-text-primary"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {notice && (
        <div className="rounded-lg border border-border bg-surface px-3 py-2 text-[12px] text-text-secondary">
          {notice}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-xl border border-border bg-surface p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all ${
              tab === t.key
                ? "bg-background text-text-primary shadow-sm"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            <t.icon className="size-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Registered Agents" value={stats?.total_agents ?? 0} icon={Bot} color="text-blue-600" sub={`${stats?.active_agents ?? 0} active`} />
            <StatCard label="Total Actions" value={stats?.total_actions ?? 0} icon={Activity} color="text-emerald-600" />
            <StatCard label="Open Anomalies" value={stats?.open_anomalies ?? 0} icon={AlertTriangle} color={((stats?.open_anomalies ?? 0) > 0) ? "text-red-600" : "text-emerald-600"} />
            <StatCard label="Avg Trust Score" value={`${stats?.avg_trust_score ?? 50}`} icon={ShieldCheck} color="text-violet-600" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Risk Distribution */}
            <div className="rounded-xl border border-border bg-surface p-5">
              <h3 className="mb-4 text-[13px] font-semibold text-text-primary">Risk Distribution</h3>
              <div className="space-y-3">
                {(["critical", "high", "medium", "low", "unknown"] as const).map((risk) => {
                  const count = stats?.by_risk?.[risk] ?? 0;
                  const total = stats?.total_agents ?? 1;
                  const pct = total > 0 ? (count / total) * 100 : 0;
                  return (
                    <div key={risk} className="flex items-center gap-3">
                      <span className="w-16 text-[11px] font-medium text-text-secondary capitalize">{risk}</span>
                      <div className="flex-1 h-2 rounded-full bg-muted">
                        <div className={`h-full rounded-full ${RISK_COLORS[risk]?.includes("red") ? "bg-red-500" : RISK_COLORS[risk]?.includes("orange") ? "bg-orange-500" : RISK_COLORS[risk]?.includes("yellow") ? "bg-yellow-500" : RISK_COLORS[risk]?.includes("green") ? "bg-green-500" : "bg-gray-400"}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-8 text-right text-[11px] text-text-tertiary">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Agent Types */}
            <div className="rounded-xl border border-border bg-surface p-5">
              <h3 className="mb-4 text-[13px] font-semibold text-text-primary">Agent Types</h3>
              <div className="space-y-2">
                {Object.entries(stats?.by_type ?? {}).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Bot className="size-3.5 text-blue-500" />
                      <span className="text-[12px] font-medium text-text-primary capitalize">{type}</span>
                    </div>
                    <span className="text-[11px] text-text-tertiary">{count}</span>
                  </div>
                ))}
                {Object.keys(stats?.by_type ?? {}).length === 0 && (
                  <p className="py-4 text-center text-[12px] text-text-tertiary">No agents registered yet</p>
                )}
              </div>
            </div>
          </div>

          {/* Recent Actions */}
          <div className="rounded-xl border border-border bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-[13px] font-semibold text-text-primary">Recent Actions</h3>
              <button onClick={() => setTab("actions")} className="text-[11px] text-blue-600 hover:text-blue-700">View all</button>
            </div>
            {actions.length === 0 ? (
              <p className="py-6 text-center text-[12px] text-text-tertiary">No actions recorded yet</p>
            ) : (
              <div className="space-y-1">
                {actions.slice(0, 8).map((a) => (
                  <div key={a.action_id} className="flex items-center gap-3 rounded-lg px-3 py-2 text-[12px] hover:bg-muted/30">
                    <Badge className={VERDICT_COLORS[a.policy_verdict] || ""}>{a.policy_verdict}</Badge>
                    <span className="font-medium text-text-primary">{a.agent_id}</span>
                    <span className="flex-1 truncate text-text-secondary">{a.action_summary}</span>
                    <span className="text-text-tertiary">{a.target_resource}</span>
                    <TimeAgo date={a.created_at} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Agents Tab */}
      {tab === "agents" && (
        <div className="space-y-4">
          {agents.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-12 text-center">
              <Bot className="mx-auto mb-3 size-10 text-text-disabled" />
              <p className="text-[13px] font-medium text-text-primary">No agents registered</p>
              <p className="mt-1 text-[12px] text-text-tertiary">Register AI agents to track their actions, policies, and anomalies</p>
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-surface">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div>
                  <h3 className="text-[13px] font-semibold text-text-primary">Registered agents</h3>
                  <p className="text-[11px] text-text-tertiary">{agents.length} governed agents with budgets, policies, and tool access</p>
                </div>
                <Badge className="bg-blue-50 text-blue-700 border-blue-200">Enterprise registry</Badge>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[980px] text-[12px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Agent</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Owner</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Model</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Risk</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Trust</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Budget</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Success</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Executions</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Last run</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {agents.map((agent) => (
                      <tr
                        key={agent.agent_id}
                        onClick={() => openAgentDrawer(agent.agent_id)}
                        className="cursor-pointer transition-colors hover:bg-muted/20"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="grid size-8 place-items-center rounded-lg bg-blue-50">
                              <Bot className="size-4 text-blue-600" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-text-primary">{agent.name}</span>
                                {agent.approval_required && <Badge className="bg-amber-50 text-amber-700 border-amber-200">approval</Badge>}
                              </div>
                              <p className="max-w-[280px] truncate font-mono text-[10px] text-text-tertiary">{agent.agent_id}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-text-primary">{agent.owner}</p>
                          <p className="text-[10px] text-text-tertiary">{agent.department || agent.team}</p>
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-text-primary">{agent.model}</p>
                          <p className="text-[10px] text-text-tertiary">{agent.provider} / v{agent.version}</p>
                        </td>
                        <td className="px-4 py-3"><Badge className={RISK_COLORS[agent.risk_level] || ""}>{agent.risk_level}</Badge></td>
                        <td className="px-4 py-3"><TrustBar score={agent.trust_score} /></td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-text-primary">${agent.monthly_budget.toLocaleString()}</p>
                          <p className="text-[10px] text-text-tertiary">${agent.daily_budget}/day</p>
                        </td>
                        <td className="px-4 py-3 text-text-primary">{agent.success_rate.toFixed(1)}%</td>
                        <td className="px-4 py-3 text-text-primary">{agent.execution_count ?? agent.total_actions}</td>
                        <td className="px-4 py-3"><TimeAgo date={agent.last_execution || agent.last_active_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {selectedAgentId && selectedAgent && (
            <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={closeAgentDrawer}>
              <aside
                className="h-full w-full max-w-[560px] overflow-y-auto border-l border-border bg-background shadow-2xl transition-transform"
                onClick={(event) => event.stopPropagation()}
                aria-label="Agent details"
              >
                <div className="sticky top-0 z-10 border-b border-border bg-background/95 px-6 py-4 backdrop-blur">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-semibold text-text-primary">{selectedAgent.name}</h2>
                        <Badge className={STATUS_COLORS[selectedAgent.status] || ""}>{selectedAgent.status}</Badge>
                      </div>
                      <p className="mt-1 font-mono text-[11px] text-text-tertiary">{selectedAgent.agent_id}</p>
                    </div>
                    <button
                      onClick={closeAgentDrawer}
                      className="grid size-8 place-items-center rounded-lg border border-border text-text-tertiary hover:bg-muted/40 hover:text-text-primary"
                      aria-label="Close agent details"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                </div>

                <div className="space-y-5 px-6 py-5">
                  {drawerLoading && <p className="text-[12px] text-text-tertiary">Loading agent details...</p>}

                  <section className="space-y-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Overview</p>
                    <p className="text-[13px] leading-6 text-text-secondary">{selectedAgent.purpose || selectedAgent.description}</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        ["Owner", selectedAgent.owner],
                        ["Department", selectedAgent.department || selectedAgent.team],
                        ["Provider", selectedAgent.provider],
                        ["Model", selectedAgent.model],
                        ["Version", selectedAgent.version],
                        ["Status", selectedAgent.status],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-lg border border-border bg-surface px-3 py-2">
                          <p className="text-[10px] text-text-tertiary">{label}</p>
                          <p className="mt-1 truncate text-[12px] font-medium text-text-primary">{value}</p>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-border bg-surface px-3 py-3">
                      <p className="text-[10px] text-text-tertiary">Monthly budget</p>
                      <p className="mt-1 text-[18px] font-semibold text-text-primary">${selectedAgent.monthly_budget.toLocaleString()}</p>
                      <p className="text-[10px] text-text-tertiary">${selectedAgent.daily_budget}/day</p>
                    </div>
                    <div className="rounded-lg border border-border bg-surface px-3 py-3">
                      <p className="text-[10px] text-text-tertiary">Trust score</p>
                      <div className="mt-2"><TrustBar score={selectedAgent.trust_score} /></div>
                      <Badge className={`mt-2 ${RISK_COLORS[selectedAgent.risk_level] || ""}`}>{selectedAgent.risk_level}</Badge>
                    </div>
                  </section>

                  <section className="grid grid-cols-3 gap-3">
                    <div className="rounded-lg border border-border bg-surface px-3 py-3">
                      <p className="text-[10px] text-text-tertiary">Success</p>
                      <p className="mt-1 text-[15px] font-semibold text-text-primary">{(selectedAgentMetrics?.success_rate ?? selectedAgent.success_rate).toFixed(1)}%</p>
                    </div>
                    <div className="rounded-lg border border-border bg-surface px-3 py-3">
                      <p className="text-[10px] text-text-tertiary">Avg latency</p>
                      <p className="mt-1 text-[15px] font-semibold text-text-primary">{Math.round(selectedAgentMetrics?.average_latency ?? selectedAgent.average_latency)}ms</p>
                    </div>
                    <div className="rounded-lg border border-border bg-surface px-3 py-3">
                      <p className="text-[10px] text-text-tertiary">Avg cost</p>
                      <p className="mt-1 text-[15px] font-semibold text-text-primary">${(selectedAgentMetrics?.average_cost ?? selectedAgent.average_cost).toFixed(3)}</p>
                    </div>
                  </section>

                  <section className="space-y-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Policies</p>
                    <div className="flex flex-wrap gap-1.5">
                      {(selectedAgentPolicies.length ? selectedAgentPolicies.map((policy) => policy.name) : selectedAgent.policies || []).map((policy) => (
                        <Badge key={policy} className="bg-amber-50 text-amber-700 border-amber-200">{policy}</Badge>
                      ))}
                    </div>
                  </section>

                  <section className="space-y-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Connected tools</p>
                    <div className="flex flex-wrap gap-1.5">
                      {((selectedAgentTools?.tools?.length ? selectedAgentTools.tools : selectedAgent.connected_tools) || []).map((tool) => (
                        <Badge key={tool} className="bg-blue-50 text-blue-700 border-blue-200">{tool}</Badge>
                      ))}
                    </div>
                  </section>

                  <section className="space-y-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Permissions</p>
                    <div className="flex flex-wrap gap-1.5">
                      {((selectedAgentTools?.permissions?.length ? selectedAgentTools.permissions : selectedAgent.permissions) || []).map((permission) => (
                        <Badge key={permission} className="bg-violet-50 text-violet-700 border-violet-200">{permission}</Badge>
                      ))}
                    </div>
                  </section>

                  <section className="space-y-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Recent execution history</p>
                    <div className="divide-y divide-border rounded-lg border border-border bg-surface">
                      {selectedAgentHistory.length === 0 ? (
                        <p className="px-3 py-4 text-center text-[12px] text-text-tertiary">No execution history recorded</p>
                      ) : (
                        selectedAgentHistory.map((item) => (
                          <div key={item.action_id} className="px-3 py-2.5">
                            <div className="flex items-center justify-between gap-3">
                              <p className="truncate text-[12px] font-medium text-text-primary">{item.action_summary}</p>
                              <Badge className={VERDICT_COLORS[item.policy_verdict] || ""}>{item.policy_verdict}</Badge>
                            </div>
                            <div className="mt-1 flex items-center gap-3 text-[10px] text-text-tertiary">
                              <span>{item.action_type}</span>
                              <span>{Math.round(item.duration_ms)}ms</span>
                              <TimeAgo date={item.created_at} />
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </section>
                </div>
              </aside>
            </div>
          )}
        </div>
      )}

      {/* Actions Tab */}
      {tab === "actions" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {(["all", "allowed", "denied", "pending_approval", "anomalous"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setActionFilter(v)}
                className={`rounded-lg px-3 py-1.5 text-[11px] font-medium transition-colors ${
                  actionFilter === v ? "bg-text-primary text-background" : "bg-surface text-text-tertiary hover:text-text-secondary border border-border"
                }`}
              >
                {v === "all" ? "All" : v.replace("_", " ")}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-text-tertiary">{filteredActions.length} actions</span>
          </div>

          {filteredActions.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-12 text-center">
              <Activity className="mx-auto mb-3 size-10 text-text-disabled" />
              <p className="text-[13px] font-medium text-text-primary">No actions recorded</p>
              <p className="mt-1 text-[12px] text-text-tertiary">Actions will appear here as agents execute tasks</p>
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-surface overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Verdict</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Agent</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Action</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Target</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Confidence</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Reasoning</th>
                      <th className="px-4 py-2.5 text-left font-medium text-text-tertiary">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredActions.map((a) => (
                      <tr key={a.action_id} className="hover:bg-muted/20">
                        <td className="px-4 py-2.5">
                          <Badge className={VERDICT_COLORS[a.policy_verdict] || ""}>{a.policy_verdict}</Badge>
                        </td>
                        <td className="px-4 py-2.5 font-medium text-text-primary">{a.agent_id}</td>
                        <td className="px-4 py-2.5 text-text-secondary">{a.action_type}</td>
                        <td className="px-4 py-2.5 text-text-tertiary font-mono text-[11px]">{a.target_resource}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1">
                            <div className="h-1 w-10 rounded-full bg-muted">
                              <div
                                className={`h-full rounded-full ${a.confidence_score >= 0.7 ? "bg-green-500" : a.confidence_score >= 0.4 ? "bg-amber-500" : "bg-red-500"}`}
                                style={{ width: `${a.confidence_score * 100}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-text-tertiary">{(a.confidence_score * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="max-w-[200px] truncate px-4 py-2.5 text-text-tertiary">{a.reasoning || "—"}</td>
                        <td className="px-4 py-2.5"><TimeAgo date={a.created_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Policies Tab */}
      {tab === "policies" && (
        <div className="space-y-4">
          <form onSubmit={handleSavePolicy} className="rounded-xl border border-border bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-[13px] font-semibold text-text-primary">{editingPolicyName ? "Edit policy" : "Create policy"}</h3>
                <p className="mt-0.5 text-[11px] text-text-tertiary">{editingPolicyName ? `Editing ${editingPolicyName}` : "Add a demo-ready allow, deny, or approval rule."}</p>
              </div>
              <div className="flex gap-2">
                {editingPolicyName && (
                  <button
                    type="button"
                    onClick={resetPolicyDraft}
                    className="rounded-lg border border-border bg-surface-elevated px-3 py-1.5 text-[11px] font-medium text-text-secondary"
                  >
                    Cancel
                  </button>
                )}
                <button
                  type="submit"
                  disabled={saving || !policyDraft.name.trim()}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-text-primary px-3 py-1.5 text-[11px] font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Plus className="size-3.5" />
                  {editingPolicyName ? "Save" : "Create"}
                </button>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-4">
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Name</span>
                <input
                  value={policyDraft.name}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, name: e.target.value }))}
                  disabled={Boolean(editingPolicyName)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] text-text-primary outline-none focus:border-text-secondary"
                  placeholder="prod-change-approval"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Effect</span>
                <select
                  value={policyDraft.effect}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, effect: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] text-text-primary outline-none focus:border-text-secondary"
                >
                  <option value="approve">Require approval</option>
                  <option value="deny">Deny</option>
                  <option value="allow">Allow</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Agents</span>
                <input
                  value={policyDraft.target_agents}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, target_agents: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] text-text-primary outline-none focus:border-text-secondary"
                  placeholder="*, deployment-agent"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Priority</span>
                <input
                  value={policyDraft.priority}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, priority: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] text-text-primary outline-none focus:border-text-secondary"
                  inputMode="numeric"
                />
              </label>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Description</span>
                <input
                  value={policyDraft.description}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, description: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] text-text-primary outline-none focus:border-text-secondary"
                  placeholder="Production changes require review"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-medium uppercase text-text-tertiary">Conditions JSON</span>
                <input
                  value={policyDraft.conditions}
                  onChange={(e) => setPolicyDraft((p) => ({ ...p, conditions: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] text-text-primary outline-none focus:border-text-secondary"
                  placeholder='{"action_type":"deploy","target_pattern":"prod"}'
                />
              </label>
            </div>
          </form>

          {policies.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-12 text-center">
              <Lock className="mx-auto mb-3 size-10 text-text-disabled" />
              <p className="text-[13px] font-medium text-text-primary">No policies defined</p>
              <p className="mt-1 text-[12px] text-text-tertiary">Create policies to control what agents can and cannot do</p>
            </div>
          ) : (
            <div className="space-y-2">
              {policies.map((p) => (
                <div key={p.policy_id} className="flex items-center gap-4 rounded-xl border border-border bg-surface px-5 py-4">
                  <div className={`grid size-8 place-items-center rounded-lg ${p.effect === "deny" ? "bg-red-50" : p.effect === "approve" ? "bg-amber-50" : "bg-green-50"}`}>
                    {p.effect === "deny" ? <Ban className="size-4 text-red-600" /> : p.effect === "approve" ? <Clock className="size-4 text-amber-600" /> : <ShieldCheck className="size-4 text-green-600" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-text-primary">{p.name}</span>
                      <Badge className={p.enabled ? "bg-green-50 text-green-700 border-green-200" : "bg-gray-50 text-gray-500 border-gray-200"}>
                        {p.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-text-tertiary">{p.description}</p>
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-text-tertiary">
                      <span>Agents: <span className="font-mono text-text-secondary">{(p.target_agents || []).join(", ") || "*"}</span></span>
                      <span>Conditions: <span className="font-mono text-text-secondary">{JSON.stringify(p.conditions || {})}</span></span>
                    </div>
                  </div>
                  <Badge className="bg-surface-elevated text-text-secondary border-border">
                    {p.effect}
                  </Badge>
                  <span className="text-[11px] text-text-tertiary">Priority {p.priority}</span>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => editPolicy(p)}
                      className="rounded-lg border border-border bg-surface-elevated px-2.5 py-1.5 text-[11px] font-medium text-text-secondary"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeletePolicy(p.name)}
                      disabled={saving}
                      className="rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-[11px] font-medium text-red-700 disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Approvals Tab */}
      {tab === "approvals" && (
        <div className="space-y-4">
          {approvals.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-12 text-center">
              <Clock className="mx-auto mb-3 size-10 text-text-disabled" />
              <p className="text-[13px] font-medium text-text-primary">No pending approvals</p>
              <p className="mt-1 text-[12px] text-text-tertiary">Governance actions that require review will appear here.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {approvals.map((approval) => (
                <div key={approval.approval_id} className="rounded-xl border border-border bg-surface px-5 py-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge className="bg-amber-50 text-amber-700 border-amber-200">{approval.status}</Badge>
                        <span className="font-mono text-[10px] text-text-tertiary">{approval.approval_id}</span>
                      </div>
                      <p className="mt-2 text-[13px] font-semibold text-text-primary">{approval.summary}</p>
                      <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-text-tertiary">
                        <span>Requester: <span className="text-text-secondary">{approval.requester}</span></span>
                        <span>Type: <span className="text-text-secondary">{approval.request_type}</span></span>
                        <TimeAgo date={approval.created_at} />
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => handleApproval(approval.approval_id, "approved")}
                        disabled={saving}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-[11px] font-medium text-green-700 disabled:opacity-50"
                      >
                        <CheckCircle className="size-3.5" />
                        Approve
                      </button>
                      <button
                        onClick={() => handleApproval(approval.approval_id, "rejected")}
                        disabled={saving}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-[11px] font-medium text-red-700 disabled:opacity-50"
                      >
                        <Ban className="size-3.5" />
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Anomalies Tab */}
      {tab === "anomalies" && (
        <div className="space-y-4">
          {anomalies.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-12 text-center">
              <CheckCircle className="mx-auto mb-3 size-10 text-green-500" />
              <p className="text-[13px] font-medium text-text-primary">No anomalies detected</p>
              <p className="mt-1 text-[12px] text-text-tertiary">System will automatically detect unusual agent behavior</p>
            </div>
          ) : (
            <div className="space-y-2">
              {anomalies.map((a) => (
                <div key={a.anomaly_id} className="flex items-start gap-4 rounded-xl border border-border bg-surface px-5 py-4">
                  <div className={`mt-0.5 grid size-8 place-items-center rounded-lg ${SEVERITY_COLORS[a.severity] || "bg-gray-50"}`}>
                    <AlertTriangle className="size-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-text-primary">{a.anomaly_type.replace(/_/g, " ")}</span>
                      <Badge className={STATUS_COLORS[a.status] || ""}>{a.status}</Badge>
                    </div>
                    <p className="text-[12px] text-text-secondary mt-0.5">{a.description}</p>
                    <div className="mt-2 flex items-center gap-4 text-[10px] text-text-tertiary">
                      <span>Agent: <span className="font-medium text-text-secondary">{a.agent_id}</span></span>
                      <span>Severity: <span className="font-medium text-text-secondary capitalize">{a.severity}</span></span>
                      <TimeAgo date={a.detected_at} />
                      {a.resolved_by && <span>Resolved by {a.resolved_by}</span>}
                    </div>
                  </div>
                  {a.status !== "resolved" && a.status !== "false_positive" && (
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => handleResolveAnomaly(a.anomaly_id, "resolved")}
                        disabled={saving}
                        className="rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-[11px] font-medium text-green-700 disabled:opacity-50"
                      >
                        Resolve
                      </button>
                      <button
                        onClick={() => handleResolveAnomaly(a.anomaly_id, "false_positive")}
                        disabled={saving}
                        className="rounded-lg border border-border bg-surface-elevated px-3 py-1.5 text-[11px] font-medium text-text-secondary disabled:opacity-50"
                      >
                        False positive
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
