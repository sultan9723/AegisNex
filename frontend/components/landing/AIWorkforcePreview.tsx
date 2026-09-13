"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Bot, CheckCircle2, Clock, ShieldCheck, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { getWorkforceStats, type WorkforceStats } from "@/lib/api";
import { BrowserFrame } from "./BrowserFrame";

function Stat({ label, value, icon: Icon }: { label: string; value: string | number; icon: React.ElementType }) {
  return (
    <div className="rounded-lg border border-border bg-background p-2.5">
      <div className="mb-1.5 flex items-center justify-between">
        <Icon className="size-3 text-primary/60" />
        <span className="text-[9px] text-text-tertiary">{label}</span>
      </div>
      <div className="text-[16px] font-bold text-text-primary">{value}</div>
    </div>
  );
}

export function AIWorkforcePreview() {
  const { user } = useAuth();
  const [stats, setStats] = useState<WorkforceStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!user) {
      setStats(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    getWorkforceStats()
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const liveStats = user && stats && !error ? stats : null;
  const live = liveStats !== null;

  return (
    <BrowserFrame url="app.aegisnex.io/workforce" className="mx-auto max-w-5xl">
      <div className="grid grid-cols-12 min-h-[380px]">
        <div className="col-span-12 border-b border-border bg-surface p-3 sm:col-span-3 sm:border-b-0 sm:border-r">
          <div className="mb-3 flex items-center gap-2">
            <div className="grid size-5 place-items-center rounded-md bg-primary/10">
              <Bot className="size-2.5 text-primary" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-text-primary">AI Workforce</p>
              <p className="text-[8px] text-text-tertiary">Agent operations</p>
            </div>
          </div>
          <div className="space-y-0.5">
            {["Agents", "Executions", "Playground", "Policies", "Health"].map((item, i) => (
              <motion.div
                key={item}
                initial={{ opacity: 0, x: -8 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05, duration: 0.3 }}
                className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] ${
                  i === 0 ? "bg-primary-subtle text-primary font-medium" : "text-text-tertiary"
                }`}
              >
                <div className="size-1 rounded-full bg-current opacity-40" />
                {item}
              </motion.div>
            ))}
          </div>
        </div>

        <div className="col-span-12 flex flex-col bg-surface sm:col-span-9">
          <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
            <div>
              <p className="text-[10px] font-semibold text-text-secondary">Workforce overview</p>
              <p className="text-[9px] text-text-tertiary">Tenant-scoped agent state and execution history</p>
            </div>
            <span className="flex items-center gap-1.5 text-[9px] text-text-tertiary">
              <span className={`size-1.5 rounded-full ${live ? "bg-success" : "bg-text-disabled"}`} />
              {loading ? "Loading" : live ? "Live workspace data" : "Product Preview"}
            </span>
          </div>

          <div className="flex-1 space-y-3 p-3">
            {liveStats ? (
              <>
                <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
                  <Stat label="Total agents" value={liveStats.total_agents} icon={Users} />
                  <Stat label="Active" value={liveStats.active_agents} icon={Activity} />
                  <Stat label="Executions" value={liveStats.total_executions} icon={Clock} />
                  <Stat label="Trust score" value={`${Math.round(liveStats.avg_trust_score)}%`} icon={ShieldCheck} />
                </div>
                <div className="rounded-lg border border-border bg-background p-2.5">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-text-secondary">Execution health</span>
                    <CheckCircle2 className="size-3 text-success/70" />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded bg-muted/50 p-2">
                      <div className="text-[13px] font-bold text-success">{liveStats.total_successes}</div>
                      <div className="text-[8px] text-text-tertiary">Successful</div>
                    </div>
                    <div className="rounded bg-muted/50 p-2">
                      <div className="text-[13px] font-bold text-text-primary">{liveStats.avg_success_rate}%</div>
                      <div className="text-[8px] text-text-tertiary">Success rate</div>
                    </div>
                    <div className="rounded bg-muted/50 p-2">
                      <div className="text-[13px] font-bold text-text-primary">${liveStats.total_cost.toFixed(3)}</div>
                      <div className="text-[8px] text-text-tertiary">Tracked cost</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-border bg-background p-6 text-center">
                <div className="max-w-sm">
                  <Bot className="mx-auto mb-3 size-6 text-primary/50" />
                  <p className="text-[11px] font-semibold text-text-secondary">
                    {error ? "Workforce data is temporarily unavailable" : "Sign in to view live AI Workforce data"}
                  </p>
                  <p className="mt-1 text-[9px] text-text-tertiary">
                    Agent counts, execution health, trust, and cost are loaded from the authenticated Workforce workspace.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </BrowserFrame>
  );
}
