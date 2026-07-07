-- 008_package_import_resolution_tables: T-2.1 结局与 DM 私密资料入库
-- endings.yml 和 dm_guide/ 都由服务端导入并读取，避免泄露推理答案和主持人资料。

CREATE TABLE script_endings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    ending_id TEXT NOT NULL,
    name TEXT NOT NULL,
    condition JSONB NOT NULL DEFAULT '{}',
    on_trigger JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, ending_id)
);

CREATE TABLE script_dm_guides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    guide_key TEXT NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, guide_key)
);

CREATE INDEX idx_script_endings_script ON script_endings(script_id);
CREATE INDEX idx_script_dm_guides_script ON script_dm_guides(script_id);

ALTER TABLE script_endings ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_dm_guides ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON script_endings
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_dm_guides
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

GRANT ALL PRIVILEGES ON TABLE
    public.script_endings,
    public.script_dm_guides
TO service_role;

COMMENT ON TABLE public.script_endings IS '剧本结局定义表，保存 endings.yml 的触发条件、事件和展示元数据。';
COMMENT ON COLUMN public.script_endings.id IS '结局记录内部 UUID。';
COMMENT ON COLUMN public.script_endings.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_endings.ending_id IS '剧本包内稳定结局 ID。';
COMMENT ON COLUMN public.script_endings.name IS '结局展示名称。';
COMMENT ON COLUMN public.script_endings.condition IS '结局触发条件 DSL。';
COMMENT ON COLUMN public.script_endings.on_trigger IS '结局触发后的系统事件列表。';
COMMENT ON COLUMN public.script_endings.metadata IS 'endings.yml 中该结局的完整扩展元数据。';
COMMENT ON COLUMN public.script_endings.created_at IS '结局记录创建时间。';

COMMENT ON TABLE public.script_dm_guides IS 'DM 私密资料表，保存 dm_guide/ 下的真相、阶段笔记和主持提示，仅服务端可读。';
COMMENT ON COLUMN public.script_dm_guides.id IS 'DM 资料记录内部 UUID。';
COMMENT ON COLUMN public.script_dm_guides.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_dm_guides.guide_key IS 'dm_guide 文件名派生的资料键，如 truth、stage_notes。';
COMMENT ON COLUMN public.script_dm_guides.content IS 'dm_guide 单文件解析后的 JSON 内容。';
COMMENT ON COLUMN public.script_dm_guides.created_at IS 'DM 资料记录创建时间。';
COMMENT ON COLUMN public.script_dm_guides.updated_at IS 'DM 资料记录最后更新时间。';
COMMENT ON POLICY "service_role_full_access" ON public.script_endings IS '服务端 service_role 可维护和读取结局定义。';
COMMENT ON POLICY "service_role_full_access" ON public.script_dm_guides IS '服务端 service_role 可维护和读取 DM 私密资料。';
