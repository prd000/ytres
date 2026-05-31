"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { PageContainer } from "@/components/layout/PageContainer";

const TABS = [
  { label: "Plan", path: "plan" },
  { label: "Research", path: "research" },
  { label: "Sources", path: "sources" },
  { label: "Chat", path: "chat" },
  { label: "Report", path: "report" },
] as const;

interface ProjectTabNavProps {
  projectId: string;
}

export function ProjectTabNav({ projectId }: ProjectTabNavProps) {
  const pathname = usePathname();

  return (
    <div className="bg-canvas border-b border-hairline">
      <PageContainer>
        <nav className="flex gap-1 overflow-x-auto scrollbar-none py-1" aria-label="Project tabs">
          {TABS.map((tab) => {
            const href = `/project/${projectId}/${tab.path}`;
            const isActive = pathname === href;
            return (
              <Link
                key={tab.path}
                href={href}
                className={cn(
                  "text-nav-link shrink-0 px-[14px] py-2 rounded-md transition-colors whitespace-nowrap",
                  isActive
                    ? "bg-surface-card text-ink"
                    : "text-muted hover:text-ink hover:bg-surface-soft"
                )}
                aria-current={isActive ? "page" : undefined}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </PageContainer>
    </div>
  );
}
