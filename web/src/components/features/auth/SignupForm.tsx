"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/Input";
import { signup, type AuthState } from "@/app/(auth)/actions";

export function SignupForm() {
  const [state, action, pending] = useActionState<AuthState, FormData>(
    signup,
    undefined
  );

  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="name" className="text-caption text-ink">Full name</label>
        <Input
          id="name"
          name="name"
          type="text"
          placeholder="Your name"
          required
          autoComplete="name"
        />
      </div>
      <div className="flex flex-col gap-1.5">
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
      <div className="flex flex-col gap-1.5">
        <label htmlFor="password" className="text-caption text-ink">Password</label>
        <Input
          id="password"
          name="password"
          type="password"
          placeholder="8+ characters"
          required
          minLength={8}
          autoComplete="new-password"
        />
      </div>

      {state?.error && (
        <p className="text-sm text-error" role="alert">{state.error}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-2 w-full h-10 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:opacity-60"
      >
        {pending ? "Creating account…" : "Create account"}
      </button>

      <p className="text-body-sm text-muted text-center">
        Already have an account?{" "}
        <Link href="/login" className="text-primary hover:text-primary-active transition-colors">
          Sign in
        </Link>
      </p>
    </form>
  );
}
