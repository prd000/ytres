# Bug Fixes
1. ~~Generating a plan failed with `ValueError: dictionary update sequence element #0 has length 1; 2 is required` at `planner.py` `dict(ctx.job["payload"])`.~~ **FIXED 2026-06-01** — asyncpg returned the jsonb `payload` as a string; registered a json/jsonb type codec on the pool (`worker.db.register_json_codecs`) so jsonb decodes to dict. See log.md / decisions.md. *Still needs live `pytest worker/` + end-to-end `generate_plan` run to confirm (no local Docker/Supabase on the dev box).*

# Major Features to add
