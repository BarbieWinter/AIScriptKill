-- 002_runtime_tables: 游戏运行时表
-- 所有剧本包共享，不做分区

-- 游戏会话
CREATE TABLE game_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id TEXT NOT NULL REFERENCES script_packages(id),
    player_id UUID REFERENCES auth.users(id),
    player_character_id TEXT NOT NULL,
    state JSONB NOT NULL DEFAULT '{}',   -- GameState 快照
    status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'paused', 'completed', 'abandoned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 会话检查点（LangGraph Checkpoint 持久化）
CREATE TABLE session_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    thread_ts TEXT NOT NULL,             -- LangGraph 时间戳
    parent_ts TEXT,                      -- 父检查点
    state JSONB NOT NULL,                -- 完整 GameState
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 聊天消息
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('player', 'npc', 'dm', 'system')),
    character_id TEXT,                   -- NPC/DM 的 ID
    text TEXT NOT NULL,
    emotion TEXT,                        -- NPC情绪
    metadata JSONB NOT NULL DEFAULT '{}', -- 是否被Guard审查等
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 会话解锁记录（线索/证物）
CREATE TABLE session_discoveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('clue', 'evidence', 'scene')),
    entity_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unlocked'
        CHECK (status IN ('unlocked', 'viewed', 'deep_viewed', 'used_in_final')),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, entity_type, entity_id)
);

-- 最终推理提交
CREATE TABLE final_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    suspect TEXT NOT NULL,
    motive TEXT,
    key_evidences TEXT[] NOT NULL DEFAULT '{}',
    deduction TEXT,
    score INTEGER,
    result JSONB NOT NULL DEFAULT '{}',  -- 评分明细
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 复盘
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    max_score INTEGER NOT NULL DEFAULT 100,
    rating TEXT,                          -- S/A/B/C/D
    breakdown JSONB NOT NULL DEFAULT '{}', -- 各项得分明细
    truth_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX idx_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX idx_checkpoints_session ON session_checkpoints(session_id, created_at DESC);
CREATE INDEX idx_discoveries_session ON session_discoveries(session_id, entity_type);
CREATE INDEX idx_sessions_status ON game_sessions(status);
