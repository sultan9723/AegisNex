"use client";

import { motion } from "framer-motion";
import {
  BrainCircuit, Radar, Workflow, Layers, MonitorCheck, Fingerprint,
} from "lucide-react";

const FEATURES = [
  {
    icon: BrainCircuit,
    title: "AI Copilot",
    description: "Natural language interface for infrastructure queries, incident analysis, and autonomous remediation.",
    stat: "98% recommendation accuracy",
    color: "from-chart-2/10 to-chart-2/5",
    iconColor: "text-chart-2",
    borderColor: "hover:border-chart-2/20",
  },
  {
    icon: Radar,
    title: "Autonomous Monitoring",
    description: "Self-healing infrastructure with intelligent alerting, anomaly detection, and automated response.",
    stat: "10K+ events/second",
    color: "from-primary/10 to-primary/5",
    iconColor: "text-primary",
    borderColor: "hover:border-primary/20",
  },
  {
    icon: Workflow,
    title: "Workflow Engine",
    description: "Visual runbooks and automated remediation pipelines with approval gates and rollback.",
    stat: "135 automations",
    color: "from-success/10 to-success/5",
    iconColor: "text-success",
    borderColor: "hover:border-success/20",
  },
  {
    icon: Layers,
    title: "Knowledge Base",
    description: "RAG-powered document intelligence with automatic chunking, embedding, and semantic search.",
    stat: "2.4M indexed chunks",
    color: "from-warning/10 to-warning/5",
    iconColor: "text-warning",
    borderColor: "hover:border-warning/20",
  },
  {
    icon: MonitorCheck,
    title: "Full-Stack Observability",
    description: "Infrastructure, containers, SSL certificates, HTTP endpoints, and TCP targets in one pane.",
    stat: "52 integrations",
    color: "from-danger/10 to-danger/5",
    iconColor: "text-danger",
    borderColor: "hover:border-danger/20",
  },
  {
    icon: Fingerprint,
    title: "Enterprise Security",
    description: "RBAC, JWT auth, API keys, audit logging, and compliance frameworks built in from day one.",
    stat: "JWT + RBAC",
    color: "from-info/10 to-info/5",
    iconColor: "text-info",
    borderColor: "hover:border-info/20",
  },
];

export function Capabilities() {
  return (
    <section id="capabilities" className="relative py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <p className="section-eyebrow mb-4">Core Capabilities</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            Built for modern infrastructure
          </h2>
        </motion.div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: i * 0.08, duration: 0.5 }}
              className={`group relative rounded-xl border border-border bg-surface p-6 transition-all duration-500 hover:border-border-strong hover:shadow-md hover:-translate-y-1 ${f.borderColor} h-full`}
            >
              <div className="relative">
                <div className={`mb-4 inline-flex size-10 items-center justify-center rounded-lg bg-gradient-to-br ${f.color} transition-transform duration-500 group-hover:scale-110`}>
                  <f.icon className={`size-5 ${f.iconColor}`} />
                </div>
                <h3 className="mb-2 text-[15px] font-semibold text-text-primary">{f.title}</h3>
                <p className="mb-4 text-[13px] leading-relaxed text-text-secondary">{f.description}</p>
                <div className="flex items-center gap-1.5">
                  <div className="h-px flex-1 bg-gradient-to-r from-border to-transparent" />
                  <span className="text-[11px] font-medium text-text-disabled">{f.stat}</span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
