-- 005_runtime_persistence_indexes: 会话持久化查询补充索引
-- 让最终提交、复盘和玩家会话列表走索引，避免运行数据增长后退化成顺序扫描

CREATE INDEX IF NOT EXISTS idx_sessions_player_status_updated
    ON game_sessions(player_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_script_packages_status_updated
    ON script_packages(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_final_submissions_session
    ON final_submissions(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reviews_session
    ON reviews(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session_thread
    ON session_checkpoints(session_id, thread_ts, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_script_evidences_cards
    ON script_evidences(script_id, type);
