import Link from "next/link";
import { PageContainer } from "@/components/layout/PageContainer";
import { ProjectCard } from "@/components/features/dashboard/ProjectCard";
import { EmptyState } from "@/components/features/dashboard/EmptyState";
import type { Project } from "@/lib/data/types";

interface DashboardViewProps {
  projects: Project[];
}

export function DashboardView({ projects }: DashboardViewProps) {
  return (
    <div className="py-12">
      <PageContainer>
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-display-md text-ink">Research Projects</h1>
          <Link
            href="/project/new"
            className="inline-flex items-center gap-2 h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            New project
          </Link>
        </div>

        {projects.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </PageContainer>
    </div>
  );
}
