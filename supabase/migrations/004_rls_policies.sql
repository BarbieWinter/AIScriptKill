-- 004_rls_policies: 行级安全策略
-- 防剧透核心：玩家只能看到已解锁内容

-- ── script_clues 线索表 ──
ALTER TABLE script_clues ENABLE ROW LEVEL SECURITY;

-- 玩家只能看到当前stage已解锁的公开线索+自己的个人线索
CREATE POLICY "players_see_unlocked_clues" ON script_clues
    FOR SELECT
    USING (
        metadata->>'stage_visible' <= current_setting('app.current_stage', true)
        AND (
            metadata->>'visibility' = 'public'
            OR metadata->>'character_id' = current_setting('app.player_character', true)
        )
    );

-- ── script_evidences 证物表 ──
ALTER TABLE script_evidences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "players_see_visible_evidences" ON script_evidences
    FOR SELECT
    USING (
        metadata->>'stage_visible' <= current_setting('app.current_stage', true)
    );

-- ── script_scenes 场景表 ──
ALTER TABLE script_scenes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "players_see_open_scenes" ON script_scenes
    FOR SELECT
    USING (
        definition->>'available_in_stages' ? current_setting('app.current_stage', true)
    );

-- ── game_sessions 会话表 ──
ALTER TABLE game_sessions ENABLE ROW LEVEL SECURITY;

-- 玩家只能看到自己的会话
CREATE POLICY "players_own_sessions" ON game_sessions
    FOR ALL
    USING (player_id = auth.uid());

-- ── chat_messages 消息表 ──
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "players_see_own_messages" ON chat_messages
    FOR SELECT
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

-- ── 管理员全权限 ──
CREATE POLICY "admin_full_access" ON script_packages
    FOR ALL
    USING (auth.role() = 'service_role');

-- 注意：script_knowledge 表不由玩家直接查询
-- 通过 RAG 服务端检索，由 service_role 访问
