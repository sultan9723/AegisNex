import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusState = "healthy" | "success" | "warning" | "danger" | "critical" | "unknown";

const styles: Record<StatusState, string> = {
  healthy: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  success: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  warning: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  danger: "border-rose-500/25 bg-rose-500/10 text-rose-300",
  critical: "border-rose-500/25 bg-rose-500/10 text-rose-300",
  unknown: "border-slate-500/30 bg-slate-500/10 text-slate-300",
};

const icons = {
  healthy: CheckCircle2,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  critical: XCircle,
  unknown: HelpCircle,
};

export function StatusBadge({ status, label }: { status: StatusState; label?: string }) {
  const Icon = icons[status] ?? HelpCircle;

  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full border px-2 text-[11px] font-medium capitalize tracking-normal",
        styles[status],
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
      {label ?? status}
    </span>
  );
}
