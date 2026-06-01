import { NextRequest, NextResponse } from "next/server";
import { updateSession } from "@/lib/supabase/proxy-session";

// Routes under the (app) group that require authentication
const APP_PATTERN = /^\/(dashboard|project)(\/|$)/;
// Auth-only routes — redirect signed-in users away
const AUTH_PATTERN = /^\/(login|signup)(\/|$)/;

export async function proxy(request: NextRequest) {
  const { response, user } = await updateSession(request);
  const { pathname } = request.nextUrl;

  // Unauthenticated user on a protected route → /login
  if (!user && APP_PATTERN.test(pathname)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Authenticated user on an auth route → /dashboard
  if (user && AUTH_PATTERN.test(pathname)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Return the session-refreshed response (may contain updated cookies).
  return response;
}

export const config = {
  // Run on all paths except Next.js internals and static assets.
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
