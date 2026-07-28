"use client";

import { motion } from "framer-motion";

const CHIPS = [
  { label: "Docker", color: "from-info/10 to-info/5", border: "border-info/20", text: "text-info/70" },
  { label: "Kubernetes", color: "from-primary/10 to-primary/5", border: "border-primary/20", text: "text-primary/70" },
  { label: "Prometheus", color: "from-warning/10 to-warning/5", border: "border-warning/20", text: "text-warning/70" },
  { label: "Grafana", color: "from-warning/10 to-warning/5", border: "border-warning/20", text: "text-warning/70" },
  { label: "Redis", color: "from-danger/10 to-danger/5", border: "border-danger/20", text: "text-danger/70" },
  { label: "PostgreSQL", color: "from-info/10 to-info/5", border: "border-info/20", text: "text-info/70" },
  { label: "OpenAI", color: "from-success/10 to-success/5", border: "border-success/20", text: "text-success/70" },
  { label: "Anthropic", color: "from-chart-2/10 to-chart-2/5", border: "border-chart-2/20", text: "text-chart-2/70" },
  { label: "MCP", color: "from-primary/10 to-primary/5", border: "border-primary/20", text: "text-primary/70" },
];

const positions = [
  { left: "5%", top: "20%", delay: 0 },
  { right: "8%", top: "15%", delay: 1.5 },
  { left: "12%", top: "65%", delay: 3 },
  { right: "15%", top: "60%", delay: 0.8 },
  { left: "25%", top: "80%", delay: 2.2 },
  { right: "25%", top: "75%", delay: 4 },
  { left: "8%", top: "42%", delay: 1.2 },
  { right: "5%", top: "38%", delay: 2.8 },
  { left: "18%", top: "10%", delay: 3.5 },
];

export function FloatingChips() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {CHIPS.map((chip, i) => {
        const pos = positions[i];
        return (
          <motion.div
            key={chip.label}
            className="absolute hidden lg:block"
            style={{ left: pos.left, right: pos.right, top: pos.top }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.5 + i * 0.1, duration: 0.6 }}
          >
            <motion.div
              animate={{
                y: [0, -8, 0, 6, 0],
                x: [0, 4, 0, -3, 0],
              }}
              transition={{
                duration: 8 + i * 1.5,
                repeat: Infinity,
                ease: "easeInOut",
                delay: pos.delay,
              }}
              className={`flex items-center gap-2 rounded-full border ${chip.border} bg-gradient-to-br ${chip.color} px-3.5 py-1.5 backdrop-blur-sm`}
            >
              <div className="size-1.5 rounded-full bg-current opacity-40" />
              <span className={`text-[11px] font-medium ${chip.text}`}>{chip.label}</span>
            </motion.div>
          </motion.div>
        );
      })}
    </div>
  );
}
