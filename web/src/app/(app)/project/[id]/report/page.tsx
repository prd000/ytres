import { notFound } from "next/navigation";
import { getProject, getSources, getReport } from "@/lib/data/client";
import { ReportTab } from "@/components/features/report/ReportTab";
import { ReportRealtime } from "@/components/features/realtime/ReportRealtime";

export default async function ReportPage(props: PageProps<"/project/[id]/report">) {
  const { id } = await props.params;
  const [project, sources, report] = await Promise.all([
    getProject(id),
    getSources(id),
    getReport(id),
  ]);
  if (!project) notFound();
  return (
    <>
      <ReportRealtime projectId={id} />
      <ReportTab project={project} sources={sources} existingReport={report} />
    </>
  );
}
