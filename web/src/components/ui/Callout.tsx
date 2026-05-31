import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type CalloutVariant = "coral" | "info" | "warning";

interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CalloutVariant;
  title?: string;
}

const variantClasses: Record<CalloutVariant, string> = {
  coral: "bg-primary text-on-primary",
  info: "bg-accent-teal/10 text-ink border border-accent-teal/25",
  warning: "bg-warning/10 text-ink border border-warning/25",
};

export function Callout({ variant = "coral", title, className, children, ...props }: CalloutProps) {
  return (
    <div className={cn("rounded-lg p-6", variantClasses[variant], className)} {...props}>
      {title && <p className="text-title-sm mb-1">{title}</p>}
      <div className="text-body-sm opacity-90">{children}</div>
    </div>
  );
}
