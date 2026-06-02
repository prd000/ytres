"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

interface ChatRealtimeProps {
  projectId: string;
}

/**
 * Mounts a Supabase Realtime subscription for the chat page.
 * Subscribes to INSERT events on `chat_messages` scoped to this project.
 * On a new row, calls router.refresh() so the server component re-fetches
 * the message list without a full page reload.
 *
 * Requires migration 0013 (alter publication supabase_realtime add table chat_messages).
 */
export function ChatRealtime({ projectId }: ChatRealtimeProps) {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel(`chat_messages:${projectId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "chat_messages",
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
