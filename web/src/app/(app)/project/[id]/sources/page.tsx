import { notFound } from "next/navigation";
import { getProject, getSubtopics, getSources } from "@/lib/data/client";
import { SourcesTab } from "@/components/features/sources/SourcesTab";

export default async function SourcesPage(props: PageProps<"/project/[id]/sources">) {
  const { id } = await props.params;
  const [project, subtopics, sources] = await Promise.all([
    getProject(id),
    getSubtopics(id),
    getSources(id),
  ]);
  if (!project) notFound();
  return <SourcesTab project={project} subtopics={subtopics} sources={sources} />;
}
