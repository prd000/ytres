# Phase 0 Implementation Plan — `ytres` Navigable Frontend Shell

## Context

`ytres` is a greenfield v2 of an AI-Powered Research Pipeline. The repo today contains **only** `context/` docs and `CLAUDE.md` — zero application code. Per the PRD's "Module Development Order", the build is deliberately front-loaded with **Phase 0: a navigable, QA-able Next.js frontend shell** so the experience can be evaluated from day one and every later UI feature wires into a real shell instead of being built blind.

Phase 0 ships a clickable product: every route renders against **typed mock data** (no backend, no real auth), with the `DESIGN.md` token system applied. The architecture deliberately isolates a single **data-access seam** so Phases 1/2/7 can swap mock reads for real Supabase/REST/Realtime calls without restructuring components — directly honoring the PRD's "browser is a pure projection of database state" principle and the two-plane model.

**Decisions confirmed with the user (2026-05-29):**
1. **Repo layout:** Next.js app lives in `ytres/web/` (leaving room for `ytres/api/` + `ytres/worker/` later — matches Render's separate-services model). → add to `decisions.md`.
2. **Components:** hand-rolled primitives against DESIGN.md tokens + **Radix headless** for behavior only (Tabs a11y, mobile nav dialog). No shadcn/ui base — the cream/coral/serif/shadow-rare brand fights generic library defaults.
3. **Mock depth:** lightweight in-memory interactivity (tab switching, chat composer typing, source-selection toggles, approve/regenerate UI states). Nothing persists.

---

## 1. Tooling & Setup

- **Next.js (App Router)** + **TypeScript (strict)** + **`src/` dir**, scaffolded into `ytres/web/`.
  - App Router is chosen because the project shell is a nested-layout problem: persistent project chrome (header + tab nav, later the Supabase Realtime channel) stays mounted while tab content swaps. `project/[id]/layout.tsx` gives this for free.
- **Tailwind v4** (CSS-first `@theme`) — lets `DESIGN.md` map **1:1** into CSS custom properties with no JS-config indirection (satisfies CLAUDE.md "tokens centralized, not inline hex").
- **`next/font/google`** for the substitute typefaces (Copernicus/StyreneB are licensed/unavailable — already acknowledged in DESIGN.md "Known Gaps"):
  - Serif display → **Cormorant Garamond** (DESIGN.md's named closest approximation), weight 500.
  - Humanist sans → **Inter** (DESIGN.md's named StyreneB substitute).
  - Mono → **JetBrains Mono**.
- **Supporting libs:** `@radix-ui/react-tabs`, `@radix-ui/react-dialog` (mobile nav sheet), `class-variance-authority` + `tailwind-merge` (variant management), `react-markdown` (Report preview). ESLint + Prettier.
- Package manager: `npm` (default; `pnpm` acceptable).

---

## 2. Directory Structure (under `ytres/web/`)

```
web/
├─ src/
│  ├─ app/
│  │  ├─ layout.tsx                 # root: fonts, <body> canvas bg
│  │  ├─ globals.css                # Tailwind @import + @theme token block (styling source of truth)
│  │  ├─ page.tsx                   # redirect → /dashboard
│  │  ├─ (auth)/                    # route group: minimal centered-card chrome
│  │  │  ├─ layout.tsx              # AuthShell (cream canvas, centered card, spike-mark)
│  │  │  ├─ login/page.tsx
│  │  │  └─ signup/page.tsx
│  │  └─ (app)/                     # route group: authed app chrome (TopNav + Footer)
│  │     ├─ layout.tsx
│  │     ├─ dashboard/page.tsx
│  │     └─ project/[id]/
│  │        ├─ layout.tsx           # PROJECT SHELL: header + ProjectTabNav (persistent) — Phase 7 Realtime seam
│  │        ├─ page.tsx             # redirect → ./plan
│  │        ├─ plan/page.tsx
│  │        ├─ research/page.tsx
│  │        ├─ sources/page.tsx
│  │        ├─ chat/page.tsx
│  │        └─ report/page.tsx
│  ├─ components/
│  │  ├─ ui/                        # design-system primitives (1:1 with DESIGN.md components:)
│  │  ├─ layout/                    # TopNav, Footer, AuthShell, ProjectShellHeader, ProjectTabNav, PageContainer, Surface
│  │  └─ features/{auth,dashboard,plan,research,sources,chat,report}/
│  └─ lib/
│     ├─ data/
│     │  ├─ types.ts                # domain types mirroring PRD data model (reused verbatim by real client later)
│     │  ├─ fixtures.ts             # the typed mock dataset
│     │  └─ client.ts              # async data-access fns — THE swappable mock→API seam
│     ├─ design/tokens.ts           # TS-side maps (status→color) that can't be pure CSS
│     └─ utils.ts                   # cn() helper, date formatting
├─ public/brand/spike-mark.svg      # placeholder radial-spike glyph
├─ next.config.ts · tsconfig.json · package.json · .env.example
```

---

## 3. Design Tokens (`globals.css` `@theme`)

Copy DESIGN.md front-matter **verbatim** into a Tailwind v4 `@theme` block as CSS custom properties (Tailwind auto-generates utilities):
- **Colors:** `--color-primary:#cc785c`, `--color-primary-active:#a9583e`, `--color-canvas:#faf9f5`, `--color-surface-soft:#f5f0e8`, `--color-surface-card:#efe9de`, `--color-surface-dark:#181715`, `--color-surface-dark-elevated:#252320`, `--color-ink:#141413`, `--color-body:#3d3d3a`, `--color-muted:#6c6a64`, `--color-hairline:#e6dfd8`, `--color-success:#5db872`, `--color-warning:#d4a017`, `--color-error:#c64545`, `--color-accent-teal:#5db8a6`, `--color-accent-amber:#e8a55a` (+ remaining).
- **Radius:** xs4 sm6 md8 lg12 xl16 pill. **Spacing:** xxs4 xs8 sm12 md16 lg24 xl32 xxl48 section96.
- **Fonts:** bind `--font-display / --font-sans / --font-mono` to the `next/font` CSS variables.
- **Typography scale:** define `.text-display-xl … .text-display-sm` (serif, weight 400, **negative letter-spacing — non-negotiable**) and `.text-title-* / .text-body-* / .text-caption*` (sans) as composite utility classes so size+weight+line-height+tracking always travel together.

`src/lib/design/tokens.ts` holds `STATUS_META: Record<ProjectStatus, { label, toneClass }>` (e.g. complete→success, researching→accent-teal, planning→warning, cancelled→muted, draft→hairline) driving `StatusPill`.

---

## 4. Component Inventory

**Primitives — `components/ui/` (1:1 with DESIGN.md `components:`):**
`Button` (variants: primary/secondary/secondaryOnDark/text/icon; active→primary-active, disabled→primary-disabled, cva-driven) · `TextLink` (coral) · `Card`/`Surface` (surface prop: card/dark/coral/canvas-bordered — encodes alternating-band rhythm) · `Input`/`Textarea` (coral 15%-alpha focus ring, hairline border) · `Badge` (pill/coral) · `StatusPill` (status enum → semantic color) · `ScorePill`/`ScoreBar` (1–5 dim scores, success/warning/error thresholds) · `Tabs` (Radix, token-styled) · `Callout` (full-bleed coral) · `SpikeMark` (inline SVG brand glyph).

**Layout — `components/layout/`:** `TopNav` (64px cream, spike-mark + "ytres" wordmark, links, sign-in / user menu, mobile hamburger → full-screen cream Radix Dialog sheet) · `Footer` (dark navy, never inverts) · `AuthShell` · `ProjectShellHeader` (serif title, research-question subtitle, StatusPill, Cancel action) · `ProjectTabNav` (`"use client"`, `usePathname()` for active state, `next/link`, category-tab tokens) · `PageContainer` (max-1200px, section spacing).

**Feature composites — `components/features/<screen>/`:**
- **auth:** `LoginForm`, `SignupForm` (presentational → router push to `/dashboard`).
- **dashboard:** `ProjectList`, `ProjectCard` (title, StatusPill, relative last-updated), `NewProjectButton`, `EmptyState`.
- **plan:** `PlanHeader`, `SubtopicCard` (title + objective + tier-pref badges + status), `GlobalSourceTierSettings`, `PlanActions` (Approve / Regenerate-with-feedback textarea — in-memory state).
- **research:** `SubtopicProgressCard` (latest worker_activity line, sources-stored count, status), `WorkerActivityFeed`, `WhyNothingReport` callout.
- **sources:** `SourcesBySubtopic` (grouped/accordion), `SourceCard` (key takeaway, 4 ScorePills, tier Badge, URL TextLink), `SourceTierFilter`.
- **chat:** `ChatThread`, `ChatMessage` (inline `Citation` chips → sources), `ChatComposer` (in-memory append), `SpawnResearchPrompt` callout (low-confidence "offer to research" state).
- **report:** `SourceSelector` (checkbox list + 25-cap counter), `AutoDraftToggle`, `ReportPreview` (`react-markdown`), `ReportActions` (Download .md wired client-side; **PDF stubbed/disabled → deferred-work**).

---

## 5. Routing Map

| Route | File | Renders |
|---|---|---|
| `/` | `app/page.tsx` | redirect → `/dashboard` |
| `/login`, `/signup` | `(auth)/…/page.tsx` | forms in AuthShell |
| `/dashboard` | `(app)/dashboard/page.tsx` | ProjectList |
| `/project/[id]` | `…/project/[id]/page.tsx` | redirect → `/plan` |
| `/project/[id]/{plan,research,sources,chat,report}` | nested tab pages | each tab |

**Persistent shell:** `(app)/layout.tsx` wraps TopNav/PageContainer/Footer. `project/[id]/layout.tsx` (server component, `await getProject(id)`) renders `ProjectShellHeader` + `ProjectTabNav` + `{children}` and **stays mounted across tab switches** — Next swaps only `page.tsx`. This is the exact seam where Phase 7 mounts the Supabase Realtime channel. `(auth)` vs `(app)` route groups give two chromes with no extra URL segments.

---

## 6. Mock Data Architecture (the swappable seam)

- **`types.ts`** — TS types mirroring the PRD data model: `ProjectStatus` (`draft|planning|researching|complete|cancelled`), `SourceTier`, `SubtopicStatus`; `Project` {id, researchQuestion, status, sourceTierSettings, ownerId, lastUpdated, createdAt}; `Subtopic` {id, projectId, title, informationObjective, sourceTierPreferences, status}; `Source` {id, projectId, subtopicIds, url, fullText, tier, keyTakeaway, scores{relevance,credibility,uniqueness,actionability}}; `WorkerActivity` {subtopicId, latestActivity, sourcesStored, status}; `ChatMessage` {id, projectId, role, content, citations[]}; `Report` {id, projectId, markdown, sourceRefs}. Written to be reused **verbatim** by the future real client.
- **`fixtures.ts`** — one cohesive dataset: ~4–6 projects covering **every** status (so all StatusPill colors + shell states render). At least one "researching" and one "complete" project carry a full set of subtopics, sources (incl. one mixed-quality score set), worker_activity (incl. one "why nothing" subtopic), a chat thread with inline citations, and a sample markdown report — so every tab is visually complete.
- **`client.ts`** — **the only module screens import for data.** Async fns: `getProjects`, `getProject(id)`, `getSubtopics(projectId)`, `getSources(projectId)`, `getWorkerActivity(projectId)`, `getChatMessages(projectId)`, `getReport(projectId)`. Async signatures so they become `fetch`/Supabase calls later with zero call-site changes. Server components `await` directly; interactive bits hold local React state only.

---

## 7. Build Order

1. **Scaffold + tokens:** `create-next-app` into `web/` (TS, App Router, src, Tailwind v4); install deps; author `globals.css` `@theme` from DESIGN.md; wire `next/font`; add typography utility classes.
2. **Primitives:** build `components/ui/*`, verify each variant against DESIGN.md specs.
3. **Data layer:** `types.ts` → `fixtures.ts` → `client.ts` → `design/tokens.ts`.
4. **Layouts & nav:** root, `(auth)` + AuthShell, `(app)` (TopNav/Footer), project `[id]` shell (header + ProjectTabNav). Verify persistent-shell + tab-swap with placeholder bodies.
5. **Auth screens** → push to `/dashboard`.
6. **Dashboard** (ProjectList/ProjectCard/EmptyState).
7. **Project tabs, one at a time:** Plan → Research → Sources → Chat → Report.
8. **Polish:** responsive breakpoints (768/1024/1440), surface-rhythm audit (no two consecutive same surfaces), mobile hamburger sheet, empty/edge states.
9. **Docs:** update `context/log.md`, populate `context/map.md` (currently empty), append `context/deferredwork.md` (font substitution, PDF-export stub, every mocked surface), and `context/decisions.md` (web/ subfolder layout, hand-rolled + Radix, mock-client seam).

---

## 8. Verification

- **Navigation:** `npm run dev`; click every route; confirm `/`→dashboard, bare `/project/[id]`→`/plan`, and tab switches swap content **without** the project header/tab bar remounting (proves the Phase 7 seam). Visit a project of each status to confirm all StatusPill colors.
- **Design fidelity:** spot-check computed styles vs tokens (coral `#cc785c`, canvas `#faf9f5`, serif headlines with negative tracking, shadows essentially absent); verify alternating cream→cream-card→dark rhythm; **grep `components/` for inline `#` hex → must be zero** (the CLAUDE.md "1:1 to DESIGN.md" guardrail).
- **Responsive:** DevTools at <768 / 768–1024 / 1024–1440 / >1440 — hamburger + cream sheet on mobile, tab nav usable on narrow, card grids reflow, max-width caps at 1200px.
- **Build health:** `npm run build` (catches server/client boundary + TS fixture errors), `npm run lint`, `tsc --noEmit`.
- **Swap-readiness:** grep confirms **no component imports `fixtures.ts` directly — only `client.ts`** (proves the mock layer is the sole thing Phases 1/2 replace).

---

## Deferred-work items to log (per CLAUDE.md)
1. Copernicus/StyreneB → Cormorant Garamond/Inter font substitution (pre-acknowledged in DESIGN.md Known Gaps).
2. Report-tab **PDF export** stubbed/disabled in Phase 0 (real export = later phase); `.md` download wired client-side now.
3. All Phase 0 screens render against mock fixtures — every mocked surface to be swapped for real data in Phases 1/2/7.
