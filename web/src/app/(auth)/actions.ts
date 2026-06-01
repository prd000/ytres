"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type AuthState = { error: string } | undefined;

export async function login(
  _prev: AuthState,
  formData: FormData
): Promise<AuthState> {
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
  });
  if (error) return { error: error.message };
  redirect("/dashboard");
}

export async function signup(
  _prev: AuthState,
  formData: FormData
): Promise<AuthState> {
  const supabase = await createClient();

  // Build an absolute confirm URL from the request origin so the email link
  // points back at whatever host the user signed up on (localhost in dev, the
  // Render URL in prod). This must also be allow-listed in the Supabase
  // dashboard → Authentication → URL Configuration → Redirect URLs.
  const origin = (await headers()).get("origin");

  const { error } = await supabase.auth.signUp({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
    options: {
      data: { full_name: formData.get("name") as string },
      emailRedirectTo: origin ? `${origin}/auth/confirm` : undefined,
    },
  });
  if (error) return { error: error.message };
  redirect("/dashboard");
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
