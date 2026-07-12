-- 受保护的剧本内容和运行时状态通过 FastAPI 访问，SQL 由后端配置的服务端数据库角色执行。
-- 旧策略把 stage_visible 当字符串比较，使用的是字典序（例如 act10 会排在 act2 前），
-- 无法表达真实阶段顺序，也不能作为防剧透授权依据，因此客户端不再直接读取这些表。

REVOKE ALL PRIVILEGES ON TABLE
    public.script_packages,
    public.script_stages,
    public.script_characters,
    public.script_clues,
    public.script_evidences,
    public.script_scenes,
    public.script_media,
    public.script_knowledge,
    public.script_endings,
    public.script_dm_guides,
    public.game_sessions,
    public.session_checkpoints,
    public.chat_messages,
    public.session_discoveries,
    public.final_submissions,
    public.reviews
FROM anon, authenticated;

-- 剧本目录也只通过 FastAPI 的字段投影返回，避免 config 中的结局和未来阶段元数据泄露。
DROP POLICY IF EXISTS "public_see_published_packages" ON public.script_packages;

DROP POLICY IF EXISTS "players_see_unlocked_clues" ON public.script_clues;
DROP POLICY IF EXISTS "players_see_visible_evidences" ON public.script_evidences;
DROP POLICY IF EXISTS "players_see_open_scenes" ON public.script_scenes;
DROP POLICY IF EXISTS "players_own_sessions" ON public.game_sessions;
DROP POLICY IF EXISTS "players_see_own_checkpoints" ON public.session_checkpoints;
DROP POLICY IF EXISTS "players_see_own_messages" ON public.chat_messages;
DROP POLICY IF EXISTS "players_see_own_discoveries" ON public.session_discoveries;
DROP POLICY IF EXISTS "players_see_own_submissions" ON public.final_submissions;
DROP POLICY IF EXISTS "players_see_own_reviews" ON public.reviews;
