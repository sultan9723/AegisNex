"use client";

import { motion } from "framer-motion";
import {
  MessageSquare, BrainCircuit, BookOpen, Container, Activity,
  ShieldAlert, ShieldCheck, CheckCircle, Zap, LayoutDashboard,
  ArrowRight, ChevronRight,
} from "lucide-react";

const AGENT_STEPS = [
  { icon: MessageSquare, label: "User Query", sublabel: "Natural language", color: "primary" },
  { icon: BrainCircuit, label: "Planner", sublabel: "Task decomposition", color: "chart-2" },
  { icon: BookOpen, label: "Knowledge", sublabel: "RAG retrieval", color: "info" },
  { icon: Container, label: "Docker", sublabel: "Tool execution", color: "primary" },
  { icon: Activity, label: "Metrics", sublabel: "Data collection", color: "success" },
  { icon: ShieldAlert, label: "Risk Assessor", sublabel: "Impact analysis", color: "warning" },
  { icon: ShieldCheck, label: "Policy Check", sublabel: "RBAC gates", color: "chart-2" },
  { icon: CheckCircle, label: "Verifier", sublabel: "Sanity checks", color: "success" },
  { icon: Zap, label: "Decision", sublabel: "Action approval", color: "primary" },
  { icon: LayoutDashboard, label: "Dashboard", sublabel: "Live update", color: "info" },
];

const colorMap: Record<string, { ring: string; bg: string; text: string; activeBg: string }> = {
  primary: { ring: "ring-primary/15", bg: "bg-primary-subtle", text: "text-primary", activeBg: "bg-primary/10" },
  "chart-2": { ring: "ring-chart-2/15", bg: "bg-chart-2/10", text: "text-chart-2", activeBg: "bg-chart-2/10" },
  info: { ring: "ring-info/15", bg: "bg-info-subtle", text: "text-info", activeBg: "bg-info/10" },
  success: { ring: "ring-success/15", bg: "bg-success-subtle", text: "text-success", activeBg: "bg-success/10" },
  warning: { ring: "ring-warning/15", bg: "bg-warning-subtle", text: "text-warning", activeBg: "bg-warning/10" },
};

export function AgentExecution() {
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
          <p className="section-eyebrow mb-4">Agent Orchestration</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            How the AI agent thinks
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[14px] text-text-secondary">
            From query to action in seconds — a multi-step orchestration pipeline with safety gates at every stage.
          </p>
        </motion.div>

        {/* Desktop: horizontal flowing pipeline */}
        <div className="hidden xl:block">
          <div className="relative rounded-2xl border border-border bg-surface p-8">
            {/* Animated connection line */}
            <div className="absolute left-8 right-8 top-1/2 h-px -translate-y-1/2">
              <div className="h-full w-full bg-gradient-to-r from-primary/10 via-chart-2/10 to-primary/10" />
              {/* Animated packet flowing through */}
              <motion.div
                className="absolute top-1/2 size-2.5 -translate-y-1/2 rounded-full bg-gradient-to-r from-primary to-chart-2 shadow-sm shadow-primary/30"
                style={{ left: "0%" }}
                animate={{ left: ["0%", "100%"] }}
                transition={{ duration: 6, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
              />
              <motion.div
                className="absolute top-1/2 size-2.5 -translate-y-1/2 rounded-full bg-gradient-to-r from-chart-2 to-success shadow-sm shadow-chart-2/30"
                style={{ left: "0%" }}
                animate={{ left: ["0%", "100%"] }}
                transition={{ duration: 6, repeat: Infinity, ease: "linear", delay: 3, repeatDelay: 2 }}
              />
            </div>

            {/* Steps */}
            <div className="relative grid grid-cols-10 gap-2">
              {AGENT_STEPS.map((step, i) => {
                const c = colorMap[step.color];
                return (
                  <motion.div
                    key={step.label}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.08, duration: 0.5 }}
                    className="group relative"
                  >
                    <div className="flex flex-col items-center text-center">
                      {/* Node circle */}
                      <motion.div
                        whileHover={{ scale: 1.1 }}
                        className={`relative mb-3 grid size-12 place-items-center rounded-xl border border-border bg-background shadow-sm transition-all duration-300 group-hover:border-border-strong group-hover:shadow-md ${c.activeBg}`}
                      >
                        <step.icon className={`size-5 ${c.text}`} />
                        {/* Pulse on active step */}
                        {i === 0 && (
                          <span className="absolute -top-1 -right-1 flex size-2.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-40" />
                            <span className="relative inline-flex size-2 rounded-full bg-primary" />
                          </span>
                        )}
                      </motion.div>
                      <p className="text-[10px] font-semibold text-text-primary leading-tight">{step.label}</p>
                      <p className="mt-0.5 text-[8px] text-text-tertiary leading-tight">{step.sublabel}</p>
                    </div>
                    {/* Arrow between steps */}
                    {i < AGENT_STEPS.length - 1 && (
                      <div className="absolute -right-1 top-5 text-text-disabled">
                        <ChevronRight className="size-3" />
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>

            {/* Legend */}
            <div className="mt-6 flex items-center justify-center gap-6 text-[10px] text-text-tertiary">
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-primary" /> Query & Decision
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-chart-2" /> AI & Policy
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-success" /> Execution & Verification
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-warning" /> Risk Assessment
              </span>
            </div>
          </div>
        </div>

        {/* Mobile/Tablet: vertical pipeline */}
        <div className="xl:hidden">
          <div className="relative rounded-2xl border border-border bg-surface p-6">
            <div className="relative ml-5">
              {/* Vertical line */}
              <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-primary/10 via-chart-2/10 to-primary/10" />
              {/* Animated packet */}
              <motion.div
                className="absolute left-0 size-2 -translate-x-1/2 rounded-full bg-gradient-to-b from-primary to-chart-2 shadow-sm shadow-primary/30"
                style={{ top: "0%" }}
                animate={{ top: ["0%", "100%"] }}
                transition={{ duration: 8, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
              />

              <div className="space-y-2">
                {AGENT_STEPS.map((step, i) => {
                  const c = colorMap[step.color];
                  return (
                    <motion.div
                      key={step.label}
                      initial={{ opacity: 0, x: -12 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: i * 0.06, duration: 0.4 }}
                      className="relative ml-6"
                    >
                      <div className={`absolute -left-6 top-1/2 grid size-3 place-items-center rounded-full ${c.bg} ring-1 ${c.ring}`}>
                        <step.icon className={`size-1.5 ${c.text}`} />
                      </div>
                      <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
                        <span className="text-[11px] font-semibold text-text-primary">{step.label}</span>
                        <span className="text-[9px] text-text-tertiary">{step.sublabel}</span>
                        {i === 0 && (
                          <span className="ml-auto size-1.5 rounded-full bg-primary animate-pulse" />
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
