import { Badge } from "@/components/ui/Badge";
import { ScorePill } from "@/components/ui/ScorePill";
import { TextLink } from "@/components/ui/TextLink";
import { cn } from "@/lib/utils";
import type { Source } from "@/lib/data/types";

const TIER_LABELS: Record<string, string> = {
  academic: "Academic",
  government: "Government",
  news: "News",
  industry: "Industry",
  social_media: "Social media",
};

interface SourceCardProps {
  source: Source;
  selected?: boolean;
  onToggle?: (id: string) => void;
  disabled?: boolean;
}

export function SourceCard({ source, selected = false, onToggle, disabled = false }: SourceCardProps) {
  const selectable = !!onToggle;

  return (
    <div
      className={cn(
        "bg-canvas rounded-lg p-5 border transition-colors",
        selectable && selected ? "border-primary bg-primary/5" : "border-hairline",
        selectable && disabled && "opacity-40"
      )}
    >
      <div className="flex items-start gap-3 mb-3">
        {selectable && (
          <input
            type="checkbox"
            checked={selected}
            disabled={disabled}
            onChange={() => onToggle(source.id)}
            className="mt-1 accent-primary shrink-0"
          />
        )}
        <div className="flex items-start justify-between gap-4 flex-1">
          <TextLink href={source.url} external className="text-title-sm">
            {source.title}
          </TextLink>
          <Badge variant="pill" className="shrink-0">
            {TIER_LABELS[source.tier]}
          </Badge>
        </div>
      </div>

      <p className="text-body-sm text-body mb-4">{source.keyTakeaway}</p>

      <div className="flex flex-wrap gap-2">
        <ScorePill label="Relevance" score={source.scores.relevance} />
        <ScorePill label="Credibility" score={source.scores.credibility} />
        <ScorePill label="Uniqueness" score={source.scores.uniqueness} />
        <ScorePill label="Actionability" score={source.scores.actionability} />
      </div>
    </div>
  );
}
