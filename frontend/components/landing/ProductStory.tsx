"use client";

import { motion } from "framer-motion";
import {
  Bell, MessageSquare, Terminal, GitBranch, FileText,
  Shield, Brain, BookOpen, CheckCircle2, ArrowDown,
} from "lucide-react";

const DISCONNECTED_TOOLS = [
  { icon: Bell, label: "PagerDuty", color: "text-danger/60" },
  { icon: MessageSquare, label: "Slack", color: "text-warning/60" },
  { icon: Terminal, label: "SSH", color: "text-text-tertiary" },
  { icon: GitBranch, label: "Git", color: "text-chart-2/60" },
  { icon: FileText, label: "Runbooks", color: "text-info/60" },
];

const CONNECTED_FLOW = [
  { icon: Shield, label: "AegisNex", color: "text-primary" },
  { icon: Brain, label: "AI Engine", color: "text-chart-2" },
  { icon: BookOpen, label: "Knowledge", color: "text-success" },
  { icon: CheckCircle2, label: "Decision", color: "text-warning" },
];

export function ProductStory() {
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
          <p className="section-eyebrow mb-4">The Transformation</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            From chaos to command
          </h2>
        </motion.div>

        <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
          {/* Left: Disconnected tools */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <p className="mb-6 text-[11px] font-semibold uppercase tracking-[0.12em] text-danger/60">
              Before AegisNex
            </p>
            <div className="rounded-2xl border border-border bg-surface p-6">
              <div className="flex flex-wrap items-center justify-center gap-3">
                {DISCONNECTED_TOOLS.map((tool, i) => (
                  <motion.div
                    key={tool.label}
                    initial={{ opacity: 0, scale: 0.8 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.1 + i * 0.08, duration: 0.4 }}
                    className="flex flex-col items-center gap-1.5 rounded-xl border border-border bg-background px-4 py-3"
                  >
                    <tool.icon className={`size-5 ${tool.color}`} />
                    <span className="text-[10px] text-text-tertiary">{tool.label}</span>
                  </motion.div>
                ))}
              </div>
              {/* Disconnection arrows */}
              <div className="mt-4 flex justify-center">
                <div className="flex gap-4">
                  {[0, 1, 2, 3].map((i) => (
                    <motion.div
                      key={i}
                      className="h-px w-8 bg-gradient-to-r from-danger/20 to-transparent"
                      style={{ transform: `rotate(${(i - 1.5) * 15}deg)` }}
                      initial={{ scaleX: 0 }}
                      whileInView={{ scaleX: 1 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.5 + i * 0.05 }}
                    />
                  ))}
                </div>
              </div>
              <p className="mt-4 text-center text-[12px] text-text-disabled">
                Disconnected. Manual. Slow.
              </p>
            </div>
          </motion.div>

          {/* Right: Connected flow */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.15 }}
          >
            <p className="mb-6 text-[11px] font-semibold uppercase tracking-[0.12em] text-primary/60">
              With AegisNex
            </p>
            <div className="rounded-2xl border border-border bg-surface p-6">
              <div className="flex flex-col items-center gap-0">
                {CONNECTED_FLOW.map((step, i) => (
                  <div key={step.label} className="flex flex-col items-center">
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8 }}
                      whileInView={{ opacity: 1, scale: 1 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.2 + i * 0.12, duration: 0.4 }}
                      className="flex items-center gap-2.5 rounded-xl border border-border bg-background px-5 py-3"
                    >
                      <step.icon className={`size-4 ${step.color}`} />
                      <span className="text-[12px] font-medium text-text-secondary">{step.label}</span>
                    </motion.div>
                    {i < CONNECTED_FLOW.length - 1 && (
                      <motion.div
                        initial={{ scaleY: 0, opacity: 0 }}
                        whileInView={{ scaleY: 1, opacity: 1 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.3 + i * 0.12, duration: 0.3 }}
                        className="flex flex-col items-center"
                      >
                        <div className="h-4 w-px bg-gradient-to-b from-primary/20 to-primary/5" />
                        <ArrowDown className="size-2.5 text-primary/30" />
                      </motion.div>
                    )}
                  </div>
                ))}
                {/* Final arrow to engineer */}
                <motion.div
                  initial={{ scaleY: 0, opacity: 0 }}
                  whileInView={{ scaleY: 1, opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.7, duration: 0.3 }}
                  className="flex flex-col items-center"
                >
                  <div className="h-4 w-px bg-gradient-to-b from-warning/20 to-primary/10" />
                  <ArrowDown className="size-2.5 text-success/30" />
                </motion.div>
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.8, duration: 0.4 }}
                  className="mt-1 rounded-xl border border-success-border bg-success-subtle px-5 py-2.5"
                >
                  <span className="text-[12px] font-medium text-success">Engineer takes action</span>
                </motion.div>
              </div>
              <p className="mt-4 text-center text-[12px] text-text-disabled">
                Connected. Autonomous. Instant.
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
