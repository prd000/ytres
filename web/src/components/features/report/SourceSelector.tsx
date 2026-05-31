import type { Source } from "@/lib/data/types";
import { cn } from "@/lib/utils";

interface SourceSelectorProps {
  sources: Source[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  cap: number;
}

export function SourceSelector({ sources, selectedIds, onToggle, cap }: SourceSelectorProps) {
  const atCap = selectedIds.size >= cap;

  return (
    <div className="flex flex-col gap-2 max-h-[400px] overflow-y-auto pr-1">
      {sources.map((src) => {
        const selected = selectedIds.has(src.id);
        const disabled = atCap && !selected;
        return (
          <label
            key={src.id}
            className={cn(
              "flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors",
              selected
                ? "border-primary bg-primary/5"
                : "border-hairline hover:border-hairline-soft hover:bg-surface-soft",
              disabled && "opacity-40 cursor-not-allowed"
            )}
          >
            <input
              type="checkbox"
              checked={selected}
              disabled={disabled}
              onChange={() => onToggle(src.id)}
              className="mt-0.5 accent-primary shrink-0"
            />
            <span className="min-w-0">
              <span className="block text-body-sm text-ink font-medium line-clamp-2">{src.title}</span>
              <span className="block text-caption text-muted mt-0.5 line-clamp-2">{src.keyTakeaway}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
