import type { LucideIcon } from "lucide-react";
import { StatusBadge } from "@/components/common/StatusBadge";

export function RouteScaffold({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card/90 px-4 py-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Icon className="size-4 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
          <StatusBadge status="healthy" label="live" />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  );
}
