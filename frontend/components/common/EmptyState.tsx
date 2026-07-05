import { AlertCircle, FileSearch, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  className,
}: {
  icon?: React.ElementType;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  className?: string;
}) {
  const IconComponent = Icon ?? FileSearch;
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-border/50 bg-surface-elevated/30 px-6 py-16 text-center", className)}>
      <div className="mb-4 grid size-14 place-items-center rounded-xl bg-surface-elevated/80 ring-1 ring-border/50">
        <IconComponent className="size-6 text-text-tertiary" />
      </div>
      <h3 className="mb-1 text-base font-semibold text-text-primary">{title}</h3>
      <p className="mb-6 max-w-sm text-sm text-text-secondary">{description}</p>
      <div className="flex items-center gap-3">
        {actionLabel && onAction && (
          <Button variant="default" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        )}
        {secondaryActionLabel && onSecondaryAction && (
          <Button variant="outline" size="sm" onClick={onSecondaryAction}>
            {secondaryActionLabel}
          </Button>
        )}
      </div>
    </div>
  );
}

export function EmptyStateNoData({ title, description, className }: { title?: string; description?: string; className?: string }) {
  return (
    <EmptyState
      icon={FileSearch}
      title={title ?? "No data found"}
      description={description ?? "There are no records to display for this section."}
      className={className}
    />
  );
}

export function EmptyStateError({ message, onRetry, className }: { message?: string; onRetry?: () => void; className?: string }) {
  return (
    <EmptyState
      icon={AlertCircle}
      title="Something went wrong"
      description={message ?? "An unexpected error occurred. Please try again."}
      actionLabel={onRetry ? "Retry" : undefined}
      onAction={onRetry}
      className={className}
    />
  );
}

export function EmptyStateSearch({ onClear, className }: { onClear?: () => void; className?: string }) {
  return (
    <EmptyState
      icon={SearchX}
      title="No results found"
      description="Try adjusting your search query or filters."
      actionLabel={onClear ? "Clear filters" : undefined}
      onAction={onClear}
      className={className}
    />
  );
}
