"use client";

import ReactMarkdown from "react-markdown";

interface ReportPreviewProps {
  markdown: string;
}

export function ReportPreview({ markdown }: ReportPreviewProps) {
  return (
    <article className="prose prose-neutral max-w-none bg-canvas rounded-lg border border-hairline p-8">
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h1 className="text-display-md text-ink mt-0 mb-6">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-display-sm text-ink mt-8 mb-4">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-title-md text-ink mt-6 mb-3">{children}</h3>
          ),
          p: ({ children }) => (
            <p className="text-body-md text-body mb-4">{children}</p>
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:text-primary-active underline underline-offset-2">
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-6 mb-4 flex flex-col gap-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-6 mb-4 flex flex-col gap-1">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="text-body-md text-body">{children}</li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary pl-4 my-4 text-muted">{children}</blockquote>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <pre className="bg-surface-dark rounded-lg p-4 overflow-x-auto">
                  <code className="font-mono text-on-dark text-body-sm">{children}</code>
                </pre>
              );
            }
            return (
              <code className="bg-surface-card text-ink font-mono text-caption px-1.5 py-0.5 rounded-sm">
                {children}
              </code>
            );
          },
          strong: ({ children }) => (
            <strong className="font-medium text-ink">{children}</strong>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
