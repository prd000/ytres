import { notFound } from "next/navigation";
import { getProject, getSubtopics, getWorkerActivity } from "@/lib/data/client";
import { ResearchTab } from "@/components/features/research/ResearchTab";

export default async function ResearchPage(props: PageProps<"/project/[id]/research">) {
  const { id } = await props.params;
  const [project, subtopics, activity] = await Promise.all([
    getProject(id),
    getSubtopics(id),
    getWorkerActivity(id),
  ]);
  if (!project) notFound();
  return <ResearchTab project={project} subtopics={subtopics} activity={activity} />;
}
