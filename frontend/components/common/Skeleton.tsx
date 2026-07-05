import { cn } from "@/lib/utils"

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("skeleton-shimmer rounded-lg", className)}
      {...props}
    />
  )
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border/50 bg-surface-elevated/50 p-5", className)}>
      <Skeleton className="mb-3 h-4 w-24" />
      <Skeleton className="mb-2 h-8 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-xl border border-border/50 bg-surface-elevated/50 p-4">
      <div className="mb-3 flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 border-t border-border/30 py-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonChart({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border/50 bg-surface-elevated/50 p-5", className)}>
      <Skeleton className="mb-4 h-4 w-32" />
      <div className="flex h-40 items-end gap-2">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton
            key={i}
            className="flex-1"
            style={{ height: `${Math.max(15, Math.random() * 100)}%` }}
          />
        ))}
      </div>
    </div>
  )
}

export function SkeletonMetricCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border/50 bg-surface-elevated/50 p-5", className)}>
      <div className="mb-3 flex items-center gap-3">
        <Skeleton className="size-9 rounded-lg" />
        <div className="flex-1">
          <Skeleton className="mb-1.5 h-3 w-16" />
          <Skeleton className="h-5 w-12" />
        </div>
      </div>
      <Skeleton className="h-2.5 w-full" />
    </div>
  )
}

export function SkeletonList({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border/30 bg-surface-elevated/30 p-3">
          <Skeleton className="size-2 rounded-full" />
          <div className="flex-1">
            <Skeleton className="mb-1 h-3 w-32" />
            <Skeleton className="h-2.5 w-48" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonDashboard() {
  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <Skeleton className="mb-2 h-4 w-40" />
          <Skeleton className="mb-2 h-10 w-96" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="flex gap-8">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="mb-1 h-3 w-16" />
              <Skeleton className="h-8 w-12" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-5"><SkeletonCard className="h-64" /></div>
        <div className="lg:col-span-7"><SkeletonCard className="h-64" /></div>
      </div>
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-8"><SkeletonCard className="h-48" /></div>
        <div className="lg:col-span-4"><SkeletonCard className="h-48" /></div>
      </div>
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-6"><SkeletonChart /></div>
        <div className="lg:col-span-6"><SkeletonChart /></div>
        <div className="lg:col-span-6"><SkeletonChart /></div>
        <div className="lg:col-span-6"><SkeletonChart /></div>
      </div>
    </div>
  )
}
