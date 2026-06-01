-- Phase 4: Hybrid vector + keyword search function with Reciprocal Rank Fusion.
--
-- Used by both the Phase 6 worker pipeline (via asyncpg) and the Phase 9 RAG
-- chatbot. A single canonical implementation eliminates drift between callers.
--
-- Not SECURITY DEFINER: the worker bypasses RLS; an authenticated wrapper
-- for the RAG chatbot is deferred to Phase 9.

create or replace function match_chunks(
    p_project_id      uuid,
    p_query_embedding vector(1536),
    p_query_text      text,
    p_match_count     int default 12
)
returns table (
    id          uuid,
    source_id   uuid,
    project_id  uuid,
    chunk_index integer,
    content     text,
    token_count integer,
    score       float8
)
language sql stable as $$
    with vector_ranked as (
        select
            sc.id,
            sc.source_id,
            sc.project_id,
            sc.chunk_index,
            sc.content,
            sc.token_count,
            row_number() over (
                order by sc.embedding <=> p_query_embedding
            ) as rank
        from source_chunks sc
        where sc.project_id = p_project_id
          and sc.embedding is not null
    ),
    keyword_ranked as (
        select
            sc.id,
            row_number() over (
                order by ts_rank(
                    to_tsvector('english', sc.content),
                    plainto_tsquery('english', p_query_text)
                ) desc
            ) as rank
        from source_chunks sc
        where sc.project_id = p_project_id
          and to_tsvector('english', sc.content)
              @@ plainto_tsquery('english', p_query_text)
    ),
    fused as (
        select
            coalesce(v.id, k.id)                                 as id,
            coalesce(1.0 / (60.0 + v.rank), 0.0)
            + coalesce(1.0 / (60.0 + k.rank), 0.0)              as score
        from vector_ranked v
        full outer join keyword_ranked k on v.id = k.id
    )
    select
        sc.id,
        sc.source_id,
        sc.project_id,
        sc.chunk_index,
        sc.content,
        sc.token_count,
        f.score
    from fused f
    join source_chunks sc on sc.id = f.id
    order by f.score desc
    limit p_match_count;
$$;
