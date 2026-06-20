"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { ReportPreview } from "@/components/features/report/ReportPreview";
import { Button } from "@/components/ui/Button";
import type { Report } from "@/lib/data/types";

interface ReportTabProps {
  existingReport: Report | null;
  isGenerating: boolean;
}

export function ReportTab({ existingReport, isGenerating }: ReportTabProps) {
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

  return (
    <div className="py-10">
      <PageContainer>
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
            <div className="flex justify-end mb-4">
              <Button variant="secondary" onClick={handleDownload}>
                Download .md
              </Button>
            </div>
            <ReportPreview markdown={existingReport.markdown} />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-center text-muted border border-dashed border-hairline rounded-lg">
            <p className="text-title-sm text-ink mb-2">No report yet</p>
            <p className="text-body-sm">
              Go to the <strong>Sources</strong> tab to select sources and generate a report.
            </p>
          </div>
        )}
      </PageContainer>
    </div>
  );
}
