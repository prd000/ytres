"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/Input";
import { login, type AuthState } from "@/app/(auth)/actions";

export function LoginForm() {
  const [state, action, pending] = useActionState<AuthState, FormData>(
    login,
    undefined
  );

  return (
    <form action={action} className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <label htmlFor="email" className="text-caption text-ink">Email</label>
        <Input
          id="email"
          name="email"
          type="email"
          placeholder="you@example.com"
          required
          autoComplete="email"
        />
      </div>
      <div className="flex flex-col gap-2">
        <label htmlFor="password" className="text-caption text-ink">Password</label>
        <Input
          id="password"
          name="password"
          type="password"
          placeholder="••••••••"
          required
          autoComplete="current-password"
        />
      </div>

      {state?.error && (
        <p className="text-sm text-error" role="alert">{state.error}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-4 w-full h-10 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:opacity-60"
      >
        {pending ? "Signing in…" : "Sign in"}
      </button>

      <p className="text-body-sm text-muted text-center">
        No account?{" "}
        <Link href="/signup" className="text-primary hover:text-primary-active transition-colors">
          Create one
        </Link>
      </p>
    </form>
  );
}
