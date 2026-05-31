"use client";

import { useState } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Textarea } from "@/components/ui/Input";
import { Callout } from "@/components/ui/Callout";
import type { Project, Subtopic } from "@/lib/data/types";

const TIER_LABELS = {
  academic: "Academic",
  government: "Government",
  news: "News",
  industry: "Industry",
};

interface PlanTabProps {
  project: Project;
  subtopics: Subtopic[];
}

export function PlanTab({ project, subtopics }: PlanTabProps) {
  const [feedback, setFeedback] = useState("");
  const [approved, setApproved] = useState(project.status === "researching" || project.status === "complete");

  const canApprove = project.status === "planning" || project.status === "draft";

  return (
    <div className="py-10">
      <PageContainer>
        {approved && (
          <Callout variant="info" title="Plan approved" className="mb-8">
            This research plan has been approved. Agents are researching each subtopic.
          </Callout>
        )}

        {/* Global source tier settings */}
        <section className="mb-8">
          <h2 className="text-title-md text-ink mb-4">Source preferences</h2>
          <div className="bg-surface-card rounded-lg p-5 border border-hairline-soft">
            <div className="flex flex-wrap gap-2 mb-4">
              {(["academic", "government", "news", "industry"] as const).map((tier) => (
                <span
                  key={tier}
                  className={`text-caption px-3 py-1 rounded-pill border transition-colors ${
                    project.sourceTierSettings[tier]
                      ? "bg-primary text-on-primary border-primary"
                      : "bg-canvas text-muted border-hairline"
                  }`}
                >
                  {TIER_LABELS[tier]}
                </span>
              ))}
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
            <span className="ml-2 text-muted text-body-sm">({subtopics.length})</span>
          </h2>
          <div className="flex flex-col gap-3">
            {subtopics.map((sub) => (
              <Card key={sub.id} surface="canvas-bordered" padding="default">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-title-sm text-ink mb-1">{sub.title}</p>
                    <p className="text-body-sm text-muted mb-3">{sub.informationObjective}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {sub.sourceTierPreferences.map((tier) => (
                        <Badge key={tier} variant="pill">
                          {TIER_LABELS[tier]}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>

        {/* Plan actions */}
        {canApprove && (
          <div className="bg-surface-card rounded-lg p-6 border border-hairline-soft">
            <h2 className="text-title-sm text-ink mb-4">Approve or refine this plan</h2>
            <Textarea
              placeholder="Optional feedback for regeneration — e.g., 'Focus more on cost implications' or 'Add a subtopic on policy barriers'"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              className="mb-4"
              rows={3}
            />
            <div className="flex items-center gap-3">
              <button
                onClick={() => setApproved(true)}
                className="h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors"
              >
                Approve plan
              </button>
              {feedback && (
                <button
                  onClick={() => setFeedback("")}
                  className="h-10 px-5 text-button text-ink border border-hairline rounded-md hover:bg-surface-soft transition-colors"
                >
                  Regenerate with feedback
                </button>
              )}
            </div>
          </div>
        )}
      </PageContainer>
    </div>
  );
}
