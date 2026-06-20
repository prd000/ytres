import { notFound } from "next/navigation";
import { getProject, getReport, getActiveReportJob } from "@/lib/data/client";
import { ReportTab } from "@/components/features/report/ReportTab";
import { ReportRealtime } from "@/components/features/realtime/ReportRealtime";

export default async function ReportPage(props: PageProps<"/project/[id]/report">) {
  const { id } = await props.params;
  const [project, report, isGenerating] = await Promise.all([
    getProject(id),
    getReport(id),
    getActiveReportJob(id),
  ]);
  if (!project) notFound();
  return (
    <>
      <ReportRealtime projectId={id} />
      <ReportTab existingReport={report} isGenerating={isGenerating} />
    </>
  );
}
