"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

/**
 * Circular icon button that flips between light and dark.
 * Styled per DESIGN.md `button-icon-circular` (36px, canvas bg, hairline
 * border, ink icon). Guards on `mounted` because the resolved theme is only
 * known client-side — rendering theme-dependent markup during SSR would cause
 * a hydration mismatch.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label={
        mounted ? `Switch to ${isDark ? "light" : "dark"} mode` : "Toggle theme"
      }
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-pill border border-hairline bg-canvas text-ink hover:bg-surface-soft transition-colors",
        className,
      )}
    >
      {/* Until mounted, render a neutral placeholder so SSR/client markup match. */}
      {!mounted ? (
        <span className="block h-[18px] w-[18px]" aria-hidden="true" />
      ) : isDark ? (
        // Sun — click switches to light
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="3.5" stroke="currentColor" strokeWidth="1.5" />
          <path
            d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M3.9 3.9l1.4 1.4M14.7 14.7l1.4 1.4M16.1 3.9l-1.4 1.4M5.3 14.7l-1.4 1.4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        // Moon — click switches to dark
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M16.5 11.5A6.5 6.5 0 1 1 8.5 3.5a5 5 0 1 0 8 8Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}
