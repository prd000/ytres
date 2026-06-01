-- Phase 4/5: Add social_media to the source_tier enum.
--
-- ADD VALUE runs in its own file because ALTER TYPE ... ADD VALUE cannot
-- be used within a transaction that also references the new value in the
-- same statement. Isolating it here is the safest migration pattern.

alter type source_tier add value if not exists 'social_media';
