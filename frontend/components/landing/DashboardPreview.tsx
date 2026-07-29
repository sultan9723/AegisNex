"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity, Shield, Cpu, HardDrive, Network, AlertTriangle,
  CheckCircle2, Clock, Brain, TrendingUp, Zap, Server,
} from "lucide-react";
import { BrowserFrame } from "./BrowserFrame";

function ProgressBar({ value, color, delay = 0 }: { value: number; color: string; delay?: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <motion.div
        className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }}
        whileInView={{ width: `${value}%` }}
        viewport={{ once: true }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay }}
      />
    </div>
  );
}

function PulseDot({ color = "bg-success" }: { color?: string }) {
  return (
    <span className="relative flex size-1.5">
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-60`} />
      <span className={`relative inline-flex size-1.5 rounded-full ${color}`} />
    </span>
  );
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
      {ok ? <PulseDot /> : <PulseDot color="bg-warning" />}
      <span className="text-[10px] text-text-tertiary">{label}</span>
    </div>
  );
}

export function DashboardPreview() {
  const stagger = 0.06;

  return (
    <BrowserFrame url="app.aegisnex.io/dashboard" className="mx-auto max-w-5xl">
      <div className="grid grid-cols-12 gap-px bg-border/50">
        {/* Sidebar */}
        <div className="col-span-12 border-b border-border bg-surface p-3 sm:col-span-3 sm:border-b-0 sm:border-r sm:min-h-[380px]">
          <div className="mb-4 flex items-center gap-2">
            <div className="grid size-6 place-items-center rounded-md bg-gradient-to-br from-primary to-primary/80">
              <Shield className="size-3 text-white" />
            </div>
            <span className="text-[11px] font-bold text-text-primary">AegisNex</span>
          </div>
          <div className="space-y-0.5">
            {["Command Center", "Containers", "Incidents", "Knowledge", "AI Workspace", "Integrations"].map((item, i) => (
              <motion.div
                key={item}
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * stagger, duration: 0.4 }}
                className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[10px] ${
                  i === 0 ? "bg-primary-subtle text-primary font-medium" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                <div className="size-1 rounded-full bg-current opacity-40" />
                {item}
              </motion.div>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="col-span-12 space-y-3 bg-surface p-3 sm:col-span-9">
          {/* Status bar */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1, duration: 0.5 }}
            className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <PulseDot />
              <span className="text-[10px] font-medium text-text-secondary">All Systems Operational</span>
            </div>
            <div className="hidden items-center gap-2 sm:flex">
              <StatusChip label="API" ok />
              <StatusChip label="DB" ok />
              <StatusChip label="Workers" ok />
            </div>
          </motion.div>

          {/* Metric cards */}
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {[
              { icon: Cpu, label: "CPU", value: "34", unit: "%", color: "text-primary", progress: 34, pColor: "bg-primary" },
              { icon: HardDrive, label: "Memory", value: "6.2", unit: "GB", color: "text-chart-2", progress: 62, pColor: "bg-chart-2" },
              { icon: Network, label: "Network", value: "847", unit: "Mbps", color: "text-success", progress: 84, pColor: "bg-success" },
              { icon: Server, label: "Containers", value: "24", unit: "up", color: "text-warning", progress: 100, pColor: "bg-warning" },
            ].map((m, i) => (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.15 + i * stagger, duration: 0.5 }}
                className="rounded-lg border border-border bg-background p-2.5"
              >
                <div className="mb-1.5 flex items-center justify-between">
                  <m.icon className={`size-3 ${m.color}`} />
                  <span className="text-[9px] text-text-tertiary">{m.label}</span>
                </div>
                <div className="text-[16px] font-bold text-text-primary">
                  {m.value}<span className="text-[10px] font-normal text-text-tertiary ml-0.5">{m.unit}</span>
                </div>
                <ProgressBar value={m.progress} color={m.pColor} delay={0.2 + i * 0.1} />
              </motion.div>
            ))}
          </div>

          {/* Two column: Incidents + AI */}
          <div className="grid gap-2 sm:grid-cols-2">
            {/* Recent Incidents */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.4, duration: 0.5 }}
              className="rounded-lg border border-border bg-background p-2.5"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-semibold text-text-secondary">Recent Incidents</span>
                <AlertTriangle className="size-3 text-warning/60" />
              </div>
              <div className="space-y-1.5">
                {[
                  { title: "SSL cert expiring", severity: "warning", time: "2m ago" },
                  { title: "Container restart", severity: "info", time: "14m ago" },
                  { title: "High CPU spike", severity: "success", time: "1h ago" },
                ].map((inc, i) => (
                  <motion.div
                    key={inc.title}
                    initial={{ opacity: 0, x: -8 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.5 + i * 0.08 }}
                    className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5"
                  >
                    <div className={`size-1.5 rounded-full ${
                      inc.severity === "warning" ? "bg-warning" :
                      inc.severity === "info" ? "bg-primary" : "bg-success"
                    }`} />
                    <span className="flex-1 truncate text-[10px] text-text-secondary">{inc.title}</span>
                    <span className="text-[9px] text-text-disabled">{inc.time}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            {/* AI Recommendations */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.48, duration: 0.5 }}
              className="rounded-lg border border-border bg-background p-2.5"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-semibold text-text-secondary">AI Recommendations</span>
                <Brain className="size-3 text-chart-2/60" />
              </div>
              <div className="space-y-1.5">
                {[
                  { text: "Scale worker replicas to 3", conf: 94 },
                  { text: "Update SSL certificate", conf: 98 },
                  { text: "Optimize DB connection pool", conf: 87 },
                ].map((rec, i) => (
                  <motion.div
                    key={rec.text}
                    initial={{ opacity: 0, x: -8 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.55 + i * 0.08 }}
                    className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5"
                  >
                    <Zap className="size-2.5 text-primary/50" />
                    <span className="flex-1 truncate text-[10px] text-text-secondary">{rec.text}</span>
                    <span className="text-[9px] text-primary/60">{rec.conf}%</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Activity bar */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.65, duration: 0.4 }}
            className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2"
          >
            <Activity className="size-3 text-primary/40" />
            <div className="flex-1 overflow-hidden">
              <div className="flex items-center gap-4 text-[9px] text-text-tertiary">
                <span className="flex items-center gap-1"><TrendingUp className="size-2.5" /> 10,247 events/s</span>
                <span className="flex items-center gap-1"><Clock className="size-2.5" /> &lt;50ms p99</span>
                <span className="flex items-center gap-1"><CheckCircle2 className="size-2.5" /> 99.97% uptime</span>
              </div>
            </div>
            <div className="hidden items-center gap-1 sm:flex">
              {[40, 65, 45, 80, 55, 70, 60, 75, 50, 85, 45, 90].map((h, i) => (
                <div key={i} className="w-1 rounded-full bg-primary/20" style={{ height: `${h * 0.24}px` }} />
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </BrowserFrame>
  );
}
