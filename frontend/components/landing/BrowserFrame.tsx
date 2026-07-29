"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function BrowserFrame({
  children,
  className,
  url = "app.aegisnex.io/dashboard",
  glow = true,
}: {
  children: React.ReactNode;
  className?: string;
  url?: string;
  glow?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "relative rounded-2xl border border-border bg-surface overflow-hidden",
        glow && "shadow-xl",
        className,
      )}
    >
      {/* Browser chrome */}
      <div className="flex items-center gap-3 border-b border-border bg-surface-glass px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="size-2.5 rounded-full bg-danger/40" />
          <div className="size-2.5 rounded-full bg-warning/40" />
          <div className="size-2.5 rounded-full bg-success/40" />
        </div>
        <div className="flex-1 rounded-lg bg-background px-3 py-1.5 text-center">
          <span className="font-mono text-[11px] text-text-tertiary">{url}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="size-1.5 rounded-full bg-success" />
          <span className="text-[10px] text-text-tertiary">Live</span>
        </div>
      </div>
      {/* Content area */}
      <div className="relative">{children}</div>
    </motion.div>
  );
}
