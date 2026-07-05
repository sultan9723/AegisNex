"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export type PipelineStep = {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  message?: string;
};

export function ProgressPipeline({
  steps: initialSteps,
  onComplete,
  onRetry,
  error,
  className,
}: {
  steps: PipelineStep[];
  onComplete?: () => void;
  onRetry?: () => void;
  error?: string | null;
  className?: string;
}) {
  const [steps, setSteps] = useState(initialSteps);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => { setSteps(initialSteps); }, [initialSteps]);

  const completed = steps.every((s) => s.status === "completed" || s.status === "failed");

  if (dismissed) return null;

  return (
    <div className={cn("rounded-xl border border-border/70 bg-surface-elevated/80 p-4 shadow-sm", className)}>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-3">
            {step.status === "running" && <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />}
            {step.status === "completed" && <CheckCircle2 className="size-3.5 shrink-0 text-success" />}
            {step.status === "failed" && <XCircle className="size-3.5 shrink-0 text-danger" />}
            {step.status === "pending" && <Clock className="size-3.5 shrink-0 text-text-tertiary" />}
            <div className="min-w-0 flex-1">
              <span className={cn(
                "text-xs",
                step.status === "completed" ? "text-text-primary" : step.status === "failed" ? "text-danger" : step.status === "running" ? "text-primary" : "text-text-tertiary"
              )}>
                {step.name}
              </span>
              {step.message && <p className="text-[10px] text-text-tertiary">{step.message}</p>}
            </div>
          </div>
        ))}
      </div>

      {completed && (
        <div className="mt-3 flex items-center gap-2">
          {steps.some((s) => s.status === "failed") && onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="text-xs font-medium text-primary hover:text-primary-hover transition-colors"
            >
              Retry
            </button>
          )}
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <p className="mt-2 text-xs text-danger">{error}</p>
      )}
    </div>
  );
}

export function usePipeline() {
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback((initialSteps: PipelineStep[]) => {
    setSteps(initialSteps);
    setError(null);
  }, []);

  const updateStep = useCallback((index: number, status: PipelineStep["status"], message?: string) => {
    setSteps((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], status, message: message ?? next[index].message };
      return next;
    });
  }, []);

  const fail = useCallback((msg: string) => {
    setError(msg);
    setSteps((prev) => prev.map((s) => s.status === "running" ? { ...s, status: "failed" } : s));
  }, []);

  return { steps, error, start, updateStep, fail };
}
