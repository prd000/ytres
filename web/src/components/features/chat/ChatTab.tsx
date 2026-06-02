"use client";

import { useRef, useEffect, useState, useTransition } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ChatMessage } from "@/components/features/chat/ChatMessage";
import { sendChatMessage } from "@/app/(app)/project/[id]/chat/actions";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";

interface ChatTabProps {
  projectId: string;
  initialMessages: ChatMessageType[];
}

export function ChatTab({ projectId, initialMessages }: ChatTabProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState("");
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  // Track whether we're waiting for the assistant reply (last message is from user)
  const waitingForReply =
    initialMessages.length > 0 &&
    initialMessages[initialMessages.length - 1].role === "user";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [initialMessages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isPending) return;

    setError(null);
    setQuestion("");

    startTransition(async () => {
      const result = await sendChatMessage(projectId, trimmed);
      if (result?.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[500px]">
      <div className="flex-1 overflow-y-auto">
        <PageContainer className="py-8">
          {initialMessages.length === 0 && !isPending ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-title-md text-ink mb-2">No messages yet</p>
              <p className="text-body-sm text-muted max-w-panel">
                Ask a question about your research and the AI will answer using
                your stored sources.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {initialMessages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  projectId={projectId}
                />
              ))}
              {/* Typing indicator while waiting for assistant reply */}
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

      {/* Composer */}
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
