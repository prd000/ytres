-- Phase 9: enable Realtime for chat_messages + add confidence column for spawn affordance.
--
-- 1. Publish chat_messages so INSERT events reach the open Chat tab (currently only
--    0002/0003/0012 added tables to the publication; chat_messages was missing).
-- 2. Add nullable confidence column on assistant rows: 'high'|'medium'|'low'.
--    NULL on user rows; the worker sets it when inserting the assistant reply.
--    The frontend renders a "Research this" spawn button when confidence = 'low'.
alter publication supabase_realtime add table chat_messages;
alter table chat_messages add column confidence text;
