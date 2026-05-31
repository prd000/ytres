"use client";

import { useState } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ReportPreview } from "@/components/features/report/ReportPreview";
import { SourceSelector } from "@/components/features/report/SourceSelector";
import { Callout } from "@/components/ui/Callout";
import type { Project, Source, Report } from "@/lib/data/types";

const SOURCE_CAP = 25;

interface ReportTabProps {
  project: Project;
  sources: Source[];
  existingReport: Report | null;
}

export function ReportTab({ project: _project, sources, existingReport }: ReportTabProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(existingReport?.sourceRefs ?? [])
  );
  const [autoDraft, setAutoDraft] = useState(!existingReport);
  const [report, setReport] = useState<Report | null>(existingReport);

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

  function handleGenerate() {
    const mockReport: Report = {
      id: "mock-gen",
      projectId: _project.id,
      markdown: `# Generated Report\n\nThis is a mock report generated from ${selectedIds.size} selected source${selectedIds.size !== 1 ? "s" : ""}.\n\nConnect to the coordinator agent in Phase 10 to generate real AI-synthesized reports with inline citations.\n`,
      sourceRefs: Array.from(selectedIds),
      generatedAt: new Date(),
    };
    setReport(mockReport);
  }

  function handleDownload() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research-report.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="py-10">
      <PageContainer>
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-8">
          {/* Left: source selection */}
          <aside>
            <div className="lg:sticky lg:top-24">
              <h2 className="text-title-md text-ink mb-1">Select sources</h2>
              <p className="text-body-sm text-muted mb-4">
                {selectedIds.size}/{SOURCE_CAP} selected
              </p>

              <label className="flex items-center gap-2 mb-4 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoDraft}
                  onChange={(e) => setAutoDraft(e.target.checked)}
                  className="accent-primary"
                />
                <span className="text-body-sm text-ink">Auto-draft (AI selects top sources)</span>
              </label>

              {!autoDraft && sources.length > 0 && (
                <SourceSelector
                  sources={sources}
                  selectedIds={selectedIds}
                  onToggle={toggleSource}
                  cap={SOURCE_CAP}
                />
              )}

              <div className="flex flex-col gap-2 mt-5">
                <button
                  onClick={handleGenerate}
                  disabled={!autoDraft && selectedIds.size === 0}
                  className="w-full h-10 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:bg-primary-disabled disabled:text-muted disabled:cursor-not-allowed"
                >
                  Generate report
                </button>
                {report && (
                  <button
                    onClick={handleDownload}
                    className="w-full h-10 text-button text-ink border border-hairline rounded-md hover:bg-surface-soft transition-colors"
                  >
                    Download .md
                  </button>
                )}
              </div>

              <Callout variant="warning" className="mt-4">
                PDF export coming in a later phase.
              </Callout>
            </div>
          </aside>

          {/* Right: preview */}
          <div>
            {report ? (
              <ReportPreview markdown={report.markdown} />
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center text-muted border border-dashed border-hairline rounded-lg">
                <p className="text-title-sm text-ink mb-2">No report yet</p>
                <p className="text-body-sm">Select sources and generate a report to preview it here.</p>
              </div>
            )}
          </div>
        </div>
      </PageContainer>
    </div>
  );
}
