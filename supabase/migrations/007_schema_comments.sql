-- 007_schema_comments: Phase 1 可验收数据字典
-- 统一补齐 public schema 的表、字段和 RLS policy 注释，方便 Supabase Studio 与审计脚本读取。

-- ── 剧本结构表 ──
COMMENT ON TABLE public.script_packages IS '剧本包主表，记录可导入、发布和归档的剧本包版本。';
COMMENT ON COLUMN public.script_packages.id IS '剧本包唯一 ID，作为所有剧本结构表的外键根。';
COMMENT ON COLUMN public.script_packages.name IS '剧本包面向玩家展示的名称。';
COMMENT ON COLUMN public.script_packages.version IS '剧本包语义化版本号。';
COMMENT ON COLUMN public.script_packages.config IS 'package.yml 解析后的完整 JSON 配置。';
COMMENT ON COLUMN public.script_packages.status IS '剧本包发布状态：draft/importing/published/archived。';
COMMENT ON COLUMN public.script_packages.created_at IS '剧本包记录创建时间。';
COMMENT ON COLUMN public.script_packages.updated_at IS '剧本包记录最后更新时间。';

COMMENT ON TABLE public.script_stages IS '剧本阶段定义表，描述序章、调查、对峙、复盘等阶段。';
COMMENT ON COLUMN public.script_stages.id IS '阶段记录内部 UUID。';
COMMENT ON COLUMN public.script_stages.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_stages.stage_id IS '剧本包内稳定阶段 ID。';
COMMENT ON COLUMN public.script_stages.name IS '阶段展示名称。';
COMMENT ON COLUMN public.script_stages.sort_order IS '阶段排序权重。';
COMMENT ON COLUMN public.script_stages.definition IS 'stage.yml 解析后的完整 JSON 定义。';
COMMENT ON COLUMN public.script_stages.created_at IS '阶段记录创建时间。';

COMMENT ON TABLE public.script_characters IS '剧本角色定义表，包含玩家角色、NPC 和 DM alter ego。';
COMMENT ON COLUMN public.script_characters.id IS '角色记录内部 UUID。';
COMMENT ON COLUMN public.script_characters.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_characters.character_id IS '剧本包内稳定角色 ID。';
COMMENT ON COLUMN public.script_characters.name IS '角色展示名称。';
COMMENT ON COLUMN public.script_characters.definition IS 'character.yml 解析后的完整 JSON 定义。';
COMMENT ON COLUMN public.script_characters.is_playable IS '该角色是否可由玩家选择。';
COMMENT ON COLUMN public.script_characters.is_dm_alter_ego IS '该角色是否为 DM/系统叙事代理。';
COMMENT ON COLUMN public.script_characters.sort_order IS '角色展示排序权重。';
COMMENT ON COLUMN public.script_characters.created_at IS '角色记录创建时间。';

COMMENT ON TABLE public.script_clues IS '剧本线索定义表，记录分阶段解锁的可调查信息。';
COMMENT ON COLUMN public.script_clues.id IS '线索记录内部 UUID。';
COMMENT ON COLUMN public.script_clues.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_clues.clue_id IS '剧本包内稳定线索 ID。';
COMMENT ON COLUMN public.script_clues.name IS '线索展示名称。';
COMMENT ON COLUMN public.script_clues.round_id IS '线索所属阶段或轮次 ID。';
COMMENT ON COLUMN public.script_clues.image_url IS '线索图片资源地址。';
COMMENT ON COLUMN public.script_clues.description IS '线索面向玩家展示的描述。';
COMMENT ON COLUMN public.script_clues.is_key IS '是否为关键线索。';
COMMENT ON COLUMN public.script_clues.importance IS '线索重要度，范围 1 到 5。';
COMMENT ON COLUMN public.script_clues.metadata IS '线索可见性、关联角色和场景等扩展元数据。';
COMMENT ON COLUMN public.script_clues.created_at IS '线索记录创建时间。';

COMMENT ON TABLE public.script_evidences IS '剧本证物定义表，记录可收集、出示和深挖的物品。';
COMMENT ON COLUMN public.script_evidences.id IS '证物记录内部 UUID。';
COMMENT ON COLUMN public.script_evidences.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_evidences.evidence_id IS '剧本包内稳定证物 ID。';
COMMENT ON COLUMN public.script_evidences.name IS '证物展示名称。';
COMMENT ON COLUMN public.script_evidences.image_url IS '证物图片资源地址。';
COMMENT ON COLUMN public.script_evidences.description_surface IS '证物初始展示描述。';
COMMENT ON COLUMN public.script_evidences.description_deep IS '证物深度调查后的描述。';
COMMENT ON COLUMN public.script_evidences.type IS '证物类型：key_evidence/evidence/prop/skill_card。';
COMMENT ON COLUMN public.script_evidences.metadata IS '证物发现条件、NPC 反应和交互扩展元数据。';
COMMENT ON COLUMN public.script_evidences.created_at IS '证物记录创建时间。';

COMMENT ON TABLE public.script_scenes IS '剧本场景定义表，描述可进入场景与热区配置。';
COMMENT ON COLUMN public.script_scenes.id IS '场景记录内部 UUID。';
COMMENT ON COLUMN public.script_scenes.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_scenes.scene_id IS '剧本包内稳定场景 ID。';
COMMENT ON COLUMN public.script_scenes.name IS '场景展示名称。';
COMMENT ON COLUMN public.script_scenes.background_url IS '场景背景图资源地址。';
COMMENT ON COLUMN public.script_scenes.definition IS '场景热区、氛围和可用阶段配置。';
COMMENT ON COLUMN public.script_scenes.created_at IS '场景记录创建时间。';

COMMENT ON TABLE public.script_media IS '剧本多媒体资源表，记录 BGM、音效、语音、图片和视频。';
COMMENT ON COLUMN public.script_media.id IS '媒体记录内部 UUID。';
COMMENT ON COLUMN public.script_media.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_media.asset_id IS '剧本包内稳定资源 ID。';
COMMENT ON COLUMN public.script_media.type IS '资源类型：bgm/story/sfx/voice/image/video。';
COMMENT ON COLUMN public.script_media.file_url IS '媒体文件地址。';
COMMENT ON COLUMN public.script_media.subtitle_url IS '字幕文件地址。';
COMMENT ON COLUMN public.script_media.duration_sec IS '媒体时长，单位秒。';
COMMENT ON COLUMN public.script_media.metadata IS '媒体触发条件、音量、循环和淡入淡出等元数据。';
COMMENT ON COLUMN public.script_media.created_at IS '媒体记录创建时间。';

COMMENT ON TABLE public.script_knowledge IS 'RAG 剧本知识向量表，只允许服务端检索并执行防剧透过滤。';
COMMENT ON COLUMN public.script_knowledge.id IS '知识分块记录内部 UUID。';
COMMENT ON COLUMN public.script_knowledge.script_id IS '所属剧本包 ID。';
COMMENT ON COLUMN public.script_knowledge.source_type IS '知识来源类型：character_knowledge/clue/script_context/evidence。';
COMMENT ON COLUMN public.script_knowledge.source_id IS '来源记录稳定 ID。';
COMMENT ON COLUMN public.script_knowledge.chunk_index IS '同一来源内的分块序号。';
COMMENT ON COLUMN public.script_knowledge.chunk_text IS '用于嵌入和召回的文本分块。';
COMMENT ON COLUMN public.script_knowledge.embedding IS '1536 维文本嵌入向量。';
COMMENT ON COLUMN public.script_knowledge.metadata IS '阶段、角色和可见性过滤元数据。';
COMMENT ON COLUMN public.script_knowledge.created_at IS '知识分块创建时间。';

-- ── 游戏运行时表 ──
COMMENT ON TABLE public.game_sessions IS '游戏会话表，记录玩家一次剧本游玩的当前快照。';
COMMENT ON COLUMN public.game_sessions.id IS '游戏会话 UUID。';
COMMENT ON COLUMN public.game_sessions.script_id IS '本次会话使用的剧本包 ID。';
COMMENT ON COLUMN public.game_sessions.player_id IS 'Supabase Auth 用户 ID，可为空以支持未登录 demo。';
COMMENT ON COLUMN public.game_sessions.player_character_id IS '玩家选择的角色 ID。';
COMMENT ON COLUMN public.game_sessions.state IS '当前 GameState 快照。';
COMMENT ON COLUMN public.game_sessions.status IS '会话状态：in_progress/paused/completed/abandoned。';
COMMENT ON COLUMN public.game_sessions.created_at IS '会话创建时间。';
COMMENT ON COLUMN public.game_sessions.updated_at IS '会话最后更新时间。';

COMMENT ON TABLE public.session_checkpoints IS 'LangGraph 会话检查点表，用于恢复游戏状态。';
COMMENT ON COLUMN public.session_checkpoints.id IS '检查点记录 UUID。';
COMMENT ON COLUMN public.session_checkpoints.session_id IS '所属游戏会话 UUID。';
COMMENT ON COLUMN public.session_checkpoints.thread_ts IS 'LangGraph 检查点时间戳。';
COMMENT ON COLUMN public.session_checkpoints.parent_ts IS '父检查点时间戳。';
COMMENT ON COLUMN public.session_checkpoints.state IS '检查点完整 GameState。';
COMMENT ON COLUMN public.session_checkpoints.created_at IS '检查点创建时间。';

COMMENT ON TABLE public.chat_messages IS '会话聊天消息表，保存玩家、NPC、DM 和系统消息。';
COMMENT ON COLUMN public.chat_messages.id IS '消息记录 UUID。';
COMMENT ON COLUMN public.chat_messages.session_id IS '所属游戏会话 UUID。';
COMMENT ON COLUMN public.chat_messages.role IS '消息角色：player/npc/dm/system。';
COMMENT ON COLUMN public.chat_messages.character_id IS '发送消息的 NPC 或 DM 角色 ID。';
COMMENT ON COLUMN public.chat_messages.text IS '消息正文。';
COMMENT ON COLUMN public.chat_messages.emotion IS 'NPC 情绪标签。';
COMMENT ON COLUMN public.chat_messages.metadata IS '审查状态、模型调用和前端展示扩展元数据。';
COMMENT ON COLUMN public.chat_messages.created_at IS '消息创建时间。';

COMMENT ON TABLE public.session_discoveries IS '会话发现记录表，记录已解锁线索、证物和场景。';
COMMENT ON COLUMN public.session_discoveries.id IS '发现记录 UUID。';
COMMENT ON COLUMN public.session_discoveries.session_id IS '所属游戏会话 UUID。';
COMMENT ON COLUMN public.session_discoveries.entity_type IS '发现实体类型：clue/evidence/scene。';
COMMENT ON COLUMN public.session_discoveries.entity_id IS '被发现实体的稳定 ID。';
COMMENT ON COLUMN public.session_discoveries.status IS '发现状态：unlocked/viewed/deep_viewed/used_in_final。';
COMMENT ON COLUMN public.session_discoveries.discovered_at IS '实体首次发现时间。';

COMMENT ON TABLE public.final_submissions IS '最终推理提交表，记录玩家对凶手、动机和证据链的判断。';
COMMENT ON COLUMN public.final_submissions.id IS '最终提交 UUID。';
COMMENT ON COLUMN public.final_submissions.session_id IS '所属游戏会话 UUID。';
COMMENT ON COLUMN public.final_submissions.suspect IS '玩家指控的嫌疑人 ID。';
COMMENT ON COLUMN public.final_submissions.motive IS '玩家填写的作案动机。';
COMMENT ON COLUMN public.final_submissions.key_evidences IS '玩家选择的关键证据 ID 列表。';
COMMENT ON COLUMN public.final_submissions.deduction IS '玩家完整推理文本。';
COMMENT ON COLUMN public.final_submissions.score IS '本次推理得分。';
COMMENT ON COLUMN public.final_submissions.result IS '评分明细 JSON。';
COMMENT ON COLUMN public.final_submissions.created_at IS '提交创建时间。';

COMMENT ON TABLE public.reviews IS '会话复盘表，保存评分、评级、真相摘要和路径对比。';
COMMENT ON COLUMN public.reviews.id IS '复盘记录 UUID。';
COMMENT ON COLUMN public.reviews.session_id IS '所属游戏会话 UUID。';
COMMENT ON COLUMN public.reviews.score IS '玩家最终得分。';
COMMENT ON COLUMN public.reviews.max_score IS '复盘满分。';
COMMENT ON COLUMN public.reviews.rating IS '复盘评级，如 S/A/B/C/D。';
COMMENT ON COLUMN public.reviews.breakdown IS '分项评分明细。';
COMMENT ON COLUMN public.reviews.truth_summary IS '真相摘要。';
COMMENT ON COLUMN public.reviews.created_at IS '复盘创建时间。';

-- ── RLS Policy 注释 ──
COMMENT ON POLICY "service_role_full_access" ON public.script_packages IS '服务端 service_role 可维护剧本包数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_stages IS '服务端 service_role 可维护阶段数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_characters IS '服务端 service_role 可维护角色数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_clues IS '服务端 service_role 可维护线索数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_evidences IS '服务端 service_role 可维护证物数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_scenes IS '服务端 service_role 可维护场景数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_media IS '服务端 service_role 可维护媒体数据。';
COMMENT ON POLICY "service_role_full_access" ON public.script_knowledge IS '服务端 service_role 可维护和检索 RAG 知识。';
COMMENT ON POLICY "service_role_full_access" ON public.game_sessions IS '服务端 service_role 可维护所有会话。';
COMMENT ON POLICY "service_role_full_access" ON public.session_checkpoints IS '服务端 service_role 可维护所有检查点。';
COMMENT ON POLICY "service_role_full_access" ON public.chat_messages IS '服务端 service_role 可维护所有聊天消息。';
COMMENT ON POLICY "service_role_full_access" ON public.session_discoveries IS '服务端 service_role 可维护所有发现记录。';
COMMENT ON POLICY "service_role_full_access" ON public.final_submissions IS '服务端 service_role 可维护所有最终提交。';
COMMENT ON POLICY "service_role_full_access" ON public.reviews IS '服务端 service_role 可维护所有复盘记录。';
COMMENT ON POLICY "players_see_unlocked_clues" ON public.script_clues IS '登录玩家只能读取当前阶段和角色可见的线索。';
COMMENT ON POLICY "players_see_visible_evidences" ON public.script_evidences IS '登录玩家只能读取当前阶段已可见的证物。';
COMMENT ON POLICY "players_see_open_scenes" ON public.script_scenes IS '登录玩家只能读取当前阶段开放的场景。';
COMMENT ON POLICY "players_own_sessions" ON public.game_sessions IS '登录玩家只能读写自己的会话。';
COMMENT ON POLICY "players_see_own_checkpoints" ON public.session_checkpoints IS '登录玩家只能读取自己会话的检查点。';
COMMENT ON POLICY "players_see_own_messages" ON public.chat_messages IS '登录玩家只能读取自己会话的聊天消息。';
COMMENT ON POLICY "players_see_own_discoveries" ON public.session_discoveries IS '登录玩家只能读取自己会话的发现记录。';
COMMENT ON POLICY "players_see_own_submissions" ON public.final_submissions IS '登录玩家只能读取自己会话的最终提交。';
COMMENT ON POLICY "players_see_own_reviews" ON public.reviews IS '登录玩家只能读取自己会话的复盘。';
COMMENT ON POLICY "public_see_published_packages" ON public.script_packages IS '匿名和登录用户只能读取已发布的剧本包列表。';
