"use client";

import { motion } from "framer-motion";
import {
  Server, BrainCircuit, Workflow, Activity,
  CheckCircle2, ChevronRight, Shield,
} from "lucide-react";

const PIPELINE_STEPS = [
  { icon: Server, label: "Collectors", sublabel: "Docker, HTTP, TCP, SSL", color: "primary" },
  { icon: BrainCircuit, label: "Knowledge", sublabel: "RAG, Embeddings", color: "chart-2" },
  { icon: Workflow, label: "Planner", sublabel: "Runbooks, Workflows", color: "success" },
  { icon: BrainCircuit, label: "AI Engine", sublabel: "Reasoning, Analysis", color: "chart-2" },
  { icon: Shield, label: "Approval", sublabel: "RBAC, Gates", color: "warning" },
  { icon: Activity, label: "Dashboard", sublabel: "Live, Real-time", color: "primary" },
];

const colorMap: Record<string, { ring: string; bg: string; text: string; line: string }> = {
  primary: { ring: "ring-primary/15", bg: "bg-primary-subtle", text: "text-primary", line: "from-primary/15" },
  "chart-2": { ring: "ring-chart-2/15", bg: "bg-chart-2/10", text: "text-chart-2", line: "from-chart-2/15" },
  success: { ring: "ring-success/15", bg: "bg-success-subtle", text: "text-success", line: "from-success/15" },
  warning: { ring: "ring-warning/15", bg: "bg-warning-subtle", text: "text-warning", line: "from-warning/15" },
};

export function ArchitecturePipeline() {
  return (
    <section id="architecture" className="relative py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <p className="section-eyebrow mb-4">Architecture</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            End-to-end intelligence pipeline
          </h2>
        </motion.div>

        {/* Desktop: horizontal pipeline */}
        <div className="hidden lg:block">
          <div className="relative">
            {/* Connection line */}
            <div className="absolute left-[5%] right-[5%] top-1/2 h-px -translate-y-1/2">
              <div className="h-full w-full bg-gradient-to-r from-primary/10 via-chart-2/10 to-primary/10" />
              {/* Animated packets */}
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-gradient-to-r from-primary to-chart-2"
                  style={{ left: "5%" }}
                  animate={{ left: ["5%", "95%"] }}
                  transition={{
                    duration: 4 + i,
                    repeat: Infinity,
                    delay: i * 1.5,
                    ease: "linear",
                  }}
                />
              ))}
            </div>

            {/* Steps */}
            <div className="relative grid grid-cols-6 gap-3">
              {PIPELINE_STEPS.map((step, i) => {
                const c = colorMap[step.color];
                return (
                  <motion.div
                    key={step.label}
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1, duration: 0.5 }}
                    className="group relative"
                  >
                    <div className="rounded-xl border border-border bg-surface p-4 text-center transition-all duration-300 hover:border-border-strong hover:shadow-md hover:-translate-y-1">
                      <div className={`mx-auto mb-3 grid size-10 place-items-center rounded-lg ${c.bg} ring-1 ${c.ring} transition-transform duration-300 group-hover:scale-110`}>
                        <step.icon className={`size-5 ${c.text}`} />
                      </div>
                      <p className="text-[12px] font-semibold text-text-primary">{step.label}</p>
                      <p className="mt-0.5 text-[10px] text-text-tertiary">{step.sublabel}</p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Mobile/Tablet: vertical pipeline */}
        <div className="lg:hidden">
          <div className="relative ml-5">
            {/* Vertical line */}
            <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-primary/10 via-chart-2/10 to-primary/10" />
            {/* Animated packet */}
            <motion.div
              className="absolute left-0 size-2 -translate-x-1/2 rounded-full bg-gradient-to-b from-primary to-chart-2"
              style={{ top: "0%" }}
              animate={{ top: ["0%", "100%"] }}
              transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
            />

            <div className="space-y-3">
              {PIPELINE_STEPS.map((step, i) => {
                const c = colorMap[step.color];
                return (
                  <motion.div
                    key={step.label}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.08, duration: 0.4 }}
                    className="relative ml-6"
                  >
                    <div className={`absolute -left-6 top-1/2 grid size-3 place-items-center rounded-full ${c.bg} ring-1 ${c.ring}`}>
                      <step.icon className={`size-1.5 ${c.text}`} />
                    </div>
                    <div className="rounded-lg border border-border bg-surface p-3">
                      <p className="text-[13px] font-semibold text-text-primary">{step.label}</p>
                      <p className="text-[11px] text-text-tertiary">{step.sublabel}</p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
