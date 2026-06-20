"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { SourceCard } from "@/components/features/sources/SourceCard";
import { Callout } from "@/components/ui/Callout";
import { Button } from "@/components/ui/Button";
import { generateReport } from "@/app/(app)/project/[id]/report/actions";
import type { Project, Subtopic, Source } from "@/lib/data/types";

const SOURCE_CAP = 25;

interface SourcesTabProps {
  project: Project;
  subtopics: Subtopic[];
  sources: Source[];
}

export function SourcesTab({ project, subtopics, sources }: SourcesTabProps) {
  const router = useRouter();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

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

  function toggleSource(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < SOURCE_CAP) {
        next.add(id);
      }
      return next;
    });
  }

  const selectableCount = Math.min(sources.length, SOURCE_CAP);
  const allSelected = selectableCount > 0 && selectedIds.size >= selectableCount;

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      if (prev.size >= selectableCount) return new Set();
      return new Set(sources.slice(0, SOURCE_CAP).map((s) => s.id));
    });
  }

  function handleGenerate(mode: "curated" | "auto") {
    setError(null);
    startTransition(async () => {
      const result = await generateReport(project.id, {
        mode,
        sourceIds: mode === "curated" ? [...selectedIds] : [],
        instructions: instructions.trim() || undefined,
      });
      if (result?.error) {
        setError(result.error);
      } else {
        router.push(`/project/${project.id}/report`);
      }
    });
  }

  return (
    <div className="py-10">
      <PageContainer>
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <h2 className="text-display-sm text-ink">Stored sources</h2>
          <div className="flex items-baseline gap-3">
            <span className="text-body-sm text-muted">
              {selectedIds.size}/{SOURCE_CAP} selected
            </span>
            <Button
              variant="text"
              size="sm"
              onClick={toggleSelectAll}
              disabled={isPending}
              className="px-0 h-auto shrink-0"
            >
              {allSelected ? "Deselect all" : "Select all"}
            </Button>
          </div>
        </div>
        <p className="text-body-md text-muted mb-8">
          {sources.length} source{sources.length !== 1 ? "s" : ""} stored across{" "}
          {subtopics.length} subtopics
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
                    <SourceCard
                      key={src.id}
                      source={src}
                      selected={selectedIds.has(src.id)}
                      onToggle={toggleSource}
                      disabled={!selectedIds.has(src.id) && selectedIds.size >= SOURCE_CAP}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>

        {/* Inline control panel after the last subtopic section */}
        <div className="mt-12 pt-8 border-t border-hairline">
          <div className="max-w-lg">
            <label className="text-body-sm text-muted block mb-1">
              Instructions (optional)
            </label>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              disabled={isPending}
              placeholder="Tone, audience, focus area…"
              rows={3}
              className="w-full rounded-md border border-hairline bg-canvas px-3 py-2 text-body-sm text-ink placeholder:text-muted-soft resize-none focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50"
            />
            {error && (
              <p className="mt-2 text-body-sm text-error">{error}</p>
            )}
            <div className="flex gap-3 mt-4">
              <Button
                variant="primary"
                onClick={() => handleGenerate("curated")}
                disabled={isPending || selectedIds.size === 0}
              >
                {isPending ? "Generating…" : "Generate report"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleGenerate("auto")}
                disabled={isPending}
              >
                Auto-draft
              </Button>
            </div>
            <p className="text-caption text-muted mt-3">PDF export coming in a later phase.</p>
          </div>
        </div>
      </PageContainer>
    </div>
  );
}
