import { cn } from "@/lib/utils";
import { STATUS_META } from "@/lib/design/tokens";
import type { ProjectStatus } from "@/lib/data/types";

interface StatusPillProps {
  status: ProjectStatus;
  className?: string;
}

export function StatusPill({ status, className }: StatusPillProps) {
  const meta = STATUS_META[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-caption rounded-pill px-3 py-1",
        meta.toneClass,
        className
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", meta.dotClass)} />
      {meta.label}
    </span>
  );
}
