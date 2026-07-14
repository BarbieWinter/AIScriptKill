-- 20260713010000_character_chapter_discoveries
-- 将人物章节授权/阅读状态纳入会话发现表，并保持浏览器角色不可直接访问。

ALTER TABLE public.session_discoveries
    DROP CONSTRAINT IF EXISTS session_discoveries_entity_type_check;

ALTER TABLE public.session_discoveries
    ADD CONSTRAINT session_discoveries_entity_type_check
    CHECK (entity_type IN ('clue', 'evidence', 'scene', 'character_chapter'));

COMMENT ON TABLE public.session_discoveries IS
    '会话内内容授权和查看进度；character_chapter 使用 unlocked/viewed 表示已发放/已阅读。';

COMMENT ON COLUMN public.session_discoveries.status IS
    '单调进度：unlocked < viewed < deep_viewed < used_in_final；重复写入不得降级。';

REVOKE ALL PRIVILEGES ON TABLE public.session_discoveries
FROM anon, authenticated;

GRANT ALL PRIVILEGES ON TABLE public.session_discoveries
TO service_role;
