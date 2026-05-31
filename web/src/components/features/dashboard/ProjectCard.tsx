import Link from "next/link";
import { StatusPill } from "@/components/ui/StatusPill";
import { formatRelativeDate } from "@/lib/utils";
import type { Project } from "@/lib/data/types";

interface ProjectCardProps {
  project: Project;
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link
      href={`/project/${project.id}/plan`}
      className="group block bg-surface-card rounded-lg p-6 border border-hairline-soft hover:border-hairline hover:shadow-[0_1px_3px_rgba(20,20,19,0.08)] transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <StatusPill status={project.status} />
      </div>
      <p className="text-title-sm text-ink group-hover:text-ink line-clamp-3 mb-4">
        {project.researchQuestion}
      </p>
      <p className="text-body-sm text-muted">
        Updated {formatRelativeDate(project.lastUpdated)}
      </p>
    </Link>
  );
}
