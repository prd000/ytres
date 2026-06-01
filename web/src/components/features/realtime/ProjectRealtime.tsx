"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

interface ProjectRealtimeProps {
  projectId: string;
}

/**
 * Mounts a Supabase Realtime subscription for the project layout.
 * Subscribes to changes on `subtopics` and `projects` scoped to this project.
 * On any change, calls router.refresh() so server components re-fetch
 * the latest state without a full page reload.
 *
 * Stays mounted across tab switches (lives in the project layout, not pages).
 * Cleanup on unmount removes the Realtime channel.
 *
 * RLS note: createBrowserClient propagates the user's session automatically
 * so Realtime row-level security (can_access_project) is enforced.
 * If events don't arrive, call supabase.realtime.setAuth(token) explicitly.
 */
export function ProjectRealtime({ projectId }: ProjectRealtimeProps) {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel(`project:${projectId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "subtopics",
          filter: `project_id=eq.${projectId}`,
        },
        () => {
          router.refresh();
        }
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "projects",
          filter: `id=eq.${projectId}`,
        },
        () => {
          router.refresh();
        }
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "worker_activity",
          filter: `project_id=eq.${projectId}`,
        },
        () => {
          router.refresh();
        }
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "sources",
          filter: `project_id=eq.${projectId}`,
        },
        () => {
          router.refresh();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [projectId, router]);

  return null;
}
