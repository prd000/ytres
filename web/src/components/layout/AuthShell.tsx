import Link from "next/link";
import { SpikeMark } from "@/components/ui/SpikeMark";
import { ReactNode } from "react";

interface AuthShellProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="min-h-screen bg-canvas flex flex-col justify-center px-4 py-16">
      <div className="w-full max-w-card mx-auto">
        {/* Wordmark */}
        <Link href="/" className="flex items-center gap-2 text-ink hover:text-primary transition-colors justify-center mb-10">
          <SpikeMark size={16} className="text-primary" />
          <span className="text-title-md tracking-tight">ytres</span>
        </Link>

        {/* Card */}
        <div className="bg-surface-card rounded-xl p-8 border border-hairline-soft">
          <div className="mb-8">
            <h1 className="text-display-sm text-ink">{title}</h1>
            {subtitle && <p className="text-body-sm text-muted mt-2">{subtitle}</p>}
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
