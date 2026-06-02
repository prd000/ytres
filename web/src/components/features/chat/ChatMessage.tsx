"use client";

import { useTransition } from "react";
import { TextLink } from "@/components/ui/TextLink";
import { spawnResearchFromChat } from "@/app/(app)/project/[id]/chat/actions";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";

interface ChatMessageProps {
  message: ChatMessageType;
  projectId: string;
}

export function ChatMessage({ message, projectId }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isLowConfidence = !isUser && message.confidence === "low";
  const [isPending, startTransition] = useTransition();

  function handleSpawn() {
    const topic = message.content.slice(0, 200);
    startTransition(async () => {
      await spawnResearchFromChat(projectId, topic);
    });
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-primary text-on-primary"
            : "bg-surface-card text-ink border border-hairline-soft"
        }`}
      >
        <p className={`text-body-sm whitespace-pre-wrap ${isUser ? "" : "text-body"}`}>
          {message.content}
        </p>
        {message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-hairline-soft flex flex-wrap gap-1.5">
            {message.citations.map((c) => (
              <TextLink
                key={c.sourceId}
                href={c.url}
                external
                className="text-caption bg-canvas px-2 py-0.5 rounded-sm"
              >
                {c.sourceTitle}
              </TextLink>
            ))}
          </div>
        )}
        {isLowConfidence && (
          <div className="mt-3 pt-3 border-t border-hairline-soft">
            <button
              type="button"
              onClick={handleSpawn}
              disabled={isPending}
              className="text-body-sm text-primary hover:underline disabled:text-muted disabled:cursor-not-allowed"
            >
              {isPending ? "Queuing research…" : "Research this →"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
