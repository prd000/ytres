"use client";

import { useState, useTransition, useEffect, useRef } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ReportPreview } from "@/components/features/report/ReportPreview";
import { SourceSelector } from "@/components/features/report/SourceSelector";
import { Button } from "@/components/ui/Button";
import { generateReport } from "@/app/(app)/project/[id]/report/actions";
import type { Project, Source, Report } from "@/lib/data/types";

const SOURCE_CAP = 25;

interface ReportTabProps {
  project: Project;
  sources: Source[];
  existingReport: Report | null;
}

export function ReportTab({ project, sources, existingReport }: ReportTabProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(existingReport?.sourceRefs ?? [])
  );
  const [instructions, setInstructions] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Clear generating state when a new report arrives via Realtime → router.refresh()
  const prevReportId = useRef<string | undefined>(existingReport?.id);
  useEffect(() => {
    if (existingReport?.id && existingReport.id !== prevReportId.current) {
      prevReportId.current = existingReport.id;
      setIsGenerating(false);
      setError(null);
    }
  }, [existingReport?.id]);

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

  // "Select all" caps at SOURCE_CAP — when there are more sources than the cap,
  // it selects the first SOURCE_CAP. "All selected" means every selectable slot
  // is filled (either all sources or the cap, whichever is smaller).
  const selectableCount = Math.min(sources.length, SOURCE_CAP);
  const allSelected = selectableCount > 0 && selectedIds.size >= selectableCount;

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      if (prev.size >= selectableCount) return new Set();
      return new Set(sources.slice(0, SOURCE_CAP).map((s) => s.id));
    });
  }

  function handleDownload() {
    if (!existingReport) return;
    const blob = new Blob([existingReport.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research-report.md";
    a.click();
    URL.revokeObjectURL(url);
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
        setIsGenerating(true);
      }
    });
  }

  const busy = isPending || isGenerating;

  return (
    <div className="py-10">
      <PageContainer>
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-8">
          {/* Left: source selection + controls */}
          <aside>
            <div className="lg:sticky lg:top-24">
              <div className="flex items-baseline justify-between gap-3 mb-1">
                <h2 className="text-title-md text-ink">Select sources</h2>
                {sources.length > 0 && (
                  <Button
                    variant="text"
                    size="sm"
                    onClick={toggleSelectAll}
                    disabled={busy}
                    className="px-0 h-auto shrink-0"
                  >
                    {allSelected ? "Deselect all" : "Select all"}
                  </Button>
                )}
              </div>
              <p className="text-body-sm text-muted mb-4">
                {selectedIds.size}/{SOURCE_CAP} selected
              </p>

              {sources.length > 0 && (
                <SourceSelector
                  sources={sources}
                  selectedIds={selectedIds}
                  onToggle={toggleSource}
                  cap={SOURCE_CAP}
                />
              )}

              {/* Optional instructions */}
              <div className="mt-5">
                <label className="text-body-sm text-muted block mb-1">
                  Instructions (optional)
                </label>
                <textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  disabled={busy}
                  placeholder="Tone, audience, focus area…"
                  rows={3}
                  className="w-full rounded-md border border-hairline bg-canvas px-3 py-2 text-body-sm text-ink placeholder:text-muted-soft resize-none focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50"
                />
              </div>

              {error && (
                <p className="mt-3 text-body-sm text-error">{error}</p>
              )}

              <div className="flex flex-col gap-2 mt-4">
                <Button
                  variant="primary"
                  onClick={() => handleGenerate("curated")}
                  disabled={busy || selectedIds.size === 0}
                  className="w-full"
                >
                  {busy ? "Generating…" : "Generate report"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleGenerate("auto")}
                  disabled={busy || sources.length === 0}
                  className="w-full"
                >
                  Auto-draft
                </Button>
                {existingReport && (
                  <Button
                    variant="secondary"
                    onClick={handleDownload}
                    disabled={busy}
                    className="w-full"
                  >
                    Download .md
                  </Button>
                )}
              </div>

              <p className="text-caption text-muted mt-3">
                PDF export coming in a later phase.
              </p>
            </div>
          </aside>

          {/* Right: preview */}
          <div>
            {isGenerating && !existingReport ? (
              <div className="flex flex-col items-center justify-center py-20 text-center text-muted border border-dashed border-hairline rounded-lg">
                <p className="text-title-sm text-ink mb-2">Generating report…</p>
                <p className="text-body-sm">
                  The AI is synthesizing your sources. This usually takes under a minute.
                </p>
              </div>
            ) : existingReport ? (
              <>
                {isGenerating && (
                  <p className="text-body-sm text-muted mb-4">
                    Generating a new version…
                  </p>
                )}
                <ReportPreview markdown={existingReport.markdown} />
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center text-muted border border-dashed border-hairline rounded-lg">
                <p className="text-title-sm text-ink mb-2">No report yet</p>
                <p className="text-body-sm">
                  Select sources and click <strong>Generate report</strong>, or use{" "}
                  <strong>Auto-draft</strong> to let the AI choose.
                </p>
              </div>
            )}
          </div>
        </div>
      </PageContainer>
    </div>
  );
}
