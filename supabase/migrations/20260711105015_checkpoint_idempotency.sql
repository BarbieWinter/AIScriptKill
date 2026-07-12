-- LangGraph 可能会在图步骤中断后重试同一检查点写入。
-- 数据库键必须与保存器的 upsert 键一致，确保重试时替换而非重复插入。
WITH ranked_checkpoint_retries AS (
    SELECT
        id,
        row_number() OVER (
            PARTITION BY session_id, thread_ts
            ORDER BY created_at DESC, id DESC
        ) AS retry_rank
    FROM public.session_checkpoints
)
DELETE FROM public.session_checkpoints
USING ranked_checkpoint_retries
WHERE session_checkpoints.id = ranked_checkpoint_retries.id
  AND ranked_checkpoint_retries.retry_rank > 1;

CREATE UNIQUE INDEX uq_session_checkpoints_session_thread_ts
    ON public.session_checkpoints(session_id, thread_ts);
