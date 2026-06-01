-- Phase 4: Vector and full-text search indexes on source_chunks.
--
-- ivfflat note: index trains on existing data at CREATE time. Run
--   REINDEX INDEX CONCURRENTLY <index-name>
-- once substantial chunks exist for good recall. HNSW is the no-tuning
-- upgrade path when the pgvector version supports it.

-- Cosine-similarity index for pgvector ANN search
create index on source_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- GIN full-text index for keyword search (English dictionary)
create index on source_chunks using gin (to_tsvector('english', content));

-- btree index for project_id scoping (used in every query)
create index on source_chunks (project_id);
