import { cn } from "@/lib/utils";

export function HealthScoreCard({
  score,
  label,
  className,
}: {
  score: number;
  label?: string;
  className?: string;
}) {
  const normalized = Math.max(0, Math.min(100, score));
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (normalized / 100) * circumference;

  const color = normalized >= 80 ? "#34D399"
    : normalized >= 60 ? "#F59E0B"
    : "#FB7185";

  return (
    <div className={cn("flex items-center gap-4", className)}>
      <div className="relative size-24 shrink-0">
        <svg className="-rotate-90" viewBox="0 0 100 100" aria-hidden="true" width="96" height="96">
          <circle cx="50" cy="50" r="42" fill="none" stroke="hsl(var(--border) / 0.5)" strokeWidth="6" />
          <circle
            cx="50" cy="50" r="42"
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-1000 ease-out-expo"
            filter="url(#glow)"
          />
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-bold tracking-tight text-text-primary">{score}</span>
        </div>
      </div>
      {label && (
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-text-tertiary">Health Score</p>
          <p className="mt-0.5 text-sm font-medium" style={{ color }}>{label}</p>
        </div>
      )}
    </div>
  );
}
