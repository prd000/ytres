import { PageContainer } from "@/components/layout/PageContainer";
import { Callout } from "@/components/ui/Callout";
import type { Project, Subtopic, WorkerActivity } from "@/lib/data/types";

const STATUS_LABELS = {
  queued: "Queued",
  running: "Running",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STATUS_DOT = {
  queued: "bg-muted",
  running: "bg-accent-teal animate-pulse",
  complete: "bg-success",
  failed: "bg-error",
  cancelled: "bg-muted-soft",
};

interface ResearchTabProps {
  project: Project;
  subtopics: Subtopic[];
  activity: WorkerActivity[];
}

export function ResearchTab({ project, subtopics, activity }: ResearchTabProps) {
  const activityMap = Object.fromEntries(activity.map((a) => [a.subtopicId, a]));

  const hasAnyActivity = activity.length > 0;
  const isIdle = project.status === "planning" || project.status === "draft";

  return (
    <div className="py-10">
      <PageContainer>
        <h2 className="text-display-sm text-ink mb-2">Research progress</h2>
        <p className="text-body-md text-muted mb-8">
          Each subtopic is researched in parallel by an independent AI agent.
        </p>

        {isIdle && (
          <Callout variant="info" title="Research not started" className="mb-8">
            Approve the research plan to start agents.
          </Callout>
        )}

        {!hasAnyActivity && !isIdle && (
          <Callout variant="warning" title="Starting up" className="mb-8">
            Agents are being initialized. Progress will appear here shortly.
          </Callout>
        )}

        <div className="flex flex-col gap-4">
          {subtopics.map((sub) => {
            const a = activityMap[sub.id];
            return (
              <div key={sub.id} className="bg-surface-card rounded-lg p-5 border border-hairline-soft">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <p className="text-title-sm text-ink">{sub.title}</p>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`w-2 h-2 rounded-full ${a ? STATUS_DOT[a.status] : STATUS_DOT.queued}`} />
                    <span className="text-caption text-muted">
                      {a ? STATUS_LABELS[a.status] : "Queued"}
                    </span>
                  </div>
                </div>

                {a ? (
                  <div>
                    <p className="text-body-sm text-muted mb-2">{a.latestActivity}</p>
                    {a.sourcesStored > 0 && (
                      <p className="text-caption text-muted-soft">
                        {a.sourcesStored} source{a.sourcesStored !== 1 ? "s" : ""} stored
                      </p>
                    )}
                    {a.whyNothingReport && (
                      <Callout variant="warning" title="No sources found" className="mt-3">
                        {a.whyNothingReport}
                      </Callout>
                    )}
                  </div>
                ) : (
                  <p className="text-body-sm text-muted">Waiting for worker slot…</p>
                )}
              </div>
            );
          })}
        </div>
      </PageContainer>
    </div>
  );
}
