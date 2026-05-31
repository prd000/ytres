-- Enable pgvector for 1536-dim embeddings (Phase 4) and pgcrypto for gen_random_uuid().
create extension if not exists "vector" with schema "public";
create extension if not exists "pgcrypto" with schema "public";
