export function HealthScoreCard({ score }: { score: number }) {
  const normalized = Math.max(0, Math.min(100, score));
  const color = normalized >= 80 ? "#22C55E" : normalized >= 60 ? "#F59E0B" : "#EF4444";

  return (
    <div className="rounded-lg border border-[#1F2937] bg-[#111827] p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">Health Score</p>
          <p className="mt-2 text-2xl font-semibold text-white">{normalized}</p>
        </div>
        <div className="relative size-14">
          <svg className="-rotate-90" viewBox="0 0 56 56">
            <circle cx="28" cy="28" r="22" fill="none" stroke="#1F2937" strokeWidth="6" />
            <circle
              cx="28"
              cy="28"
              r="22"
              fill="none"
              stroke={color}
              strokeLinecap="round"
              strokeWidth="6"
              strokeDasharray={138}
              strokeDashoffset={138 - (normalized / 100) * 138}
            />
          </svg>
        </div>
      </div>
    </div>
  );
}
