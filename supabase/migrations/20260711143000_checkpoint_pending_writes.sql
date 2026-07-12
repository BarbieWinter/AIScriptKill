-- 待处理写入可能先于对应检查点记录到达，因此直接引用游戏会话，
-- 并使用逻辑检查点 ID，而不是指向 session_checkpoints 的外键。
CREATE TABLE public.session_checkpoint_writes (
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    write_idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, checkpoint_id, task_id, write_idx)
);

ALTER TABLE public.session_checkpoint_writes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.session_checkpoint_writes
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

GRANT ALL PRIVILEGES ON TABLE public.session_checkpoint_writes TO service_role;
REVOKE ALL PRIVILEGES ON TABLE public.session_checkpoint_writes FROM anon, authenticated;

COMMENT ON TABLE public.session_checkpoint_writes IS
    'LangGraph 待处理写入独立存储，以保证跨进程幂等性。';
COMMENT ON COLUMN public.session_checkpoint_writes.session_id IS
    '所属游戏会话及 LangGraph 线程标识符。';
COMMENT ON COLUMN public.session_checkpoint_writes.checkpoint_id IS
    '逻辑检查点标识符；对应检查点记录可能稍后插入。';
COMMENT ON COLUMN public.session_checkpoint_writes.task_id IS
    '产生此待处理写入的 LangGraph 任务。';
COMMENT ON COLUMN public.session_checkpoint_writes.write_idx IS
    '用于幂等冲突处理的稳定通道写入索引。';
COMMENT ON COLUMN public.session_checkpoint_writes.channel IS
    '接收序列化值的 LangGraph 通道。';
COMMENT ON COLUMN public.session_checkpoint_writes.value IS
    '由严格检查点编解码器编码的受限类型化值。';
COMMENT ON COLUMN public.session_checkpoint_writes.created_at IS
    '待处理写入记录首次插入时的数据库时间戳。';
COMMENT ON POLICY "service_role_full_access" ON public.session_checkpoint_writes IS
    '只有受信任的后端 service_role 连接可以访问检查点写入。';
