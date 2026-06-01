"use client";

import { useRef, useEffect } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ChatMessage } from "@/components/features/chat/ChatMessage";
import { Callout } from "@/components/ui/Callout";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";

interface ChatTabProps {
  projectId: string;
  initialMessages: ChatMessageType[];
}

export function ChatTab({ projectId: _projectId, initialMessages }: ChatTabProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [initialMessages]);

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[500px]">
      <div className="flex-1 overflow-y-auto">
        <PageContainer className="py-8">
          <Callout variant="info" title="Chat coming soon" className="mb-6">
            AI-powered chat with inline citations becomes available once the RAG
            backend is connected (Phase 9).
          </Callout>

          {initialMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-title-md text-ink mb-2">No messages yet</p>
              <p className="text-body-sm text-muted max-w-sm">
                Chat will be available once your research is complete and the
                RAG backend is connected.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {initialMessages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </PageContainer>
      </div>

      {/* Composer — disabled until RAG backend (Phase 9) */}
      <div className="border-t border-hairline bg-canvas py-4">
        <PageContainer>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Chat available once the RAG backend is connected…"
              disabled
              className="flex-1 h-10 px-4 bg-surface-soft text-muted-soft text-body-md rounded-md border border-hairline cursor-not-allowed"
            />
            <button
              type="button"
              disabled
              className="h-10 px-5 text-button bg-primary-disabled text-muted rounded-md cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </PageContainer>
      </div>
    </div>
  );
}
