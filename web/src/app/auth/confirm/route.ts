import { type EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Email confirmation handler.
 *
 * Supabase email templates link here with `token_hash` + `type` (configure the
 * "Confirm signup" template to point at `{{ .SiteURL }}/auth/confirm?...`). We
 * verify the OTP server-side so the session cookie is written through the SSR
 * client — leaving the user authenticated on the server. The default implicit
 * flow only sets a client-side token in the URL fragment, which never reaches
 * our cookie-based server session.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const token_hash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = searchParams.get("next") ?? "/dashboard";

  // Only ever redirect to an in-app path — never an attacker-supplied URL.
  const safeNext =
    next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";

  // Render (and most PaaS proxies) terminate TLS upstream, so the public host
  // arrives via forwarded headers. Prefer those to build an absolute redirect.
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const origin = forwardedHost
    ? `${forwardedProto ?? "https"}://${forwardedHost}`
    : request.nextUrl.origin;

  if (token_hash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash });
    if (!error) {
      return NextResponse.redirect(`${origin}${safeNext}`);
    }
  }

  const reason = encodeURIComponent(
    "Email confirmation link is invalid or has expired. Please sign in or request a new link."
  );
  return NextResponse.redirect(`${origin}/login?error=${reason}`);
}
