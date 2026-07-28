"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Zap, Sparkles, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Spinner } from "@/components/common/LoadingState";

import { LandingNav } from "@/components/landing/LandingNav";
import { NetworkBackground } from "@/components/landing/NetworkBackground";
import { FloatingChips } from "@/components/landing/FloatingChips";
import { DashboardPreview } from "@/components/landing/DashboardPreview";
import { ProductStory } from "@/components/landing/ProductStory";
import { Capabilities } from "@/components/landing/Capabilities";
import { ArchitecturePipeline } from "@/components/landing/ArchitecturePipeline";
import { AgentExecution } from "@/components/landing/AgentExecution";
import { KnowledgePipeline } from "@/components/landing/KnowledgePipeline";
import { IntegrationGrid } from "@/components/landing/IntegrationGrid";
import { AIWorkspacePreview } from "@/components/landing/AIWorkspacePreview";
import { ProductTabs } from "@/components/landing/ProductTabs";
import { SecurityGrid } from "@/components/landing/SecurityGrid";

const METRICS = [
  { value: "99.97%", label: "Uptime SLA" },
  { value: "<50ms", label: "Response Time" },
  { value: "10K+", label: "Events/Second" },
  { value: "0", label: "False Negatives" },
];

export default function LandingPage() {
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState("");
  const { demoLogin } = useAuth();
  const router = useRouter();

  const handleDemoLogin = useCallback(async () => {
    setDemoError("");
    setDemoLoading(true);
    try {
      await demoLogin();
      router.push("/dashboard");
    } catch (err) {
      setDemoError(err instanceof Error ? err.message : "Demo login failed. Is the backend running?");
    } finally {
      setDemoLoading(false);
    }
  }, [demoLogin, router]);

  return (
    <div className="min-h-screen bg-background text-text-primary overflow-x-hidden">
      <LandingNav />

      {/* Hero */}
      <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-28">
        {/* Background */}
        <div className="absolute inset-0 bg-gradient-hero" />
        <div className="absolute inset-0 bg-grid opacity-30" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 size-[600px] rounded-full bg-primary/[0.02] blur-[120px]" />
        <NetworkBackground />
        <FloatingChips />

        <div className="relative mx-auto max-w-6xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary-subtle px-4 py-1.5 text-[11px] font-medium text-primary">
              <span className="relative flex size-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex size-1.5 rounded-full bg-primary" />
              </span>
              AI-Native Infrastructure Intelligence
            </div>
            <h1 className="mb-6 text-[2.5rem] font-bold tracking-[-0.04em] sm:text-[3.25rem] lg:text-[3.75rem] leading-[1.05]">
              Your infrastructure,{" "}
              <span className="gradient-text">autonomously secured</span>
            </h1>
            <p className="mb-10 text-[15px] text-text-secondary sm:text-[17px] leading-relaxed max-w-xl mx-auto">
              Unified monitoring, AI-powered incident response, and autonomous remediation - from a single command center.
            </p>
            <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <button
                onClick={handleDemoLogin}
                disabled={demoLoading}
                className="group inline-flex h-12 items-center gap-2.5 rounded-xl bg-primary px-7 text-[13px] font-semibold text-white shadow-sm shadow-primary/20 transition-all hover:shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5 disabled:opacity-50"
              >
                {demoLoading ? <Spinner className="size-4" /> : <Zap className="size-4 transition-transform group-hover:scale-110" />}
                {demoLoading ? "Signing in..." : "Try Demo Workspace"}
                {!demoLoading && <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />}
              </button>
              <a
                href="#architecture"
                className="inline-flex h-12 items-center gap-2 rounded-xl border border-border bg-surface px-6 text-[13px] font-medium text-text-secondary transition-all hover:border-border-strong hover:bg-background hover:text-text-primary"
              >
                View Architecture
              </a>
            </div>
            {demoError && (
              <p className="mt-4 text-sm text-danger">{demoError}</p>
            )}
          </div>

          {/* Metrics bar */}
          <div className="mx-auto mt-20 grid max-w-2xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
            {METRICS.map((m) => (
              <div key={m.label} className="bg-surface px-6 py-5 text-center">
                <div className="text-[22px] font-bold tracking-tight text-text-primary">{m.value}</div>
                <div className="mt-1 text-[11px] text-text-tertiary">{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Live Dashboard Preview */}
      <section className="relative py-12 sm:py-20">
        <div className="mx-auto max-w-6xl px-6">
          <DashboardPreview />
        </div>
      </section>

      <div className="divider mx-auto max-w-4xl" />

      {/* Product Story */}
      <ProductStory />

      <div className="divider mx-auto max-w-4xl" />

      {/* Core Capabilities */}
      <Capabilities />

      <div className="divider mx-auto max-w-4xl" />

      {/* Architecture Pipeline */}
      <ArchitecturePipeline />

      <div className="divider mx-auto max-w-4xl" />

      {/* Agent Execution Visualization */}
      <AgentExecution />

      <div className="divider mx-auto max-w-4xl" />

      {/* AI Workspace Preview */}
      <section className="relative py-20 sm:py-28">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-12 text-center">
            <p className="section-eyebrow mb-4">AI Operations</p>
            <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
              AI Operations Workspace
            </h2>
            <p className="mx-auto mt-4 max-w-lg text-[14px] text-text-secondary">
              A unified AI workspace with reasoning, evidence, tool execution, and knowledge search - all from a single interface.
            </p>
          </div>
          <AIWorkspacePreview />
        </div>
      </section>

      <div className="divider mx-auto max-w-4xl" />

      {/* Knowledge Pipeline Visualization */}
      <KnowledgePipeline />

      <div className="divider mx-auto max-w-4xl" />

      {/* Integrations */}
      <IntegrationGrid />

      <div className="divider mx-auto max-w-4xl" />

      {/* Product Tabs */}
      <ProductTabs />

      <div className="divider mx-auto max-w-4xl" />

      {/* Security */}
      <SecurityGrid />

      {/* CTA */}
      <section className="relative py-20 sm:py-28">
        <div className="mx-auto max-w-6xl px-6">
          <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-8 text-center sm:p-12">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.03] via-transparent to-chart-2/[0.03]" />
            <div className="absolute inset-0 bg-grid opacity-20" />
            <div className="relative">
              <h2 className="mb-4 text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
                Ready to transform your infrastructure?
              </h2>
              <p className="mx-auto mb-8 max-w-lg text-[14px] text-text-secondary">
                Join the next generation of infrastructure management. One platform, AI-native, fully autonomous.
              </p>
              <button
                onClick={handleDemoLogin}
                disabled={demoLoading}
                className="group inline-flex h-12 items-center gap-2.5 rounded-xl bg-primary px-8 text-[13px] font-semibold text-white shadow-sm shadow-primary/20 transition-all hover:shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5 disabled:opacity-50"
              >
                {demoLoading ? <Spinner className="size-4" /> : <Sparkles className="size-4 transition-transform group-hover:scale-110" />}
                {demoLoading ? "Signing in..." : "Launch Demo Workspace"}
                {!demoLoading && <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-12">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <div className="flex items-center gap-3">
              <div className="grid size-7 place-items-center rounded-md bg-gradient-to-br from-primary to-primary/80">
                <Shield className="size-4 text-white" strokeWidth={2.5} />
              </div>
              <span className="text-[13px] font-bold text-text-primary">AegisNex</span>
            </div>
            <div className="flex items-center gap-6 text-[11px] text-text-tertiary">
              <span>AI-Native Infrastructure Intelligence</span>
              <span className="hidden sm:inline">|</span>
              <span>Open Source Platform</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
