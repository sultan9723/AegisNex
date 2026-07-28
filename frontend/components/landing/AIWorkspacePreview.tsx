"use client";

import { motion } from "framer-motion";
import {
  Brain, MessageSquare, Library, Activity, CheckCircle2,
  Sparkles, Braces, Clock, Shield, Zap,
} from "lucide-react";
import { BrowserFrame } from "./BrowserFrame";

export function AIWorkspacePreview() {
  const stagger = 0.05;

  return (
    <BrowserFrame url="app.aegisnex.io/ai" className="mx-auto max-w-5xl">
      <div className="grid grid-cols-12 min-h-[380px]">
        {/* Sidebar */}
        <div className="col-span-12 border-b border-border bg-surface p-3 sm:col-span-3 sm:border-b-0 sm:border-r">
          <div className="mb-3 flex items-center gap-2">
            <div className="grid size-5 place-items-center rounded-md bg-chart-2/10">
              <Brain className="size-2.5 text-chart-2" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-text-primary">AI Workspace</p>
              <p className="text-[8px] text-text-tertiary">Intelligence engine</p>
            </div>
          </div>
          <div className="space-y-0.5">
            {[
              { icon: MessageSquare, label: "Chat", active: true },
              { icon: Clock, label: "History", active: false },
              { icon: Activity, label: "Executions", active: false },
              { icon: Library, label: "Memory", active: false },
              { icon: Braces, label: "Tools", active: false },
              { icon: Shield, label: "Policies", active: false },
            ].map((tab, i) => (
              <motion.div
                key={tab.label}
                initial={{ opacity: 0, x: -8 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * stagger, duration: 0.3 }}
                className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] ${
                  tab.active ? "bg-primary-subtle text-primary font-medium" : "text-text-tertiary"
                }`}
              >
                <tab.icon className="size-2.5" />
                {tab.label}
              </motion.div>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="col-span-12 flex flex-col bg-surface sm:col-span-9">
          {/* Chat area */}
          <div className="flex-1 space-y-3 p-3">
            {/* User message */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="flex justify-end"
            >
              <div className="max-w-[80%] rounded-lg bg-primary-subtle px-3 py-2 text-[10px] text-primary">
                Analyze the current system health and recommend optimizations
              </div>
            </motion.div>

            {/* AI Response */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.25 }}
              className="space-y-2"
            >
              {/* Response card */}
              <div className="rounded-lg border border-border bg-background p-3">
                <div className="mb-2 flex items-center gap-2">
                  <div className="grid size-4 place-items-center rounded bg-chart-2/10">
                    <Sparkles className="size-2 text-chart-2" />
                  </div>
                  <span className="text-[10px] font-semibold text-text-secondary">Response</span>
                  <span className="rounded bg-success-subtle px-1 py-0.5 text-[8px] font-medium text-success">
                    Goal achieved
                  </span>
                  <span className="ml-auto rounded bg-muted px-1 py-0.5 text-[8px] text-text-tertiary">
                    98%
                  </span>
                </div>
                <p className="text-[10px] leading-relaxed text-text-secondary">
                  System health analysis complete. Found 3 optimization opportunities:
                  worker replica scaling, SSL certificate renewal, and DB connection pool tuning.
                  All changes are low-risk with rollback capability.
                </p>
              </div>

              {/* Evidence */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.4 }}
                className="rounded-lg border border-border bg-background p-2.5"
              >
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Library className="size-2.5 text-info/50" />
                  <span className="text-[9px] font-semibold text-text-secondary">Evidence</span>
                  <span className="rounded bg-muted px-1 text-[8px] text-text-tertiary">5</span>
                </div>
                <div className="space-y-1">
                  {["Container cpu_usage_avg: 78%", "SSL cert expires in 14 days", "DB pool utilization: 92%"].map((e, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-[9px] text-text-tertiary">
                      <div className="size-1 rounded-full bg-info/30" />
                      {e}
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Execution steps */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.5 }}
                className="rounded-lg border border-border bg-background p-2.5"
              >
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Activity className="size-2.5 text-primary/50" />
                  <span className="text-[9px] font-semibold text-text-secondary">Execution Steps</span>
                </div>
                <div className="space-y-1">
                  {[
                    { node: "health_check", summary: "Collected system metrics", ok: true },
                    { node: "analyzer", summary: "Identified 3 optimization targets", ok: true },
                    { node: "planner", summary: "Generated action plan with rollback", ok: true },
                  ].map((step, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -6 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.55 + i * 0.08 }}
                      className="flex items-center gap-1.5 rounded px-1.5 py-1 text-[9px]"
                    >
                      <CheckCircle2 className="size-2 text-success/60" />
                      <span className="font-mono text-[8px] text-text-tertiary">{step.node}</span>
                      <span className="text-text-secondary">{step.summary}</span>
                    </motion.div>
                  ))}
                </div>
              </motion.div>

              {/* Confidence + reasoning */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.7 }}
                className="flex flex-wrap items-center gap-2"
              >
                <div className="flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1">
                  <Brain className="size-2.5 text-chart-2/40" />
                  <span className="text-[8px] text-text-tertiary">Reasoning: 3 optimization strategies analyzed</span>
                </div>
                <div className="flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1">
                  <Zap className="size-2.5 text-primary/40" />
                  <span className="text-[8px] text-text-tertiary">120ms</span>
                </div>
              </motion.div>
            </motion.div>
          </div>

          {/* Input */}
          <div className="border-t border-border bg-surface px-3 py-2">
            <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
              <span className="text-[10px] text-text-disabled">Ask anything about your infrastructure...</span>
              <div className="ml-auto grid size-5 place-items-center rounded bg-primary/10">
                <Sparkles className="size-2.5 text-primary/60" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}
