import { notFound } from "next/navigation";
import { getProject, getSubtopics } from "@/lib/data/client";
import { PlanTab } from "@/components/features/plan/PlanTab";

export default async function PlanPage(props: PageProps<"/project/[id]/plan">) {
  const { id } = await props.params;
  const [project, subtopics] = await Promise.all([getProject(id), getSubtopics(id)]);
  if (!project) notFound();
  return <PlanTab project={project} subtopics={subtopics} />;
}
