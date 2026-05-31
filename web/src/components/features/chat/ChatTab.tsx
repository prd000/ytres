"use client";

import { useState, useRef, useEffect } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ChatMessage } from "@/components/features/chat/ChatMessage";
import { Callout } from "@/components/ui/Callout";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";

interface ChatTabProps {
  projectId: string;
  initialMessages: ChatMessageType[];
}

export function ChatTab({ projectId: _projectId, initialMessages }: ChatTabProps) {
  const [messages, setMessages] = useState<ChatMessageType[]>(initialMessages);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg: ChatMessageType = {
      id: `msg-${Date.now()}`,
      projectId: _projectId,
      role: "user",
      content: input.trim(),
      citations: [],
      createdAt: new Date(),
    };
    const assistantMsg: ChatMessageType = {
      id: `msg-${Date.now() + 1}`,
      projectId: _projectId,
      role: "assistant",
      content: "*(Mock response — connect to the RAG backend in Phase 9 to get real answers based on your stored sources.)*",
      citations: [],
      createdAt: new Date(),
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
  }

  const hasNoSources = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[500px]">
      <div className="flex-1 overflow-y-auto">
        <PageContainer className="py-8">
          {hasNoSources && (
            <Callout variant="info" title="Chat with your sources" className="mb-6">
              Once research is complete, ask questions and the AI will answer using your stored sources with inline citations.
            </Callout>
          )}

          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-title-md text-ink mb-2">Ask anything about your research</p>
              <p className="text-body-sm text-muted max-w-sm">
                The chatbot searches your stored sources and cites them inline.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </PageContainer>
      </div>

      {/* Composer */}
      <div className="border-t border-hairline bg-canvas py-4">
        <PageContainer>
          <form onSubmit={handleSend} className="flex gap-3">
            <input
              type="text"
              placeholder="Ask a question about your research…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="flex-1 h-10 px-4 bg-canvas text-ink text-body-md rounded-md border border-hairline placeholder:text-muted-soft focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition-colors"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:bg-primary-disabled disabled:text-muted disabled:cursor-not-allowed"
            >
              Send
            </button>
          </form>
        </PageContainer>
      </div>
    </div>
  );
}
