-- 003_vector_tables: RAG 向量检索表
-- 剧本包知识的分块+向量化存储

CREATE EXTENSION IF NOT EXISTS vector;

-- 剧本知识向量表
CREATE TABLE script_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL           -- 'character_knowledge' | 'clue' | 'script_context' | 'evidence'
        CHECK (source_type IN ('character_knowledge', 'clue', 'script_context', 'evidence')),
    source_id TEXT NOT NULL,            -- 源记录ID
    chunk_index INTEGER NOT NULL,       -- 切片序号
    chunk_text TEXT NOT NULL,           -- 切片文本
    embedding VECTOR(1536),             -- 嵌入向量
    metadata JSONB NOT NULL DEFAULT '{}',
    -- 权限过滤字段（防剧透核心）：
    --  metadata->>'stage_visible'    这段文本在哪个stage后可见
    --  metadata->>'character_id'     这段文本属于哪个角色（'public'=公开）
    --  metadata->>'visibility'       'public' | 'character_only' | 'dm_only'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_script_knowledge_chunk
        UNIQUE (script_id, source_type, source_id, chunk_index)
);

-- 向量索引 (IVFFlat)
CREATE INDEX idx_knowledge_embedding ON script_knowledge
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 按剧本+可见性检索的索引
CREATE INDEX idx_knowledge_permissions ON script_knowledge(script_id, source_type);

CREATE INDEX idx_knowledge_visibility ON script_knowledge(
    script_id,
    (COALESCE((metadata->>'stage_order')::int, 0)),
    (metadata->>'visibility'),
    (metadata->>'character_id')
);
