"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Server, BookOpen, Brain, FileBarChart,
  Activity, Shield, Cpu, HardDrive, Network, AlertTriangle,
  CheckCircle2, TrendingUp, Zap, Clock,
} from "lucide-react";

type Tab = "overview" | "infrastructure" | "knowledge" | "ai" | "reports";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "infrastructure", label: "Infrastructure", icon: Server },
  { key: "knowledge", label: "Knowledge", icon: BookOpen },
  { key: "ai", label: "AI Workspace", icon: Brain },
  { key: "reports", label: "Reports", icon: FileBarChart },
];

function MiniMetric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-2.5">
      <div className="text-[9px] text-text-tertiary">{label}</div>
      <div className={`mt-0.5 text-[14px] font-bold ${color}`}>{value}</div>
    </div>
  );
}

function OverviewPreview() {
  return (
    <div className="grid grid-cols-3 gap-2">
      <MiniMetric label="Uptime" value="99.97%" color="text-success" />
      <MiniMetric label="Incidents" value="3" color="text-warning" />
      <MiniMetric label="Containers" value="24" color="text-primary" />
      <div className="col-span-3 rounded-lg border border-border bg-background p-2.5">
        <div className="flex items-center gap-1.5 mb-2">
          <Activity className="size-2.5 text-primary/40" />
          <span className="text-[9px] font-semibold text-text-secondary">Activity</span>
        </div>
        <div className="flex items-end gap-0.5">
          {[30, 45, 25, 60, 40, 55, 35, 70, 50, 65, 45, 75, 40, 80, 55].map((h, i) => (
            <div key={i} className="flex-1 rounded-sm bg-primary/15" style={{ height: `${h * 0.4}px` }} />
          ))}
        </div>
      </div>
    </div>
  );
}

function InfrastructurePreview() {
  return (
    <div className="grid grid-cols-2 gap-2">
      {[
        { icon: Cpu, label: "CPU", val: "34%", color: "text-primary", w: "34%" },
        { icon: HardDrive, label: "Memory", val: "6.2GB", color: "text-chart-2", w: "62%" },
        { icon: Network, label: "Network", val: "847Mbps", color: "text-success", w: "84%" },
        { icon: Server, label: "Containers", val: "24/24", color: "text-warning", w: "100%" },
      ].map((m) => (
        <div key={m.label} className="rounded-lg border border-border bg-background p-2.5">
          <div className="flex items-center gap-1.5 mb-1.5">
            <m.icon className={`size-2.5 ${m.color}`} />
            <span className="text-[9px] text-text-tertiary">{m.label}</span>
          </div>
          <div className="text-[12px] font-bold text-text-primary">{m.val}</div>
          <div className="mt-1.5 h-1 rounded-full bg-muted">
            <motion.div
              className={`h-full rounded-full ${m.color.replace("text-", "bg-")}`}
              initial={{ width: 0 }}
              whileInView={{ width: m.w }}
              viewport={{ once: true }}
              transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function KnowledgePreview() {
  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-border bg-background p-2.5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] font-semibold text-text-secondary">Knowledge Base</span>
          <span className="text-[8px] text-success">2.4M chunks indexed</span>
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          {[{ v: "12.4K", l: "Documents" }, { v: "847", l: "Sources" }, { v: "99.2%", l: "Accuracy" }].map((s) => (
            <div key={s.l} className="rounded bg-muted/50 p-1.5 text-center">
              <div className="text-[11px] font-bold text-text-primary">{s.v}</div>
              <div className="text-[8px] text-text-tertiary">{s.l}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-background p-2.5">
        <div className="mb-1.5 flex items-center gap-1.5">
          <BookOpen className="size-2.5 text-chart-2/50" />
          <span className="text-[9px] font-semibold text-text-secondary">Recent Chunks</span>
        </div>
        {["Docker Compose reference", "SSL certificate management", "PostgreSQL tuning guide"].map((t, i) => (
          <div key={i} className="flex items-center gap-1.5 py-1 text-[9px] text-text-tertiary">
            <div className="size-1 rounded-full bg-chart-2/30" />
            {t}
          </div>
        ))}
      </div>
    </div>
  );
}

function AIPreview() {
  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-border bg-background p-2.5">
        <div className="flex items-center gap-1.5 mb-2">
          <Brain className="size-2.5 text-chart-2/50" />
          <span className="text-[9px] font-semibold text-text-secondary">AI Copilot</span>
          <span className="ml-auto flex items-center gap-1 rounded bg-success-subtle px-1 py-0.5 text-[7px] text-success">
            <CheckCircle2 className="size-1.5" /> Active
          </span>
        </div>
        <div className="space-y-1.5">
          <div className="rounded bg-primary-subtle px-2 py-1.5 text-[8px] text-primary text-right">
            Analyze system health
          </div>
          <div className="rounded bg-muted/50 px-2 py-1.5 text-[8px] text-text-secondary">
            All systems operational. 1 optimization found.
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-border bg-background p-2">
          <span className="text-[8px] text-text-tertiary">Executions</span>
          <div className="text-[12px] font-bold text-text-primary">1,247</div>
        </div>
        <div className="rounded-lg border border-border bg-background p-2">
          <span className="text-[8px] text-text-tertiary">Accuracy</span>
          <div className="text-[12px] font-bold text-success">98%</div>
        </div>
      </div>
    </div>
  );
}

function ReportsPreview() {
  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-border bg-background p-2.5">
        <div className="flex items-center gap-1.5 mb-2">
          <FileBarChart className="size-2.5 text-warning/50" />
          <span className="text-[9px] font-semibold text-text-secondary">Weekly Report</span>
        </div>
        <div className="space-y-1.5">
          {[
            { l: "Incidents Resolved", v: "12", c: "text-success" },
            { l: "Avg Response Time", v: "42ms", c: "text-primary" },
            { l: "AI Accuracy", v: "98.2%", c: "text-chart-2" },
          ].map((r) => (
            <div key={r.l} className="flex items-center justify-between text-[9px]">
              <span className="text-text-tertiary">{r.l}</span>
              <span className={`font-semibold ${r.c}`}>{r.v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const PREVIEWS: Record<Tab, React.ReactNode> = {
  overview: <OverviewPreview />,
  infrastructure: <InfrastructurePreview />,
  knowledge: <KnowledgePreview />,
  ai: <AIPreview />,
  reports: <ReportsPreview />,
};

export function ProductTabs() {
  const [active, setActive] = useState<Tab>("overview");

  return (
    <section className="relative py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <p className="section-eyebrow mb-4">Platform</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            One platform. Every workflow.
          </h2>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.15, duration: 0.5 }}
        >
          {/* Tab bar */}
          <div className="mb-6 flex justify-center">
            <div className="inline-flex gap-1 rounded-xl border border-border bg-surface p-1">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActive(tab.key)}
                  className={`relative flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all duration-200 ${
                    active === tab.key ? "text-text-primary" : "text-text-tertiary hover:text-text-secondary"
                  }`}
                >
                  {active === tab.key && (
                    <motion.div
                      layoutId="product-tab"
                      className="absolute inset-0 rounded-lg bg-muted"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <tab.icon className="relative size-3.5" />
                  <span className="relative hidden sm:inline">{tab.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Preview area */}
          <div className="mx-auto max-w-xl rounded-2xl border border-border bg-surface p-5">
            <AnimatePresence mode="wait">
              <motion.div
                key={active}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                {PREVIEWS[active]}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
