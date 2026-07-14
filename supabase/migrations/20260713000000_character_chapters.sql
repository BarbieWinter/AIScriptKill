-- character_chapters: 角色专属 Markdown 章节与其发布元数据
-- 章节正文不直接授权给客户端；后续由服务端结合会话角色和解锁状态读取。

CREATE TABLE public.script_character_chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES public.script_packages(id) ON DELETE CASCADE,
    chapter_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    title TEXT NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility = 'character_only'),
    release JSONB NOT NULL,
    stage_min TEXT,
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, chapter_id),
    FOREIGN KEY (script_id, character_id)
        REFERENCES public.script_characters(script_id, character_id)
        ON DELETE CASCADE,
    FOREIGN KEY (script_id, stage_min)
        REFERENCES public.script_stages(script_id, stage_id)
);

CREATE INDEX idx_script_character_chapters_character_order
    ON public.script_character_chapters(script_id, character_id, sort_order);

ALTER TABLE public.script_character_chapters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.script_character_chapters
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.script_character_chapters
FROM anon, authenticated;

GRANT ALL PRIVILEGES ON TABLE public.script_character_chapters
TO service_role;

COMMENT ON TABLE public.script_character_chapters IS '角色专属 Markdown 章节表，仅服务端可按角色和会话解锁状态读取。';
COMMENT ON COLUMN public.script_character_chapters.id IS '人物章节记录内部 UUID。';
COMMENT ON COLUMN public.script_character_chapters.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_character_chapters.chapter_id IS '剧本包内全局唯一的人物章节 ID。';
COMMENT ON COLUMN public.script_character_chapters.character_id IS '拥有该私有章节的角色 ID。';
COMMENT ON COLUMN public.script_character_chapters.sort_order IS '该角色人物章节的展示顺序。';
COMMENT ON COLUMN public.script_character_chapters.title IS '人物章节展示标题。';
COMMENT ON COLUMN public.script_character_chapters.visibility IS '固定为 character_only，禁止直接公开读取。';
COMMENT ON COLUMN public.script_character_chapters.release IS '确定性章节发布声明，原样保留 frontmatter 映射。';
COMMENT ON COLUMN public.script_character_chapters.stage_min IS '章节关联的可选最早阶段 ID，不替代独立章节授权。';
COMMENT ON COLUMN public.script_character_chapters.content IS '人物章节 Markdown 正文，不自动进入普通 RAG 索引。';
COMMENT ON COLUMN public.script_character_chapters.created_at IS '人物章节记录创建时间。';
COMMENT ON COLUMN public.script_character_chapters.updated_at IS '人物章节记录最后更新时间。';
COMMENT ON POLICY "service_role_full_access" ON public.script_character_chapters IS '仅服务端 service_role 可维护和读取人物章节。';
