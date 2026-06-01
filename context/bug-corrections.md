# Bug Fixes
1. ~~Login page card is extremely narrow and unusable — the entire card, including inputs, labels, and buttons, is compressed into a very thin column. The layout needs a proper minimum width and the form elements need full-width sizing so the page is actually usable.~~ — **Done (2026-06-01):** Root cause was `AuthShell` centering with `flex flex-col items-center` and relying solely on `w-full` for the inner wrapper's width (non-stretch cross-axis collapses to content width). Fixed by dropping `items-center` (defaults to `stretch`) and adding `mx-auto` to the `w-full max-w-md` wrapper. Covers login + signup. See `log.md`.

# Major Features to add
