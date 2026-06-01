import { StatusPill } from "@/components/ui/StatusPill";
import { DeleteProjectButton } from "@/components/layout/DeleteProjectButton";
import type { Project } from "@/lib/data/types";

interface ProjectShellHeaderProps {
  project: Project;
}

export function ProjectShellHeader({ project }: ProjectShellHeaderProps) {
  return (
    <div className="bg-canvas border-b border-hairline py-5">
      <div className="mx-auto w-full max-w-content px-4 sm:px-6 lg:px-8">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 mb-1">
              <StatusPill status={project.status} />
            </div>
            <h1 className="text-display-sm text-ink line-clamp-2">{project.researchQuestion}</h1>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {(project.status === "researching" || project.status === "planning") && (
              <button className="shrink-0 inline-flex items-center justify-center h-8 px-3 text-button text-muted border border-hairline rounded-md hover:border-error hover:text-error transition-colors text-sm">
                Cancel
              </button>
            )}
            <DeleteProjectButton projectId={project.id} />
          </div>
        </div>
      </div>
    </div>
  );
}
