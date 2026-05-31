import { notFound } from "next/navigation";
import { getProject } from "@/lib/data/client";
import { ProjectShellHeader } from "@/components/layout/ProjectShellHeader";
import { ProjectTabNav } from "@/components/layout/ProjectTabNav";
import { ReactNode } from "react";

export default async function ProjectLayout(props: LayoutProps<"/project/[id]">) {
  const { id } = await props.params;
  const project = await getProject(id);

  if (!project) notFound();

  return (
    <div className="flex flex-col flex-1">
      {/* These stay mounted as tab content swaps — Phase 7 Realtime seam */}
      <ProjectShellHeader project={project} />
      <ProjectTabNav projectId={id} />
      <div className="flex-1 bg-canvas">{props.children}</div>
    </div>
  );
}
