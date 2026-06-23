import { Skeleton } from "@/components/common/Skeleton";

export function LoadingState({ label = "Loading live telemetry" }: { label?: string }) {
  return (
    <div className="space-y-4 rounded-xl border border-border bg-card/90 p-5 shadow-sm">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <Skeleton className="size-4 rounded-full" />
        {label}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
      <Skeleton className="h-80 w-full rounded-lg" />
    </div>
  );
}
