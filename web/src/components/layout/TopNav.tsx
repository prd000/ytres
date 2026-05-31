"use client";

import Link from "next/link";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { SpikeMark } from "@/components/ui/SpikeMark";
import { PageContainer } from "@/components/layout/PageContainer";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import type { User } from "@supabase/supabase-js";

interface TopNavProps {
  user?: User | null;
  signOut?: () => Promise<void>;
}

export function TopNav({ user, signOut }: TopNavProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 h-16 bg-canvas border-b border-hairline">
      <PageContainer className="h-full flex items-center justify-between">
        {/* Wordmark */}
        <Link href="/dashboard" className="flex items-center gap-2 text-ink hover:text-primary transition-colors">
          <SpikeMark size={14} className="text-primary" />
          <span className="text-title-sm tracking-tight">ytres</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          <Link
            href="/dashboard"
            className="text-nav-link text-muted hover:text-ink px-3 py-2 rounded-md hover:bg-surface-soft transition-colors"
          >
            Dashboard
          </Link>
        </nav>

        {/* Desktop right cluster */}
        <div className="hidden md:flex items-center gap-3">
          <ThemeToggle />
          {user ? (
            <>
              <span className="text-body-sm text-muted hidden lg:block">{user.email}</span>
              <form action={signOut}>
                <button
                  type="submit"
                  className="text-button text-muted hover:text-ink transition-colors"
                >
                  Sign out
                </button>
              </form>
            </>
          ) : (
            <>
              <Link href="/login" className="text-button text-muted hover:text-ink transition-colors">
                Sign in
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center justify-center h-8 px-4 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors"
              >
                Get started
              </Link>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
          <Dialog.Trigger asChild>
            <button
              className="md:hidden p-2 rounded-md text-ink hover:bg-surface-soft transition-colors"
              aria-label="Open menu"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M2 5h16M2 10h16M2 15h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </Dialog.Trigger>

          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-[#141413]/50" />
            <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-sm flex flex-col bg-canvas p-6 shadow-lg">
              <div className="flex items-center justify-between mb-8">
                <Link href="/dashboard" className="flex items-center gap-2 text-ink" onClick={() => setMobileOpen(false)}>
                  <SpikeMark size={14} className="text-primary" />
                  <span className="text-title-sm tracking-tight">ytres</span>
                </Link>
                <div className="flex items-center gap-2">
                  <ThemeToggle />
                  <Dialog.Close asChild>
                    <button className="p-2 rounded-md text-muted hover:text-ink hover:bg-surface-soft transition-colors" aria-label="Close menu">
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                        <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </button>
                  </Dialog.Close>
                </div>
              </div>

              <nav className="flex flex-col gap-1 flex-1">
                <Link
                  href="/dashboard"
                  className="text-title-sm text-body py-3 border-b border-hairline-soft hover:text-ink transition-colors"
                  onClick={() => setMobileOpen(false)}
                >
                  Dashboard
                </Link>
              </nav>

              <div className="flex flex-col gap-3 pt-6 border-t border-hairline">
                {user ? (
                  <>
                    <p className="text-body-sm text-muted text-center truncate">{user.email}</p>
                    <form action={signOut}>
                      <button
                        type="submit"
                        className="flex items-center justify-center w-full h-10 px-5 text-button text-ink border border-hairline rounded-md hover:bg-surface-soft transition-colors"
                        onClick={() => setMobileOpen(false)}
                      >
                        Sign out
                      </button>
                    </form>
                  </>
                ) : (
                  <>
                    <Link href="/login" className="text-button text-muted text-center py-2" onClick={() => setMobileOpen(false)}>
                      Sign in
                    </Link>
                    <Link
                      href="/signup"
                      className="flex items-center justify-center h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors w-full"
                      onClick={() => setMobileOpen(false)}
                    >
                      Get started
                    </Link>
                  </>
                )}
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </PageContainer>
    </header>
  );
}
