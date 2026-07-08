-- 004_rls_policies: 行级安全策略
-- 防剧透核心：默认锁定 public schema 表，只开放玩家自己的会话数据和已解锁内容。

-- ── 剧本结构表 RLS 开关 ──

ALTER TABLE script_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_characters ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_clues ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_evidences ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_knowledge ENABLE ROW LEVEL SECURITY;


-- ── 运行时表 RLS 开关 ──

ALTER TABLE game_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_discoveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE final_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;


-- ── 服务端全权限 ──

CREATE POLICY "service_role_full_access" ON script_packages
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_stages
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_characters
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_clues
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_evidences
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_scenes
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_media
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON script_knowledge
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON game_sessions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON session_checkpoints
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON chat_messages
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON session_discoveries
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON final_submissions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "service_role_full_access" ON reviews
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- ── 玩家剧本内容读取 ──

CREATE POLICY "players_see_unlocked_clues" ON script_clues
    FOR SELECT
    TO authenticated
    USING (
        metadata->>'stage_visible' <= current_setting('app.current_stage', true)
        AND (
            metadata->>'visibility' = 'public'
            OR metadata->>'character_id' = current_setting('app.player_character', true)
        )
    );

CREATE POLICY "players_see_visible_evidences" ON script_evidences
    FOR SELECT
    TO authenticated
    USING (
        metadata->>'stage_visible' <= current_setting('app.current_stage', true)
    );

CREATE POLICY "players_see_open_scenes" ON script_scenes
    FOR SELECT
    TO authenticated
    USING (
        definition->'available_in_stages' ? current_setting('app.current_stage', true)
    );


-- ── 玩家会话数据读取 ──

CREATE POLICY "players_own_sessions" ON game_sessions
    FOR ALL
    TO authenticated
    USING (player_id = auth.uid())
    WITH CHECK (player_id = auth.uid());

CREATE POLICY "players_see_own_checkpoints" ON session_checkpoints
    FOR SELECT
    TO authenticated
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

CREATE POLICY "players_see_own_messages" ON chat_messages
    FOR SELECT
    TO authenticated
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

CREATE POLICY "players_see_own_discoveries" ON session_discoveries
    FOR SELECT
    TO authenticated
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

CREATE POLICY "players_see_own_submissions" ON final_submissions
    FOR SELECT
    TO authenticated
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

CREATE POLICY "players_see_own_reviews" ON reviews
    FOR SELECT
    TO authenticated
    USING (
        session_id IN (
            SELECT id FROM game_sessions WHERE player_id = auth.uid()
        )
    );

-- 注意：script_knowledge 表不由玩家直接查询。
-- RAG 服务端使用 service_role 检索，并在应用层注入当前阶段与角色上下文。
