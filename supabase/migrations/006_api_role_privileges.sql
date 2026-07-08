-- 006_api_role_privileges: Supabase API 角色权限
-- RLS 决定哪些行可见，GRANT 决定 PostgREST 角色能否访问这些表。

-- ── Schema 使用权限 ──

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;


-- ── 服务端维护权限 ──

GRANT ALL PRIVILEGES ON TABLE
    public.script_packages,
    public.script_stages,
    public.script_characters,
    public.script_clues,
    public.script_evidences,
    public.script_scenes,
    public.script_media,
    public.script_knowledge,
    public.game_sessions,
    public.session_checkpoints,
    public.chat_messages,
    public.session_discoveries,
    public.final_submissions,
    public.reviews
TO service_role;


-- ── 前端公开剧本列表 ──

CREATE POLICY "public_see_published_packages" ON script_packages
    FOR SELECT
    TO anon, authenticated
    USING (status = 'published');

GRANT SELECT ON TABLE public.script_packages TO anon, authenticated;


-- ── 登录玩家会话访问入口 ──

GRANT SELECT ON TABLE
    public.script_clues,
    public.script_evidences,
    public.script_scenes,
    public.chat_messages,
    public.session_checkpoints,
    public.session_discoveries,
    public.final_submissions,
    public.reviews
TO authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.game_sessions TO authenticated;
