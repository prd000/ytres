"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { ButtonHTMLAttributes, forwardRef } from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 text-button rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-on-primary hover:bg-primary-active active:bg-primary-active disabled:bg-primary-disabled disabled:text-muted",
        secondary:
          "bg-canvas text-ink border border-hairline hover:bg-surface-soft active:bg-surface-card disabled:text-muted-soft",
        secondaryOnDark:
          "bg-surface-dark-elevated text-on-dark border border-surface-dark-elevated hover:bg-surface-dark-soft active:bg-surface-dark-soft",
        text: "bg-transparent text-ink hover:text-primary active:text-primary-active",
        icon: "bg-canvas text-ink border border-hairline rounded-full hover:bg-surface-soft active:bg-surface-card",
        destructive:
          "bg-error text-on-primary hover:bg-error/90 active:bg-error/80",
      },
      size: {
        default: "h-10 px-5 py-3",
        sm: "h-8 px-3 py-2 text-caption",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
