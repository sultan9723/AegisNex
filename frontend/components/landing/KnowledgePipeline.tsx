"use client";

import { motion } from "framer-motion";
import {
  FileText, Scissors, Brain, Database, Search,
  Layers, Sparkles, MessageSquare, ArrowRight,
} from "lucide-react";

const PIPELINE_STEPS = [
  { icon: FileText, label: "Document Ingestion", sublabel: "PDF, Markdown, HTML", color: "info" },
  { icon: Scissors, label: "Chunking", sublabel: "Semantic splitting", color: "warning" },
  { icon: Brain, label: "Embeddings", sublabel: "Vector encoding", color: "chart-2" },
  { icon: Database, label: "Vector Store", sublabel: "Indexed storage", color: "success" },
  { icon: Search, label: "Semantic Search", sublabel: "Context retrieval", color: "primary" },
  { icon: Layers, label: "Context Assembly", sublabel: "Prompt construction", color: "chart-2" },
  { icon: Sparkles, label: "LLM Generation", sublabel: "Reasoning engine", color: "primary" },
  { icon: MessageSquare, label: "Answer", sublabel: "Grounded response", color: "success" },
];

const colorMap: Record<string, { ring: string; bg: string; text: string; activeBg: string }> = {
  primary: { ring: "ring-primary/15", bg: "bg-primary-subtle", text: "text-primary", activeBg: "bg-primary/10" },
  "chart-2": { ring: "ring-chart-2/15", bg: "bg-chart-2/10", text: "text-chart-2", activeBg: "bg-chart-2/10" },
  info: { ring: "ring-info/15", bg: "bg-info-subtle", text: "text-info", activeBg: "bg-info/10" },
  success: { ring: "ring-success/15", bg: "bg-success-subtle", text: "text-success", activeBg: "bg-success/10" },
  warning: { ring: "ring-warning/15", bg: "bg-warning-subtle", text: "text-warning", activeBg: "bg-warning/10" },
};

export function KnowledgePipeline() {
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
          <p className="section-eyebrow mb-4">Knowledge Engine</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            From documents to answers
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[14px] text-text-secondary">
            RAG-powered knowledge pipeline that ingests, chunks, embeds, and retrieves — so the AI always has the right context.
          </p>
        </motion.div>

        {/* Desktop: horizontal pipeline */}
        <div className="hidden lg:block">
          <div className="relative rounded-2xl border border-border bg-surface p-8">
            {/* Animated connection line */}
            <div className="absolute left-8 right-8 top-1/2 h-px -translate-y-1/2">
              <div className="h-full w-full bg-gradient-to-r from-info/10 via-chart-2/10 to-success/10" />
              {/* Animated packet */}
              <motion.div
                className="absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-gradient-to-r from-info to-chart-2 shadow-sm shadow-info/30"
                style={{ left: "0%" }}
                animate={{ left: ["0%", "100%"] }}
                transition={{ duration: 5, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
              />
              <motion.div
                className="absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-gradient-to-r from-chart-2 to-success shadow-sm shadow-chart-2/30"
                style={{ left: "0%" }}
                animate={{ left: ["0%", "100%"] }}
                transition={{ duration: 5, repeat: Infinity, ease: "linear", delay: 2.5, repeatDelay: 2 }}
              />
            </div>

            {/* Steps */}
            <div className="relative grid grid-cols-8 gap-2">
              {PIPELINE_STEPS.map((step, i) => {
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
                      <motion.div
                        whileHover={{ scale: 1.1 }}
                        className={`relative mb-3 grid size-11 place-items-center rounded-xl border border-border bg-background shadow-sm transition-all duration-300 group-hover:border-border-strong group-hover:shadow-md ${c.activeBg}`}
                      >
                        <step.icon className={`size-5 ${c.text}`} />
                      </motion.div>
                      <p className="text-[10px] font-semibold text-text-primary leading-tight">{step.label}</p>
                      <p className="mt-0.5 text-[8px] text-text-tertiary leading-tight">{step.sublabel}</p>
                    </div>
                    {i < PIPELINE_STEPS.length - 1 && (
                      <div className="absolute -right-1 top-4 text-text-disabled">
                        <ArrowRight className="size-3" />
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>

            {/* Stats bar */}
            <div className="mt-6 flex items-center justify-center gap-8 text-[10px] text-text-tertiary">
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-info" /> 2.4M chunks indexed
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-chart-2" /> 1536-dim embeddings
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-success" /> {"<50ms"} retrieval latency
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-primary" /> 99.2% relevance
              </span>
            </div>
          </div>
        </div>

        {/* Mobile/Tablet: vertical pipeline */}
        <div className="lg:hidden">
          <div className="relative rounded-2xl border border-border bg-surface p-6">
            <div className="relative ml-5">
              <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-info/10 via-chart-2/10 to-success/10" />
              <motion.div
                className="absolute left-0 size-2 -translate-x-1/2 rounded-full bg-gradient-to-b from-info to-success shadow-sm shadow-info/30"
                style={{ top: "0%" }}
                animate={{ top: ["0%", "100%"] }}
                transition={{ duration: 7, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
              />

              <div className="space-y-2">
                {PIPELINE_STEPS.map((step, i) => {
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
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {/* Stats */}
            <div className="mt-4 grid grid-cols-2 gap-2">
              {[
                { label: "Chunks", value: "2.4M", color: "text-info" },
                { label: "Latency", value: "<50ms", color: "text-chart-2" },
                { label: "Accuracy", value: "99.2%", color: "text-success" },
                { label: "Sources", value: "847", color: "text-primary" },
              ].map((s) => (
                <div key={s.label} className="rounded-lg bg-muted/50 px-3 py-2 text-center">
                  <div className={`text-[12px] font-bold ${s.color}`}>{s.value}</div>
                  <div className="text-[8px] text-text-tertiary">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
