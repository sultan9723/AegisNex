import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StatusState } from "@/components/common/StatusBadge";
import { StatusBadge } from "@/components/common/StatusBadge";

export function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  status,
  trend,
  progress,
  className,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail?: string;
  status?: StatusState;
  trend?: "up" | "down" | "neutral";
  progress?: number;
  className?: string;
}) {
  return (
    <div className={cn(
      "rounded-xl border border-border/70 bg-surface-elevated/80 p-5 shadow-md",
      "transition-all duration-300 hover:border-border hover:shadow-lg hover:bg-surface-elevated/95",
      className
    )}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/15">
            <Icon className="size-4" />
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-tertiary">{label}</p>
            <p className="mt-0.5 text-2xl font-semibold tracking-tight text-text-primary">{value}</p>
          </div>
        </div>
        {status && <StatusBadge status={status} />}
      </div>
      {(detail || trend) && (
        <div className="mt-3 flex items-center gap-2 border-t border-border/40 pt-3">
          {trend && (
            <span className={cn(
              "text-[11px] font-medium",
              trend === "up" && "text-success",
              trend === "down" && "text-danger",
              trend === "neutral" && "text-text-tertiary",
            )}>
              {trend === "up" && "↑"} {trend === "down" && "↓"} {trend === "neutral" && "→"}
            </span>
          )}
          {detail && <span className="text-xs text-text-secondary">{detail}</span>}
        </div>
      )}
      {typeof progress === "number" && (
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-chart-2 transition-all duration-700 ease-out-expo"
            style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
          />
        </div>
      )}
    </div>
  );
}
