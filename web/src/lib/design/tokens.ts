import { ProjectStatus } from "@/lib/data/types";

export type StatusMeta = {
  label: string;
  toneClass: string;
  dotClass: string;
};

export const STATUS_META: Record<ProjectStatus, StatusMeta> = {
  draft: {
    label: "Draft",
    toneClass: "bg-hairline text-muted",
    dotClass: "bg-muted",
  },
  planning: {
    label: "Planning",
    toneClass: "bg-warning/15 text-warning",
    dotClass: "bg-warning",
  },
  researching: {
    label: "Researching",
    toneClass: "bg-accent-teal/15 text-accent-teal",
    dotClass: "bg-accent-teal",
  },
  complete: {
    label: "Complete",
    toneClass: "bg-success/15 text-success",
    dotClass: "bg-success",
  },
  cancelled: {
    label: "Cancelled",
    toneClass: "bg-hairline text-muted",
    dotClass: "bg-muted-soft",
  },
};

export const SCORE_THRESHOLD = {
  success: 4,
  warning: 3,
};

export function scoreClass(score: number): string {
  if (score >= SCORE_THRESHOLD.success) return "text-success";
  if (score >= SCORE_THRESHOLD.warning) return "text-warning";
  return "text-error";
}

export function scoreBarClass(score: number): string {
  if (score >= SCORE_THRESHOLD.success) return "bg-success";
  if (score >= SCORE_THRESHOLD.warning) return "bg-warning";
  return "bg-error";
}
