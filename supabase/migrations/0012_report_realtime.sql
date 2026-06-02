-- Phase 10: publish the reports table to Supabase Realtime so INSERT events
-- reach open browser tabs without a manual refresh.
--
-- Note: apply via `supabase db push` or directly over SUPABASE_DB_URL.
-- Idempotent on re-apply (Postgres silently ignores adding an already-published
-- table to the publication).
alter publication supabase_realtime add table reports;
