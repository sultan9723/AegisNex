import { cn } from "@/lib/utils";

export function LoadingState({
  message,
  size = "md",
  className,
}: {
  message?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes = { sm: "size-6", md: "size-10", lg: "size-14" };
  return (
    <div className={cn("flex flex-col items-center justify-center py-24", className)}>
      <div className="relative">
        <div className={cn(sizes[size], "animate-spin rounded-full border-2 border-border border-t-primary")} />
        <div className={cn(
          sizes[size],
          "absolute inset-0 animate-ping-slow rounded-full border-2 border-primary/20"
        )} />
      </div>
      {message && (
        <p className="mt-4 text-sm text-text-secondary animate-fade-in">{message}</p>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("animate-spin text-current", className)}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

export function ProgressBar({ value, className }: { value: number; className?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated", className)}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-primary via-chart-2 to-chart-3 transition-all duration-500 ease-out-expo"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
