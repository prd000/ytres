import { Badge } from "@/components/ui/Badge";
import { ScorePill } from "@/components/ui/ScorePill";
import { TextLink } from "@/components/ui/TextLink";
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
}

export function SourceCard({ source }: SourceCardProps) {
  return (
    <div className="bg-canvas rounded-lg p-5 border border-hairline">
      <div className="flex items-start justify-between gap-4 mb-3">
        <TextLink href={source.url} external className="text-title-sm">
          {source.title}
        </TextLink>
        <Badge variant="pill" className="shrink-0">
          {TIER_LABELS[source.tier]}
        </Badge>
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
