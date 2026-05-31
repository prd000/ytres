import "server-only";
import { cache } from "react";
import { createClient } from "@/lib/supabase/server";

/**
 * Returns the currently authenticated Supabase user, or null.
 * React cache() dedups the Supabase call within a single render pass.
 */
export const getCurrentUser = cache(async () => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
});
