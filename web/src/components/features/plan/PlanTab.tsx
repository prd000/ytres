"use client";

import { useActionState } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Textarea } from "@/components/ui/Input";
import { Callout } from "@/components/ui/Callout";
import {
  approvePlan,
  regeneratePlan,
  type ApprovePlanState,
  type RegeneratePlanState,
} from "@/app/(app)/project/actions";
import type { Project, Subtopic } from "@/lib/data/types";

const TIER_LABELS: Record<string, string> = {
  academic: "Academic",
  government: "Government",
  news: "News",
  industry: "Industry",
  social_media: "Social media",
};

interface PlanTabProps {
  project: Project;
  subtopics: Subtopic[];
}

export function PlanTab({ project, subtopics }: PlanTabProps) {
  const boundApprove = approvePlan.bind(null, project.id);
  const boundRegenerate = regeneratePlan.bind(null, project.id);

  const [approveState, approveAction, isApproving] = useActionState<
    ApprovePlanState,
    FormData
  >(boundApprove, undefined);

  const [regenState, regenAction, isRegenerating] = useActionState<
    RegeneratePlanState,
    FormData
  >(boundRegenerate, undefined);

  const isPlanning = project.status === "planning";
  const isApproved =
    project.status === "researching" || project.status === "complete";
  const isDraft = project.status === "draft";

  return (
    <div className="py-10">
      <PageContainer>
        {isApproved && (
          <Callout variant="info" title="Plan approved" className="mb-8">
            This research plan has been approved. Agents are researching each
            subtopic.
          </Callout>
        )}

        {/* Global source tier settings */}
        <section className="mb-8">
          <h2 className="text-title-md text-ink mb-4">Source preferences</h2>
          <div className="bg-surface-card rounded-lg p-5 border border-hairline-soft">
            <div className="flex flex-wrap gap-2 mb-4">
              {(
                [
                  "academic",
                  "government",
                  "news",
                  "industry",
                  "social_media",
                ] as const
              ).map((tier) => {
                const enabled =
                  tier === "social_media"
                    ? project.sourceTierSettings.socialMedia
                    : project.sourceTierSettings[tier];
                return (
                  <span
                    key={tier}
                    className={`text-caption px-3 py-1 rounded-pill border transition-colors ${
                      enabled
                        ? "bg-primary text-on-primary border-primary"
                        : "bg-canvas text-muted border-hairline"
                    }`}
                  >
                    {TIER_LABELS[tier]}
                  </span>
                );
              })}
            </div>
            <p className="text-body-sm text-muted">
              {project.sourceTierSettings.recencyMonths
                ? `Sources from the last ${project.sourceTierSettings.recencyMonths} months`
                : "No recency filter — all dates included"}
            </p>
          </div>
        </section>

        {/* Subtopics */}
        <section className="mb-8">
          <h2 className="text-title-md text-ink mb-4">
            Research subtopics
            <span className="ml-2 text-muted text-body-sm">
              ({subtopics.length})
            </span>
          </h2>

          {isPlanning && subtopics.length === 0 ? (
            <div className="flex items-center gap-3 py-8 text-muted">
              <span className="inline-flex gap-1">
                <span className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
              <span className="text-body-md">
                Generating your research plan…
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {subtopics.map((sub) => (
                <Card key={sub.id} surface="canvas-bordered" padding="default">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-title-sm text-ink mb-1">{sub.title}</p>
                      <p className="text-body-sm text-muted mb-3">
                        {sub.informationObjective}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {sub.sourceTierPreferences.map((tier) => (
                          <Badge key={tier} variant="pill">
                            {TIER_LABELS[tier] ?? tier}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Plan actions — shown when planning with subtopics ready */}
        {isPlanning && subtopics.length > 0 && (
          <div className="bg-surface-card rounded-lg p-6 border border-hairline-soft">
            <h2 className="text-title-sm text-ink mb-4">
              Approve or refine this plan
            </h2>

            {(approveState?.error || regenState?.error) && (
              <Callout variant="coral" className="mb-4">
                {approveState?.error ?? regenState?.error}
              </Callout>
            )}

            {/*
              Two separate forms share one textarea via the HTML `form` attribute.
              This avoids invalid nested-form markup while keeping both actions
              wired to useActionState.
            */}
            <form id="approve-form" action={approveAction} />
            <form id="regen-form" action={regenAction}>
              <Textarea
                name="feedback"
                placeholder="Optional feedback for regeneration — e.g., 'Focus more on cost implications' or 'Add a subtopic on policy barriers'"
                className="mb-4"
                rows={3}
              />
            </form>

            <div className="flex items-center gap-3">
              <button
                form="approve-form"
                type="submit"
                disabled={isApproving || isRegenerating}
                className="h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:bg-primary-disabled disabled:text-muted disabled:cursor-not-allowed"
              >
                {isApproving ? "Approving…" : "Approve plan"}
              </button>

              <button
                form="regen-form"
                type="submit"
                disabled={isApproving || isRegenerating}
                className="h-10 px-5 text-button text-ink border border-hairline rounded-md hover:bg-surface-soft transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRegenerating ? "Regenerating…" : "Regenerate with feedback"}
              </button>
            </div>
          </div>
        )}

        {/* Legacy draft fallback */}
        {isDraft && (
          <Callout variant="info" title="Plan not yet started">
            This project was created before automatic planning. Submit a new
            project to trigger the plan generator.
          </Callout>
        )}
      </PageContainer>
    </div>
  );
}
