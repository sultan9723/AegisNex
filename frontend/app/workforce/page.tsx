"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity, AlertTriangle, Bot, CheckCircle, Clock, Copy, Camera, Download,
  Eye, PauseCircle, PlayCircle, Plus, RefreshCw, Search, Shield,
  StopCircle, Terminal, TrendingUp, Users, X, Archive, Zap,
  DollarSign, HeartPulse, FileText, Key, BookOpen,
} from "lucide-react";
import {
  type WorkforceAgent, type WorkforceStats, type WorkforceExecution,
  type AgentVersion, type PromptVersion, type ToolPermission,
  type KnowledgeAssignment, type HealthRecord,
  getWorkforceStats, listWorkforceAgents, getWorkforceAgent,
  createWorkforceAgent, updateWorkforceAgent, deleteWorkforceAgent,
  activateWorkforceAgent, pauseWorkforceAgent, resumeWorkforceAgent,
  archiveWorkforceAgent, cloneWorkforceAgent,
  listAgentVersions, createAgentVersion, getAgentVersion, restoreAgentVersion,
  listAgentPrompts, saveAgentPrompt,
  listAgentToolPermissions, setAgentToolPermission, deleteAgentToolPermission,
  listAgentKnowledge, assignAgentKnowledge, removeAgentKnowledge,
  listAgentExecutions, getAgentExecutionStats,
  getAgentBudget, getAgentHealthHistory, recordAgentHealthCheck,
  playgroundExecute, createAgentWizard,
} from "@/lib/api";

type Tab = "overview" | "agents" | "playground";

const LIFECYCLE_COLORS: Record<string, string> = {
  draft: "bg-gray-50 text-gray-600 border-gray-200",
  active: "bg-green-50 text-green-700 border-green-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  archived: "bg-blue-50 text-blue-700 border-blue-200",
  decommissioned: "bg-red-50 text-red-700 border-red-200",
};

const HEALTH_COLORS: Record<string, string> = {
  healthy: "bg-green-50 text-green-700 border-green-200",
  degraded: "bg-amber-50 text-amber-700 border-amber-200",
  unhealthy: "bg-red-50 text-red-700 border-red-200",
  unknown: "bg-gray-50 text-gray-500 border-gray-200",
};

const EXECUTION_COLORS: Record<string, string> = {
  success: "bg-green-50 text-green-700 border-green-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  error: "bg-red-50 text-red-700 border-red-200",
  timeout: "bg-amber-50 text-amber-700 border-amber-200",
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
          <div className="grid size-9 place-items-center rounded-lg bg-muted/50">
            <Icon className={`size-4 ${color}`} />
          </div>
          <div>
            <p className="text-[22px] font-bold tracking-tight text-text-primary">{value}</p>
            <p className="text-[11px] text-text-tertiary">{label}</p>
          </div>
        </div>
      </div>
      {sub && <p className="mt-1.5 text-[11px] text-text-tertiary">{sub}</p>}
    </div>
  );
}

function ProgressBar({ value, max = 100, color = "bg-blue-500" }: { value: number; max?: number; color?: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function Modal({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border border-border bg-surface p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-text-tertiary hover:bg-muted"><X className="size-4" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function WizardModal({ open, onClose, onCreated }: {
  open: boolean; onClose: () => void; onCreated: (a: WorkforceAgent) => void;
}) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    name: "", description: "", agent_type: "general",
    provider: "openai", model: "gpt-4o-mini",
    daily_budget: 25, monthly_budget: 750,
    owner: "", team: "", system_prompt: "",
    tools: "", permissions: "", knowledge_sources: "", tags: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const update = (k: string, v: string | number) => setForm(p => ({ ...p, [k]: v }));

  const handleCreate = async () => {
    setSaving(true); setError("");
    try {
      const tools = form.tools ? form.tools.split(",").map(s => ({ name: s.trim(), allowed: true })) : undefined;
      const permissions = form.permissions ? form.permissions.split(",").map(s => s.trim()) : undefined;
      const knowledge_sources = form.knowledge_sources ? form.knowledge_sources.split(",").map(s => s.trim()) : undefined;
      const tags = form.tags ? form.tags.split(",").map(s => s.trim()) : undefined;
      const agent = await createAgentWizard({
        name: form.name, description: form.description,
        agent_type: form.agent_type, provider: form.provider, model: form.model,
        daily_budget: Number(form.daily_budget), monthly_budget: Number(form.monthly_budget),
        owner: form.owner, team: form.team, system_prompt: form.system_prompt || undefined,
        tools, permissions, knowledge_sources, tags,
      });
      onCreated(agent);
      onClose();
    } catch (e: any) {
      setError(e?.message || "Failed to create agent");
    } finally { setSaving(false); }
  };

  const steps = ["Basics", "Config", "Capabilities", "Review"];

  return (
    <Modal open={open} onClose={onClose} title="Create Agent Wizard">
      <div className="mb-6 flex gap-1">
        {steps.map((s, i) => (
          <div key={s} className={`flex-1 rounded-lg px-3 py-1.5 text-center text-xs font-medium ${i === step ? "bg-blue-50 text-blue-700" : i < step ? "bg-green-50 text-green-700" : "bg-muted text-text-tertiary"}`}>
            {s}
          </div>
        ))}
      </div>
      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</div>}

      {step === 0 && (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Name *</label>
            <input value={form.name} onChange={e => update("name", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-blue-400 focus:outline-none" placeholder="e.g. Security Analyst Bot" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Description</label>
            <textarea value={form.description} onChange={e => update("description", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-blue-400 focus:outline-none" rows={3} placeholder="What this agent does" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Type</label>
              <select value={form.agent_type} onChange={e => update("agent_type", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
                <option value="general">General</option>
                <option value="security">Security</option>
                <option value="compliance">Compliance</option>
                <option value="operations">Operations</option>
                <option value="infrastructure">Infrastructure</option>
                <option value="research">Research</option>
                <option value="monitoring">Monitoring</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Owner</label>
              <input value={form.owner} onChange={e => update("owner", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="user@example.com" />
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Provider</label>
              <select value={form.provider} onChange={e => update("provider", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="google">Google</option>
                <option value="mistral">Mistral</option>
                <option value="local">Local</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Model</label>
              <input value={form.model} onChange={e => update("model", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="gpt-4o-mini" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Daily Budget ($)</label>
              <input type="number" value={form.daily_budget} onChange={e => update("daily_budget", Number(e.target.value))} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">Monthly Budget ($)</label>
              <input type="number" value={form.monthly_budget} onChange={e => update("monthly_budget", Number(e.target.value))} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">System Prompt</label>
            <textarea value={form.system_prompt} onChange={e => update("system_prompt", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm font-mono text-text-primary placeholder:text-text-tertiary focus:border-blue-400 focus:outline-none" rows={6} placeholder="You are a helpful AI assistant that..." />
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Tools (comma-separated)</label>
            <input value={form.tools} onChange={e => update("tools", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="docker, kubernetes, metrics, knowledge" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Permissions (comma-separated)</label>
            <input value={form.permissions} onChange={e => update("permissions", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="read_incidents, write_actions, read_metrics" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Knowledge Sources (comma-separated IDs)</label>
            <input value={form.knowledge_sources} onChange={e => update("knowledge_sources", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="kb-001, kb-002" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Tags (comma-separated)</label>
            <input value={form.tags} onChange={e => update("tags", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="production, security, monitoring" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">Team</label>
            <input value={form.team} onChange={e => update("team", e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm" placeholder="Security Team" />
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3 text-sm">
          <h3 className="font-medium text-text-primary">Review Configuration</h3>
          <div className="rounded-lg border border-border bg-muted/20 p-4 space-y-2">
            <Row label="Name" value={form.name} />
            <Row label="Type" value={form.agent_type} />
            <Row label="Provider/Model" value={`${form.provider}/${form.model}`} />
            <Row label="Budget" value={`$${form.daily_budget} daily / $${form.monthly_budget} monthly`} />
            <Row label="Owner/Team" value={`${form.owner || "-"} / ${form.team || "-"}`} />
            <Row label="Tools" value={form.tools || "(none)"} />
            <Row label="Permissions" value={form.permissions || "(none)"} />
            <Row label="Knowledge" value={form.knowledge_sources || "(none)"} />
            {form.system_prompt && <Row label="System Prompt" value={`${form.system_prompt.slice(0, 80)}...`} />}
          </div>
        </div>
      )}

      <div className="mt-6 flex justify-between">
        <button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-muted disabled:opacity-40">Back</button>
        {step < 3 ? (
          <button onClick={() => setStep(step + 1)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">Next</button>
        ) : (
          <button onClick={handleCreate} disabled={!form.name || saving} className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
            {saving ? "Creating..." : "Create Agent"}
          </button>
        )}
      </div>
    </Modal>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-4"><span className="text-text-secondary">{label}</span><span className="text-text-primary font-medium">{value}</span></div>;
}

function TrustBadge({ score }: { score: number }) {
  const color = score >= 70 ? "text-green-600" : score >= 40 ? "text-amber-600" : "text-red-600";
  return <span className={`font-bold ${color}`}>{score.toFixed(0)}</span>;
}

// =========================================================================
// Detail Drawer
// =========================================================================
function AgentDetailDrawer({ agentId, onClose, onRefresh }: {
  agentId: string; onClose: () => void; onRefresh: () => void;
}) {
  const [agent, setAgent] = useState<WorkforceAgent | null>(null);
  const [tab, setTab] = useState("overview");
  const [versions, setVersions] = useState<AgentVersion[]>([]);
  const [prompts, setPrompts] = useState<PromptVersion[]>([]);
  const [tools, setTools] = useState<ToolPermission[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeAssignment[]>([]);
  const [executions, setExecutions] = useState<WorkforceExecution[]>([]);
  const [budget, setBudget] = useState<any>(null);
  const [health, setHealth] = useState<{ records: HealthRecord[]; latest: HealthRecord | null }>({ records: [], latest: null });
  const [execStats, setExecStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, v, p, t, k, e, es, b, h] = await Promise.all([
        getWorkforceAgent(agentId),
        listAgentVersions(agentId).catch(() => ({ versions: [], total: 0 })),
        listAgentPrompts(agentId).catch(() => ({ prompts: [], total: 0 })),
        listAgentToolPermissions(agentId).catch(() => ({ tools: [], total: 0 })),
        listAgentKnowledge(agentId).catch(() => ({ assignments: [], total: 0 })),
        listAgentExecutions(agentId, { limit: 20 }).catch(() => ({ executions: [], total: 0 })),
        getAgentExecutionStats(agentId).catch(() => ({})),
        getAgentBudget(agentId).catch(() => null),
        getAgentHealthHistory(agentId, 10).catch(() => ({ records: [], latest: null })),
      ]);
      setAgent(a); setVersions(v.versions); setPrompts(p.prompts);
      setTools(t.tools); setKnowledge(k.assignments);
      setExecutions(e.executions); setExecStats(es);
      setBudget(b); setHealth(h);
    } catch (e) { setActionMsg("Failed to load agent detail"); }
    finally { setLoading(false); }
  }, [agentId]);

  useEffect(() => { load(); }, [load]);

  const doAction = async (action: string, fn: () => Promise<any>) => {
    try {
      await fn();
      setActionMsg(`${action} successful`);
      load(); onRefresh();
      setTimeout(() => setActionMsg(""), 3000);
    } catch (e: any) { setActionMsg(`${action} failed: ${e?.message}`); }
  };

  if (loading) return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-xl border-l border-border bg-surface p-6 shadow-xl overflow-y-auto">
      <p className="text-sm text-text-tertiary">Loading...</p>
    </div>
  );
  if (!agent) return null;

  const tabs = [
    { key: "overview", label: "Overview", icon: Eye },
    { key: "versions", label: "Versions", icon: Clock },
    { key: "prompts", label: "Prompts", icon: FileText },
    { key: "tools", label: "Tools", icon: Key },
    { key: "knowledge", label: "Knowledge", icon: BookOpen },
    { key: "executions", label: "Executions", icon: Terminal },
    { key: "budget", label: "Budget", icon: DollarSign },
    { key: "health", label: "Health", icon: HeartPulse },
  ];

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-xl border-l border-border bg-surface p-6 shadow-xl overflow-y-auto">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">{agent.name || agent.agent_id}</h2>
          <p className="text-xs text-text-tertiary">{agent.agent_id}</p>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 text-text-tertiary hover:bg-muted"><X className="size-4" /></button>
      </div>

      {actionMsg && (
        <div className="mb-4 rounded-lg bg-blue-50 p-3 text-xs text-blue-700">{actionMsg}</div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <Badge className={LIFECYCLE_COLORS[agent.lifecycle_status] || ""}>{agent.lifecycle_status}</Badge>
        <Badge className={HEALTH_COLORS[agent.health_status] || ""}>{agent.health_status}</Badge>
        <Badge className="bg-purple-50 text-purple-700 border-purple-200">v{agent.version}</Badge>
        <Badge className="bg-gray-50 text-gray-600 border-gray-200">{agent.agent_type}</Badge>
        <span className="text-[10px] text-text-tertiary self-center ml-1">{agent.provider}/{agent.model}</span>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {agent.lifecycle_status === "draft" && (
          <button onClick={() => doAction("Activate", () => activateWorkforceAgent(agentId))} className="flex items-center gap-1 rounded-lg border border-green-200 bg-green-50 px-2.5 py-1 text-[11px] font-medium text-green-700 hover:bg-green-100"><PlayCircle className="size-3" /> Activate</button>
        )}
        {agent.lifecycle_status === "active" && (
          <button onClick={() => doAction("Pause", () => pauseWorkforceAgent(agentId))} className="flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"><PauseCircle className="size-3" /> Pause</button>
        )}
        {agent.lifecycle_status === "paused" && (
          <button onClick={() => doAction("Resume", () => resumeWorkforceAgent(agentId))} className="flex items-center gap-1 rounded-lg border border-green-200 bg-green-50 px-2.5 py-1 text-[11px] font-medium text-green-700 hover:bg-green-100"><PlayCircle className="size-3" /> Resume</button>
        )}
        <button onClick={() => doAction("Clone", () => cloneWorkforceAgent(agentId))} className="flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100"><Copy className="size-3" /> Clone</button>
        <button onClick={() => doAction("Archive", () => archiveWorkforceAgent(agentId))} className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-100"><Archive className="size-3" /> Archive</button>
        <button onClick={() => doAction("Snapshot", () => createAgentVersion(agentId, { change_summary: "Manual snapshot", created_by: "ui" }))} className="flex items-center gap-1 rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1 text-[11px] font-medium text-purple-700 hover:bg-purple-100"><Camera className="size-3" /> Snapshot</button>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium whitespace-nowrap ${tab === t.key ? "bg-blue-50 text-blue-700" : "text-text-tertiary hover:bg-muted"}`}>
            <t.icon className="size-3" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-muted/20 p-4 space-y-2 text-sm">
            <Row label="Type" value={agent.agent_type} />
            <Row label="Model" value={`${agent.provider}/${agent.model}`} />
            <Row label="Version" value={`v${agent.version}`} />
            <Row label="Owner" value={agent.owner || "-"} />
            <Row label="Team" value={agent.team || "-"} />
            {agent.description && <Row label="Description" value={agent.description} />}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-border p-3">
              <p className="text-[11px] text-text-tertiary">Trust Score</p>
              <p className="text-xl font-bold text-text-primary"><TrustBadge score={agent.trust_score} /></p>
              <ProgressBar value={agent.trust_score} color={agent.trust_score >= 70 ? "bg-green-500" : agent.trust_score >= 40 ? "bg-amber-500" : "bg-red-500"} />
            </div>
            <div className="rounded-lg border border-border p-3">
              <p className="text-[11px] text-text-tertiary">Success Rate</p>
              <p className="text-xl font-bold text-text-primary">{agent.success_rate.toFixed(1)}%</p>
              <ProgressBar value={agent.success_rate} color={agent.success_rate >= 80 ? "bg-green-500" : "bg-amber-500"} />
            </div>
            <div className="rounded-lg border border-border p-3">
              <p className="text-[11px] text-text-tertiary">Executions</p>
              <p className="text-xl font-bold text-text-primary">{agent.total_executions}</p>
              <p className="text-[10px] text-text-tertiary mt-1">Avg latency: {agent.average_latency_ms.toFixed(0)}ms</p>
            </div>
            <div className="rounded-lg border border-border p-3">
              <p className="text-[11px] text-text-tertiary">Total Cost</p>
              <p className="text-xl font-bold text-text-primary">${agent.total_cost.toFixed(4)}</p>
              <p className="text-[10px] text-text-tertiary mt-1">Confidence: {(agent.confidence * 100).toFixed(0)}%</p>
            </div>
          </div>
          {agent.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {agent.tags.map(t => <Badge key={t} className="bg-gray-50 text-gray-600 border-gray-200">{t}</Badge>)}
            </div>
          )}
        </div>
      )}

      {tab === "versions" && (
        <div className="space-y-2">
          {versions.length === 0 && <p className="text-xs text-text-tertiary">No versions recorded</p>}
          {versions.map(v => (
            <div key={v.id} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-sm text-text-primary">v{v.version}</span>
                  <span className="ml-2 text-xs text-text-tertiary">{v.created_at}</span>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => doAction("Restore", () => restoreAgentVersion(agentId, v.version))} className="rounded px-2 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-700 hover:bg-blue-100">Restore</button>
                </div>
              </div>
              <p className="text-xs text-text-secondary mt-1">{v.change_summary || "No summary"}</p>
              <p className="text-[10px] text-text-tertiary">by {v.created_by || "system"}</p>
            </div>
          ))}
        </div>
      )}

      {tab === "prompts" && (
        <div className="space-y-2">
          {prompts.length === 0 && <p className="text-xs text-text-tertiary">No prompts saved</p>}
          {prompts.map(p => (
            <div key={p.prompt_id} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-sm text-text-primary">{p.name}</span>
                  <Badge className="ml-2 bg-gray-50 text-gray-600 border-gray-200">{p.role}</Badge>
                  <span className="ml-1 text-xs text-text-tertiary">v{p.version}</span>
                </div>
              </div>
              <pre className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap rounded bg-muted/30 p-2 text-[10px] text-text-secondary font-mono">{p.content}</pre>
              {p.variables.length > 0 && <p className="mt-1 text-[10px] text-text-tertiary">Variables: {p.variables.join(", ")}</p>}
            </div>
          ))}
        </div>
      )}

      {tab === "tools" && (
        <div className="space-y-2">
          {tools.length === 0 && <p className="text-xs text-text-tertiary">No tool permissions configured</p>}
          {tools.map(t => (
            <div key={t.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text-primary">{t.tool_name}</span>
                <Badge className={t.allowed ? "bg-green-50 text-green-700 border-green-200" : "bg-red-50 text-red-700 border-red-200"}>
                  {t.allowed ? "Allowed" : "Denied"}
                </Badge>
              </div>
              <button onClick={() => doAction("Delete Tool", () => deleteAgentToolPermission(agentId, t.tool_name))} className="text-[10px] text-red-600 hover:underline">Remove</button>
            </div>
          ))}
        </div>
      )}

      {tab === "knowledge" && (
        <div className="space-y-2">
          {knowledge.length === 0 && <p className="text-xs text-text-tertiary">No knowledge assigned</p>}
          {knowledge.map(k => (
            <div key={k.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <span className="text-sm font-medium text-text-primary">{k.knowledge_source_id}</span>
                <Badge className="ml-2 bg-gray-50 text-gray-600 border-gray-200">{k.knowledge_source_type}</Badge>
                <span className="ml-1 text-[10px] text-text-tertiary">{k.access_level}</span>
              </div>
              <button onClick={() => doAction("Remove Knowledge", () => removeAgentKnowledge(agentId, k.knowledge_source_id))} className="text-[10px] text-red-600 hover:underline">Remove</button>
            </div>
          ))}
        </div>
      )}

      {tab === "executions" && (
        <div className="space-y-2">
          {execStats && Object.keys(execStats).length > 0 && (
            <div className="mb-3 grid grid-cols-3 gap-2">
              <div className="rounded-lg border border-border p-2 text-center">
                <p className="text-lg font-bold text-green-600">{execStats.successes || 0}</p>
                <p className="text-[10px] text-text-tertiary">Success</p>
              </div>
              <div className="rounded-lg border border-border p-2 text-center">
                <p className="text-lg font-bold text-red-600">{execStats.failures || 0}</p>
                <p className="text-[10px] text-text-tertiary">Failed</p>
              </div>
              <div className="rounded-lg border border-border p-2 text-center">
                <p className="text-lg font-bold text-text-primary">{execStats.total || 0}</p>
                <p className="text-[10px] text-text-tertiary">Total</p>
              </div>
            </div>
          )}
          {executions.length === 0 && <p className="text-xs text-text-tertiary">No executions</p>}
          {executions.map(e => (
            <div key={e.execution_id} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-primary truncate max-w-[200px]">{e.task}</span>
                <Badge className={EXECUTION_COLORS[e.status] || ""}>{e.status}</Badge>
              </div>
              <div className="mt-1 flex gap-3 text-[10px] text-text-tertiary">
                <span>{(e.latency_ms).toFixed(0)}ms</span>
                <span>${e.cost.toFixed(6)}</span>
                <span>{(e.confidence * 100).toFixed(0)}%</span>
              </div>
              {e.response && <p className="mt-1 text-[10px] text-text-secondary line-clamp-2">{e.response}</p>}
            </div>
          ))}
        </div>
      )}

      {tab === "budget" && budget && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border p-4">
            <p className="mb-1 text-xs font-medium text-text-secondary">Daily Budget</p>
            <p className="text-xl font-bold text-text-primary">${budget.daily_used?.toFixed(4) || "0"} / ${budget.daily_budget?.toFixed(2) || "0"}</p>
            <ProgressBar value={budget.daily_used || 0} max={budget.daily_budget || 1} color={budget.remaining_daily > 0 ? "bg-blue-500" : "bg-red-500"} />
            <p className="mt-1 text-[10px] text-text-tertiary">Remaining: ${(budget.remaining_daily || 0).toFixed(4)}</p>
          </div>
          <div className="rounded-lg border border-border p-4">
            <p className="mb-1 text-xs font-medium text-text-secondary">Monthly Budget</p>
            <p className="text-xl font-bold text-text-primary">${budget.monthly_used?.toFixed(4) || "0"} / ${budget.monthly_budget?.toFixed(2) || "0"}</p>
            <ProgressBar value={budget.monthly_used || 0} max={budget.monthly_budget || 1} color={budget.remaining_monthly > 0 ? "bg-blue-500" : "bg-red-500"} />
            <p className="mt-1 text-[10px] text-text-tertiary">Remaining: ${(budget.remaining_monthly || 0).toFixed(4)}</p>
          </div>
        </div>
      )}

      {tab === "health" && (
        <div className="space-y-3">
          {health.latest && (
            <div className={`rounded-lg border p-3 ${health.latest.status === "healthy" ? "border-green-200 bg-green-50" : health.latest.status === "degraded" ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50"}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{health.latest.status}</span>
                <span className="text-[10px] text-text-tertiary">{health.latest.checked_at}</span>
              </div>
              <p className="text-[11px] text-text-secondary mt-1">{health.latest.check_type} — {health.latest.metric_value}</p>
            </div>
          )}
          <div className="flex gap-1.5">
            <button onClick={() => doAction("Health Check", () => recordAgentHealthCheck(agentId, { status: "healthy", check_type: "heartbeat", metric_value: 1 }))} className="rounded-lg border border-green-200 bg-green-50 px-2.5 py-1 text-[10px] font-medium text-green-700 hover:bg-green-100">Check Healthy</button>
            <button onClick={() => doAction("Health Check", () => recordAgentHealthCheck(agentId, { status: "degraded", check_type: "response_time", metric_value: 5000, details: { reason: "slow response" } }))} className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-medium text-amber-700 hover:bg-amber-100">Mark Degraded</button>
          </div>
          {health.records.length > 1 && (
            <div className="space-y-1 mt-3">
              <p className="text-xs font-medium text-text-secondary">History</p>
              {health.records.slice(1).map(r => (
                <div key={r.id} className="flex items-center justify-between rounded border border-border px-3 py-1.5">
                  <Badge className={HEALTH_COLORS[r.status] || ""}>{r.status}</Badge>
                  <span className="text-[10px] text-text-tertiary">{r.check_type}</span>
                  <span className="text-[10px] text-text-tertiary">{r.checked_at}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =========================================================================
// Main Page
// =========================================================================
export default function WorkforcePage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<WorkforceStats | null>(null);
  const [agents, setAgents] = useState<WorkforceAgent[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [playgroundAgentId, setPlaygroundAgentId] = useState("");
  const [playgroundTask, setPlaygroundTask] = useState("");
  const [playgroundResult, setPlaygroundResult] = useState<WorkforceExecution | null>(null);
  const [playgroundLoading, setPlaygroundLoading] = useState(false);
  const [playgroundSimulate, setPlaygroundSimulate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, a] = await Promise.all([
        getWorkforceStats().catch(() => null),
        listWorkforceAgents({ search: search || undefined, lifecycle_status: statusFilter || undefined, limit: 200 }),
      ]);
      if (s) setStats(s);
      setAgents(a.agents);
      setTotalAgents(a.total);
    } catch (e) { /* ignore */ }
    finally { setLoading(false); }
  }, [search, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handlePlayground = async () => {
    if (!playgroundAgentId || !playgroundTask) return;
    setPlaygroundLoading(true);
    setPlaygroundResult(null);
    try {
      const result = await playgroundExecute(playgroundAgentId, { task: playgroundTask, simulate: playgroundSimulate });
      setPlaygroundResult(result);
    } catch (e: any) {
      setPlaygroundResult({ execution_id: "", agent_id: playgroundAgentId, task: playgroundTask, response: "", latency_ms: 0, cost: 0, confidence: 0, tools_used: [], status: "error", error: e?.message || "Failed", prompt_version_id: "", metadata: {}, created_at: "" });
    } finally { setPlaygroundLoading(false); }
  };

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">AI Workforce</h1>
          <p className="text-sm text-text-tertiary">Manage agents, lifecycle, versions, permissions, and execution</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-text-secondary hover:bg-muted"><RefreshCw className="size-3.5" /> Refresh</button>
          <button onClick={() => setWizardOpen(true)} className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"><Plus className="size-3.5" /> Create Agent</button>
        </div>
      </div>

      <div className="mb-6 flex gap-1 border-b border-border">
        {(["overview", "agents", "playground"] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2.5 text-sm font-medium transition-colors ${tab === t ? "border-b-2 border-blue-600 text-blue-600" : "text-text-tertiary hover:text-text-primary"}`}>
            {t === "overview" && "Overview"}
            {t === "agents" && `Agents (${totalAgents})`}
            {t === "playground" && "Playground"}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats && (
              <>
                <StatCard label="Total Agents" value={stats.total_agents} icon={Users} color="text-blue-600" />
                <StatCard label="Active" value={stats.active_agents} icon={PlayCircle} color="text-green-600" sub={`${stats.paused_agents} paused, ${stats.draft_agents} draft`} />
                <StatCard label="Avg Trust Score" value={`${stats.avg_trust_score}%`} icon={TrendingUp} color={stats.avg_trust_score >= 70 ? "text-green-600" : "text-amber-600"} />
                <StatCard label="Total Executions" value={stats.total_executions} icon={Terminal} color="text-purple-600" sub={`${stats.total_successes} success, ${stats.total_failures} failed`} />
              </>
            )}
          </div>

          {stats && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-border bg-surface p-5">
                <h3 className="mb-3 text-sm font-semibold text-text-primary">By Type</h3>
                <div className="space-y-2">
                  {Object.entries(stats.by_type).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <span className="text-sm text-text-secondary capitalize">{type}</span>
                      <span className="text-sm font-medium text-text-primary">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-surface p-5">
                <h3 className="mb-3 text-sm font-semibold text-text-primary">By Health</h3>
                <div className="space-y-2">
                  {Object.entries(stats.by_health).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`size-2 rounded-full ${status === "healthy" ? "bg-green-500" : status === "degraded" ? "bg-amber-500" : status === "unhealthy" ? "bg-red-500" : "bg-gray-400"}`} />
                        <span className="text-sm text-text-secondary capitalize">{status}</span>
                      </div>
                      <span className="text-sm font-medium text-text-primary">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-border bg-surface p-5">
            <h3 className="mb-3 text-sm font-semibold text-text-primary">Quick Actions</h3>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => { setTab("agents"); }} className="rounded-lg border border-border px-3 py-2 text-xs font-medium text-text-secondary hover:bg-muted">View All Agents</button>
              <button onClick={() => setWizardOpen(true)} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700">Create New Agent</button>
              <button onClick={() => { setTab("playground"); }} className="rounded-lg border border-border px-3 py-2 text-xs font-medium text-text-secondary hover:bg-muted">Open Playground</button>
            </div>
          </div>
        </div>
      )}

      {tab === "agents" && (
        <div>
          <div className="mb-4 flex items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-text-tertiary" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents..." className="w-full rounded-lg border border-border bg-muted/30 py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-blue-400 focus:outline-none" />
            </div>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-text-primary">
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
              <option value="decommissioned">Decommissioned</option>
            </select>
          </div>

          {loading ? (
            <p className="text-sm text-text-tertiary">Loading...</p>
          ) : agents.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-8 text-center">
              <Bot className="mx-auto mb-3 size-8 text-text-tertiary" />
              <p className="text-sm text-text-tertiary">No agents found</p>
              <button onClick={() => setWizardOpen(true)} className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">Create your first agent</button>
            </div>
          ) : (
            <div className="space-y-2">
              {agents.map(a => (
                <div key={a.agent_id} onClick={() => setSelectedAgentId(a.agent_id)} className="flex cursor-pointer items-center justify-between rounded-xl border border-border bg-surface p-4 transition-colors hover:bg-muted/30">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className={`grid size-9 shrink-0 place-items-center rounded-lg ${a.lifecycle_status === "active" ? "bg-green-50" : a.lifecycle_status === "paused" ? "bg-amber-50" : "bg-gray-50"}`}>
                      <Bot className={`size-4 ${a.lifecycle_status === "active" ? "text-green-600" : a.lifecycle_status === "paused" ? "text-amber-600" : "text-gray-500"}`} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-text-primary">{a.name || a.agent_id}</span>
                        <Badge className={LIFECYCLE_COLORS[a.lifecycle_status] || ""}>{a.lifecycle_status}</Badge>
                        <Badge className={HEALTH_COLORS[a.health_status] || ""}>{a.health_status}</Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-text-tertiary truncate max-w-md">{a.description || `${a.provider}/${a.model} · v${a.version}`}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-6 text-xs text-text-tertiary shrink-0">
                    <div className="text-right">
                      <p className="font-medium text-text-primary"><TrustBadge score={a.trust_score} /></p>
                      <p>Trust</p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium text-text-primary">{a.success_rate.toFixed(0)}%</p>
                      <p>Success</p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium text-text-primary">{a.total_executions}</p>
                      <p>Runs</p>
                    </div>
                    <div className="hidden md:block text-right">
                      <p className="font-medium text-text-primary">${a.total_cost.toFixed(2)}</p>
                      <p>Cost</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "playground" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-border bg-surface p-5">
            <h3 className="mb-4 text-sm font-semibold text-text-primary">Test Agent</h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-text-secondary">Select Agent</label>
                <select value={playgroundAgentId} onChange={e => setPlaygroundAgentId(e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-text-primary">
                  <option value="">-- Select --</option>
                  {agents.filter(a => a.lifecycle_status === "active").map(a => (
                    <option key={a.agent_id} value={a.agent_id}>{a.name || a.agent_id} ({a.agent_type})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-text-secondary">Task</label>
                <textarea value={playgroundTask} onChange={e => setPlaygroundTask(e.target.value)} className="w-full rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-blue-400 focus:outline-none" rows={5} placeholder="Describe a task for the agent..." />
              </div>
              <label className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2">
                <span className="text-xs font-medium text-text-secondary">Simulation mode</span>
                <input type="checkbox" checked={playgroundSimulate} onChange={e => setPlaygroundSimulate(e.target.checked)} className="size-4" />
              </label>
              <button onClick={handlePlayground} disabled={!playgroundAgentId || !playgroundTask || playgroundLoading} className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
                {playgroundLoading ? "Running..." : <Zap className="size-3.5" />}
                {playgroundLoading ? "Executing..." : "Execute"}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface p-5">
            <h3 className="mb-4 text-sm font-semibold text-text-primary">Result</h3>
            {!playgroundResult ? (
              <div className="flex flex-col items-center justify-center py-12 text-text-tertiary">
                <Terminal className="mb-2 size-8" />
                <p className="text-sm">Run a task to see results</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge className={EXECUTION_COLORS[playgroundResult.status] || ""}>{playgroundResult.status}</Badge>
                  <span className="text-xs text-text-tertiary">{playgroundResult.execution_id}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-lg border border-border p-2 text-center">
                    <p className="font-bold text-text-primary">{(playgroundResult.latency_ms || 0).toFixed(0)}ms</p>
                    <p className="text-text-tertiary">Latency</p>
                  </div>
                  <div className="rounded-lg border border-border p-2 text-center">
                    <p className="font-bold text-text-primary">${(playgroundResult.cost || 0).toFixed(6)}</p>
                    <p className="text-text-tertiary">Cost</p>
                  </div>
                  <div className="rounded-lg border border-border p-2 text-center">
                    <p className="font-bold text-text-primary">{(playgroundResult.confidence || 0) * 100}%</p>
                    <p className="text-text-tertiary">Confidence</p>
                  </div>
                </div>
                {playgroundResult.response && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-text-secondary">Response</p>
                    <div className="rounded-lg bg-muted/30 p-3 text-xs text-text-primary whitespace-pre-wrap">{playgroundResult.response}</div>
                  </div>
                )}
                {playgroundResult.error && (
                  <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{playgroundResult.error}</div>
                )}
                {playgroundResult.tools_used.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-text-secondary">Tools Used</p>
                    <div className="flex flex-wrap gap-1">
                      {playgroundResult.tools_used.map(t => <Badge key={t} className="bg-purple-50 text-purple-700 border-purple-200">{t}</Badge>)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Detail Drawer */}
      {selectedAgentId && (
        <AgentDetailDrawer
          agentId={selectedAgentId}
          onClose={() => setSelectedAgentId(null)}
          onRefresh={load}
        />
      )}

      {/* Wizard Modal */}
      <WizardModal open={wizardOpen} onClose={() => setWizardOpen(false)} onCreated={() => { load(); setTab("agents"); }} />
    </div>
  );
}
