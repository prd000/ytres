import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type BadgeVariant = "pill" | "coral" | "outline";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  pill: "bg-surface-card text-ink text-caption rounded-pill px-3 py-1",
  coral: "bg-primary text-on-primary text-caption-uppercase rounded-pill px-3 py-1",
  outline: "border border-hairline text-muted text-caption rounded-pill px-3 py-1",
};

export function Badge({ variant = "pill", className, children, ...props }: BadgeProps) {
  return (
    <span className={cn(variantClasses[variant], className)} {...props}>
      {children}
    </span>
  );
}
