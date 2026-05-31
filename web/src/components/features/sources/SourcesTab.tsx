import { PageContainer } from "@/components/layout/PageContainer";
import { SourceCard } from "@/components/features/sources/SourceCard";
import { Callout } from "@/components/ui/Callout";
import type { Project, Subtopic, Source } from "@/lib/data/types";

interface SourcesTabProps {
  project: Project;
  subtopics: Subtopic[];
  sources: Source[];
}

export function SourcesTab({ project, subtopics, sources }: SourcesTabProps) {
  if (sources.length === 0) {
    return (
      <div className="py-10">
        <PageContainer>
          <Callout variant="info" title="No sources yet">
            Sources will appear here once research agents begin storing findings.
          </Callout>
        </PageContainer>
      </div>
    );
  }

  return (
    <div className="py-10">
      <PageContainer>
        <h2 className="text-display-sm text-ink mb-2">Stored sources</h2>
        <p className="text-body-md text-muted mb-8">
          {sources.length} source{sources.length !== 1 ? "s" : ""} stored across {subtopics.length} subtopics
        </p>

        <div className="flex flex-col gap-10">
          {subtopics.map((sub) => {
            const subSources = sources.filter((s) => s.subtopicIds.includes(sub.id));
            if (subSources.length === 0) return null;
            return (
              <section key={sub.id}>
                <h3 className="text-title-md text-ink mb-1">{sub.title}</h3>
                <p className="text-body-sm text-muted mb-4">
                  {subSources.length} source{subSources.length !== 1 ? "s" : ""}
                </p>
                <div className="flex flex-col gap-4">
                  {subSources.map((src) => (
                    <SourceCard key={src.id} source={src} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </PageContainer>
    </div>
  );
}
