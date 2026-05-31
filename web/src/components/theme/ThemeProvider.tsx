"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Wraps the app in next-themes. Uses the `class` strategy → toggles `.dark` on
 * <html>, which our globals.css remaps all role tokens against. `defaultTheme`
 * is "system" so first-time visitors match their OS preference; the choice is
 * then persisted to localStorage by next-themes. `disableTransitionOnChange`
 * avoids a color-transition flash on toggle.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
