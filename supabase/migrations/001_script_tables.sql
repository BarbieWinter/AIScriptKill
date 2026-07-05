-- 001_script_tables: 剧本包结构表
-- 所有剧本包共享此Schema，按 script_id 分区
-- 参考：SCRIPT_PACKAGE_SCHEMA.md

-- 剧本包主表
CREATE TABLE script_packages (
    id TEXT PRIMARY KEY,             -- 唯一标识，如 "snow-village"
    name TEXT NOT NULL,               -- 展示名
    version TEXT NOT NULL DEFAULT '1.0.0',
    config JSONB NOT NULL DEFAULT '{}', -- package.yml 完整内容
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'importing', 'published', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 阶段定义
CREATE TABLE script_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL,           -- 如 "act1_investigation"
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    definition JSONB NOT NULL,        -- stage.yml 完整内容
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, stage_id)
);

-- 角色定义
CREATE TABLE script_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    character_id TEXT NOT NULL,       -- 如 "wangdada"
    name TEXT NOT NULL,
    definition JSONB NOT NULL,        -- character.yml 完整内容
    is_playable BOOLEAN NOT NULL DEFAULT true,
    is_dm_alter_ego BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, character_id)
);

-- 线索定义
CREATE TABLE script_clues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    clue_id TEXT NOT NULL,
    name TEXT NOT NULL,
    round_id TEXT NOT NULL,           -- 所属轮次
    image_url TEXT,
    description TEXT NOT NULL,
    is_key BOOLEAN NOT NULL DEFAULT false,
    importance INTEGER NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    metadata JSONB NOT NULL DEFAULT '{}', -- stage_visible, visibility, related_scene, related_characters
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, clue_id)
);

-- 证物定义
CREATE TABLE script_evidences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    name TEXT NOT NULL,
    image_url TEXT,
    description_surface TEXT NOT NULL,
    description_deep TEXT,
    type TEXT NOT NULL DEFAULT 'evidence'
        CHECK (type IN ('key_evidence', 'evidence', 'prop', 'skill_card')),
    metadata JSONB NOT NULL DEFAULT '{}', -- discovery条件, npc_reactions, interactions
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, evidence_id)
);

-- 场景定义
CREATE TABLE script_scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    scene_id TEXT NOT NULL,
    name TEXT NOT NULL,
    background_url TEXT,
    definition JSONB NOT NULL DEFAULT '{}', -- hotspots, ambient
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, scene_id)
);

-- 多媒体资源
CREATE TABLE script_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('bgm', 'story', 'sfx', 'voice', 'image', 'video')),
    file_url TEXT NOT NULL,
    subtitle_url TEXT,
    duration_sec REAL,
    metadata JSONB NOT NULL DEFAULT '{}', -- volume, loop, fade_in, skip_allowed, trigger_on
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_id, asset_id)
);

-- 索引
CREATE INDEX idx_script_stages_order ON script_stages(script_id, sort_order);
CREATE INDEX idx_script_clues_round ON script_clues(script_id, round_id);
CREATE INDEX idx_script_characters_playable ON script_characters(script_id, is_playable);
