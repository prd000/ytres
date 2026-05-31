import "server-only";
import { createClient } from "@supabase/supabase-js";

// Service-role client — bypasses RLS. Use only in Server Actions that require
// privileged writes. Never expose SUPABASE_SERVICE_ROLE_KEY to the browser.
export function createAdminClient() {
  return createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
  );
}
