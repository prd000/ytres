# Fix "Not authenticated" on project creation + skinny sign-in page

## Context

When creating a project, clicking **Create project** returns a "Not authenticated" error instead of working. The user correctly noted: *if they simply weren't signed in, they should have been redirected to `/login`* — never shown this error from inside the app.

That observation is the key. The redirect-to-login is the job of `web/proxy.ts` (Next.js 16's replacement for `middleware.ts`). **The proxy is in the wrong location, so it never runs.**

Per the Next.js 16 docs (`node_modules/next/dist/docs/.../proxy.md`):
> Create a `proxy.ts` file in the project root, **or inside `src` if applicable, so that it is located at the same level as `pages` or `app`.**

This project's app lives at `web/src/app/`, but `proxy.ts` is at `web/proxy.ts` (project root). With the app under `src/`, Next.js only picks up `web/src/proxy.ts`. As placed, the proxy is silently ignored, which means:

- **No auth gating** — an unauthenticated visitor is never redirected to `/login`. They reach `/project/new` (a plain form with no auth check) and only hit the wall when `createProject`'s `supabase.auth.getUser()` returns null → `"Not authenticated."`
- **No session refresh** — even signed-in users' tokens are never refreshed (JWT expiry is 1h with refresh-token rotation), so sessions silently break after expiry.

This explains every symptom, including the missing redirect.

The user also tied this to **bug #1** (sign-in page is "very skinny / all crammed together"). Since the working proxy will now actually route people to `/login`, we fix that page's spacing in the same pass.

## Changes

### 1. Move the proxy into `src/` (the actual fix)

- Move `web/proxy.ts` → `web/src/proxy.ts`. **Content is unchanged** — the `@/lib/supabase/proxy-session` import uses the `@/ → src/` alias, which still resolves; the `config.matcher` and redirect logic stay as-is.
- Delete the old `web/proxy.ts`.
- No change needed to `createProject` itself — once the proxy runs, unauthenticated users are redirected before they reach the form. The action's `getUser()` check stays as a correct defensive backstop.

Critical files:
- `web/proxy.ts` (move out)
- `web/src/proxy.ts` (new location)

### 2. Fix sign-in / sign-up page spacing (bug #1)

The auth card is currently `max-w-sm` (384px) with tight `gap-4` field rhythm — narrow and cramped against DESIGN.md's editorial, generous-whitespace intent (32px card padding, breathing room between elements). Widen and loosen, grounded in DESIGN.md's spacing tokens:

- `web/src/components/layout/AuthShell.tsx`: widen card `max-w-sm` → `max-w-md` (448px); increase header rhythm (`mb-6` → `mb-8`, title→subtitle `mt-1` → `mt-2`); keep `p-8` (32px = `spacing.xl`, on-spec) — bump to `p-10` only if it still reads tight after visual check.
- `web/src/components/features/auth/LoginForm.tsx` and `SignupForm.tsx`: loosen form rhythm `gap-4` → `gap-5`; label↔input `gap-1.5` → `gap-2`; give the submit button a bit more separation.

All values pulled from the DESIGN.md spacing scale (`xs` 8 · `sm` 12 · `md` 16 · `lg` 24 · `xl` 32). Final values tuned against a live screenshot (see Verification) so the page matches the warm, editorial pacing rather than a stock SaaS form.

### 3. Docs (required by CLAUDE.md)

- `context/log.md`: add a newest-first entry describing the proxy relocation (root-cause: src-dir proxy placement) and the auth-page spacing fix.
- `context/bug-corrections.md`: mark bug #1 resolved.
- No `decisions.md` or `deferredwork.md` change needed (this is a bug fix, not an architectural decision or a deferred dependency).

## Verification

1. **Proxy runs / redirect works:** From a signed-out state (clear cookies or use a private window), `npm run dev` in `web/`, visit `/dashboard` and `/project/new` directly → should now **redirect to `/login`** (previously rendered without redirect). This is the proof the proxy is being picked up.
2. **Create-project flow:** Sign in, go to **New project**, enter a research question, submit → should create the project and land on `/project/<id>/plan` with **no "Not authenticated" error**. Confirm a row in the `projects` table (RLS-scoped to the user).
3. **Session refresh:** Confirm `getCurrentUser()` keeps the TopNav showing the signed-in email across navigations (proxy refreshes the token).
4. **Spacing (bug #1):** Load `/login` and `/signup` and screenshot; confirm the card is wider and fields have comfortable, editorial spacing consistent with DESIGN.md. Run `npx tsc --noEmit` for type safety.
