"use client";

import { useRef, useEffect, useState, useTransition } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ChatMessage } from "@/components/features/chat/ChatMessage";
import { sendChatMessage } from "@/app/(app)/project/[id]/chat/actions";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";
import { createClient } from "@/lib/supabase/client";

interface ChatTabProps {
  projectId: string;
  initialMessages: ChatMessageType[];
}

export function ChatTab({ projectId, initialMessages }: ChatTabProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState("");
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>(initialMessages);
  // Tracks the temporary ID of an optimistic user message so the real one can replace it.
  const optimisticIdRef = useRef<string | null>(null);
  // Tracks whether research was just spawned (before worker picks it up) and which subtopics are actively running.
  const [spawnedPending, setSpawnedPending] = useState(false);
  const [activeResearchIds, setActiveResearchIds] = useState<string[]>([]);

  // Subscribe to Realtime INSERT events and append directly to local state —
  // no router.refresh() round-trip needed.
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
        (payload) => {
          const row = payload.new as Record<string, unknown>;
          const msg: ChatMessageType = {
            id: row.id as string,
            projectId: row.project_id as string,
            role: row.role as ChatMessageType["role"],
            content: row.content as string,
            citations: (row.citations as ChatMessageType["citations"]) ?? [],
            confidence: (row.confidence as ChatMessageType["confidence"]) ?? undefined,
            createdAt: new Date(row.created_at as string),
          };
          setMessages((prev) => {
            // Replace the optimistic placeholder when the real user message arrives.
            if (msg.role === "user" && optimisticIdRef.current) {
              const filtered = prev.filter((m) => m.id !== optimisticIdRef.current);
              optimisticIdRef.current = null;
              return [...filtered, msg];
            }
            // Deduplicate — guard against any double-delivery edge cases.
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
          });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [projectId]);

  // Subscribe to worker_activity to track research-in-progress state.
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel(`worker_activity_chat:${projectId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "worker_activity",
          filter: `project_id=eq.${projectId}`,
        },
        (payload) => {
          // Any activity event means the worker has picked up the job.
          setSpawnedPending(false);
          const row = payload.new as Record<string, unknown> | null;
          if (!row) return;
          const subtopicId = row.subtopic_id as string;
          const status = row.status as string;
          if (status === "running") {
            setActiveResearchIds((prev) =>
              prev.includes(subtopicId) ? prev : [...prev, subtopicId]
            );
          } else {
            setActiveResearchIds((prev) => prev.filter((id) => id !== subtopicId));
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // True when the last message in local state is from the user (assistant reply pending).
  const waitingForReply =
    messages.length > 0 && messages[messages.length - 1].role === "user";

  const researchInProgress = spawnedPending || activeResearchIds.length > 0;

  function handleResearchSpawned() {
    setSpawnedPending(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isPending) return;

    setError(null);
    setQuestion("");

    // Optimistically append the user's message so it appears immediately.
    const optimisticId = `optimistic-${Date.now()}`;
    optimisticIdRef.current = optimisticId;
    setMessages((prev) => [
      ...prev,
      {
        id: optimisticId,
        projectId,
        role: "user",
        content: trimmed,
        citations: [],
        createdAt: new Date(),
      },
    ]);

    startTransition(async () => {
      const result = await sendChatMessage(projectId, trimmed);
      if (result?.error) {
        setError(result.error);
        setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
        optimisticIdRef.current = null;
      }
    });
  }

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[500px]">
      <div className="flex-1 overflow-y-auto">
        <PageContainer className="py-8">
          {messages.length === 0 && !isPending ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-title-md text-ink mb-2">No messages yet</p>
              <p className="text-body-sm text-muted max-w-panel">
                Ask a question about your research and the AI will answer using
                your stored sources.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  projectId={projectId}
                  onResearchSpawned={handleResearchSpawned}
                />
              ))}
              {researchInProgress && (
                <div className="flex justify-center">
                  <div className="flex items-center gap-2 text-body-sm text-muted px-4 py-2 bg-surface-soft border border-hairline-soft rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-teal animate-pulse flex-shrink-0" />
                    Research in progress…
                  </div>
                </div>
              )}
              {(isPending || waitingForReply) && (
                <div className="flex justify-start">
                  <div className="bg-surface-card text-muted border border-hairline-soft rounded-lg px-4 py-3">
                    <span className="text-body-sm">Thinking…</span>
                  </div>
                </div>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </PageContainer>
      </div>

      <div className="border-t border-hairline bg-canvas py-4">
        <PageContainer>
          {error && (
            <p className="text-body-sm text-error mb-2">{error}</p>
          )}
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about your research…"
              disabled={isPending}
              className="flex-1 h-10 px-4 bg-surface-soft text-ink text-body-md rounded-md border border-hairline focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:text-muted-soft disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={isPending || !question.trim()}
              className="h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary/90 transition-colors disabled:bg-primary-disabled disabled:text-muted disabled:cursor-not-allowed"
            >
              {isPending ? "Sending…" : "Send"}
            </button>
          </form>
        </PageContainer>
      </div>
    </div>
  );
}
