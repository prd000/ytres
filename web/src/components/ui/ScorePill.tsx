import { cn } from "@/lib/utils";
import { scoreClass } from "@/lib/design/tokens";

interface ScorePillProps {
  label: string;
  score: number;
  className?: string;
}

export function ScorePill({ label, score, className }: ScorePillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-caption bg-surface-card rounded-md px-2 py-1",
        className
      )}
    >
      <span className="text-muted">{label}</span>
      <span className={cn("font-medium", scoreClass(score))}>{score}/5</span>
    </span>
  );
}

interface ScoreBarProps {
  score: number;
  className?: string;
}

export function ScoreBar({ score, className }: ScoreBarProps) {
  const pct = (score / 5) * 100;
  const colorClass =
    score >= 4 ? "bg-success" : score >= 3 ? "bg-warning" : "bg-error";

  return (
    <div className={cn("h-1 w-full bg-hairline rounded-full overflow-hidden", className)}>
      <div
        className={cn("h-full rounded-full transition-all", colorClass)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
