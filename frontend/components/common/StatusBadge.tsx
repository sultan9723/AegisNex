import { Badge } from "@/components/ui/badge";

export type StatusState = "healthy" | "ok" | "success" | "warning" | "medium" | "info" | "danger" | "critical" | "high" | "error" | "low";

const statusVariantMap: Record<string, "success-subtle" | "warning-subtle" | "danger-subtle" | "info-subtle" | "secondary"> = {
  healthy: "success-subtle",
  ok: "success-subtle",
  success: "success-subtle",
  running: "success-subtle",
  active: "success-subtle",
  resolved: "success-subtle",
  passed: "success-subtle",
  up: "success-subtle",
  warning: "warning-subtle",
  medium: "warning-subtle",
  degraded: "warning-subtle",
  pending: "warning-subtle",
  unknown: "secondary",
  stopped: "secondary",
  dormant: "secondary",
  danger: "danger-subtle",
  critical: "danger-subtle",
  high: "danger-subtle",
  error: "danger-subtle",
  down: "danger-subtle",
  failed: "danger-subtle",
  unhealthy: "danger-subtle",
  info: "info-subtle",
  low: "info-subtle",
};

export function StatusBadge({ status, label, pulse }: { status: StatusState | string; label?: string; pulse?: boolean }) {
  const variant = statusVariantMap[status.toLowerCase()] ?? "secondary";
  return <Badge variant={variant} dot pulse={pulse}>{label ?? status}</Badge>;
}
