-- 20260713020000_rag_embedding_v4_1024: align pgvector storage with DashScope text-embedding-v4
-- Existing 1536-dimensional vectors cannot be cast to 1024 dimensions safely, so clear the
-- derived index rows and let package reindexing rebuild them with the configured provider.

DROP INDEX IF EXISTS public.idx_knowledge_embedding;

TRUNCATE TABLE public.script_knowledge;

ALTER TABLE public.script_knowledge
    ALTER COLUMN embedding TYPE vector(1024)
    USING NULL::vector(1024);

CREATE INDEX idx_knowledge_embedding ON public.script_knowledge
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON COLUMN public.script_knowledge.embedding IS
    'DashScope text-embedding-v4 的 1024 维文本嵌入向量。';
