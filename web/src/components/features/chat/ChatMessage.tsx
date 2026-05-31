import { TextLink } from "@/components/ui/TextLink";
import type { ChatMessage as ChatMessageType } from "@/lib/data/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

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
      </div>
    </div>
  );
}
