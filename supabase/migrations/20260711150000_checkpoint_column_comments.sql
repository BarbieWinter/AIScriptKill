-- 检查点持久化已改为 LangGraph 版本化信封；通过前向迁移修正文档，
-- 保留已部署迁移的不可变历史。
COMMENT ON COLUMN public.session_checkpoints.thread_ts IS
    'LangGraph 逻辑检查点 ID；该值不是数据库时间戳。';
COMMENT ON COLUMN public.session_checkpoints.parent_ts IS
    '父级 LangGraph 逻辑检查点 ID；根检查点为空。';
COMMENT ON COLUMN public.session_checkpoints.state IS
    '版本化检查点信封，包含类型化 checkpoint、metadata 和兼容旧数据的 pending_writes。';
