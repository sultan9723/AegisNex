import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";

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
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-start justify-between rounded-xl border border-border/60 bg-surface-elevated/60 px-5 py-4 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
            <Icon className="size-4" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-text-primary">{title}</h1>
            <p className="mt-0.5 text-sm text-text-secondary">{description}</p>
          </div>
        </div>
        <Badge variant="success-subtle" dot pulse>live</Badge>
      </div>
      {children}
    </div>
  );
}
