"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

interface ReportRealtimeProps {
  projectId: string;
}

/**
 * Mounts a Supabase Realtime subscription for the report page.
 * Subscribes to INSERT events on `reports` scoped to this project.
 * On a new report row, calls router.refresh() so the server component
 * re-fetches the latest report without a full page reload.
 *
 * Requires migration 0012 (alter publication supabase_realtime add table reports)
 * and the Realtime publication enabled in the Supabase dashboard.
 */
export function ReportRealtime({ projectId }: ReportRealtimeProps) {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel(`reports:${projectId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "reports",
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
