import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusBadge, type StatusState } from "@/components/common/StatusBadge";

export function MetricCard({
  label,
  value,
  detail,
  status = "healthy",
  icon: Icon,
}: {
  label: string;
  value: string;
  detail?: string;
  status?: StatusState;
  icon: LucideIcon;
}) {
  return (
    <div className="rounded-lg border border-[#1F2937] bg-[#111827] p-4 shadow-sm transition hover:border-[#00E5FF]/40">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
          <Icon className="size-4 text-[#00E5FF]" aria-hidden="true" />
          {label}
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="mt-3 flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold leading-none text-white">{value}</div>
        {detail && (
          <div
            className={cn(
              "truncate text-xs",
              status === "danger" || status === "critical"
                ? "text-[#EF4444]"
                : status === "warning"
                  ? "text-[#F59E0B]"
                  : "text-slate-500",
            )}
          >
            {detail}
          </div>
        )}
      </div>
    </div>
  );
}
