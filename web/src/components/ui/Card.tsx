import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type SurfaceVariant = "card" | "dark" | "coral" | "canvas" | "canvas-bordered" | "dark-elevated";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  surface?: SurfaceVariant;
  padding?: "none" | "sm" | "default" | "lg";
}

const surfaceClasses: Record<SurfaceVariant, string> = {
  canvas: "bg-canvas text-ink",
  "canvas-bordered": "bg-canvas text-ink border border-hairline",
  card: "bg-surface-card text-ink",
  dark: "bg-surface-dark text-on-dark",
  "dark-elevated": "bg-surface-dark-elevated text-on-dark",
  coral: "bg-primary text-on-primary",
};

const paddingClasses = {
  none: "",
  sm: "p-4",
  default: "p-6",
  lg: "p-8",
};

export function Card({ surface = "card", padding = "default", className, children, ...props }: CardProps) {
  return (
    <div
      className={cn("rounded-lg", surfaceClasses[surface], paddingClasses[padding], className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function Surface({ surface = "card", padding = "default", className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(surfaceClasses[surface], paddingClasses[padding], className)}
      {...props}
    >
      {children}
    </div>
  );
}
