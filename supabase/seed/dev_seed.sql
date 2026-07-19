-- dev_seed: Phase 1 本地验收数据
-- 只放公开 demo 数据，便于验证剧本列表、RLS 可见性和 pgvector 查询链路。

INSERT INTO public.script_packages (id, name, version, config, status)
VALUES (
    'snow-village',
    '雪乡连环杀人事件',
    '0.1.0',
    '{"title":"雪乡连环杀人事件","min_players":1,"max_players":4,"engine":{"entry_stage":"prologue"}}'::jsonb,
    'published'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    version = EXCLUDED.version,
    config = EXCLUDED.config,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO public.script_stages (script_id, stage_id, name, sort_order, definition)
VALUES
    ('snow-village', 'prologue', '雪夜抵达', 10, '{"available_actions":["talk_to_npc","open_clue_board"],"available_characters":["wangdada"],"available_scenes":["village_entrance"]}'::jsonb),
    ('snow-village', 'act1_investigation', '饭店调查', 20, '{"available_actions":["talk_to_npc","examine_scene","show_evidence","request_advance"],"available_characters":["wangdada","chengjun"],"available_scenes":["restaurant_hall","crime_scene"]}'::jsonb)
ON CONFLICT (script_id, stage_id) DO UPDATE
SET name = EXCLUDED.name,
    sort_order = EXCLUDED.sort_order,
    definition = EXCLUDED.definition;

INSERT INTO public.script_characters (
    script_id,
    character_id,
    name,
    definition,
    is_playable,
    is_dm_alter_ego,
    sort_order
)
VALUES
    ('snow-village', 'zhuosiyuan', '卓司元', '{"role":"player","bio":"返乡调查者"}'::jsonb, true, false, 10),
    ('snow-village', 'wangdada', '王大达', '{"role":"npc","bio":"雪乡饭店老板"}'::jsonb, false, false, 20),
    ('snow-village', 'dm', '主持人', '{"role":"dm","bio":"系统叙事代理"}'::jsonb, false, true, 99)
ON CONFLICT (script_id, character_id) DO UPDATE
SET name = EXCLUDED.name,
    definition = EXCLUDED.definition,
    is_playable = EXCLUDED.is_playable,
    is_dm_alter_ego = EXCLUDED.is_dm_alter_ego,
    sort_order = EXCLUDED.sort_order;

INSERT INTO public.script_scenes (script_id, scene_id, name, background_url, definition)
VALUES
    ('snow-village', 'village_entrance', '雪乡入口', NULL, '{"available_in_stages":["prologue"],"hotspots":["lantern","snow_path"]}'::jsonb),
    ('snow-village', 'restaurant_hall', '饭店大厅', NULL, '{"available_in_stages":["act1_investigation"],"hotspots":["counter","fireplace"]}'::jsonb),
    ('snow-village', 'crime_scene', '后院案发地', NULL, '{"available_in_stages":["act1_investigation"],"hotspots":["footprint","broken_lantern"]}'::jsonb)
ON CONFLICT (script_id, scene_id) DO UPDATE
SET name = EXCLUDED.name,
    background_url = EXCLUDED.background_url,
    definition = EXCLUDED.definition;

INSERT INTO public.script_clues (
    script_id,
    clue_id,
    name,
    round_id,
    image_url,
    description,
    is_key,
    importance,
    metadata
)
VALUES
    ('snow-village', 'broken_lantern', '破碎的红灯笼', 'act1_investigation', NULL, '灯笼碎片上残留着不属于饭店后院的煤灰。', true, 4, '{"stage_visible":"act1_investigation","visibility":"public","character_id":"public"}'::jsonb),
    ('snow-village', 'muddy_footprint', '雪泥脚印', 'act1_investigation', NULL, '脚印从后门一路延伸到柴房方向。', false, 2, '{"stage_visible":"act1_investigation","visibility":"public","character_id":"public"}'::jsonb)
ON CONFLICT (script_id, clue_id) DO UPDATE
SET name = EXCLUDED.name,
    round_id = EXCLUDED.round_id,
    image_url = EXCLUDED.image_url,
    description = EXCLUDED.description,
    is_key = EXCLUDED.is_key,
    importance = EXCLUDED.importance,
    metadata = EXCLUDED.metadata;

INSERT INTO public.script_evidences (
    script_id,
    evidence_id,
    name,
    image_url,
    description_surface,
    description_deep,
    type,
    metadata
)
VALUES (
    'snow-village',
    'coal_stained_glove',
    '沾煤灰的手套',
    NULL,
    '手套外侧有明显煤灰，指尖处还有红蜡痕迹。',
    '煤灰来源与饭店后门柴房一致，红蜡可能来自案发现场灯笼。',
    'key_evidence',
    '{"stage_visible":"act1_investigation","visibility":"public"}'::jsonb
)
ON CONFLICT (script_id, evidence_id) DO UPDATE
SET name = EXCLUDED.name,
    image_url = EXCLUDED.image_url,
    description_surface = EXCLUDED.description_surface,
    description_deep = EXCLUDED.description_deep,
    type = EXCLUDED.type,
    metadata = EXCLUDED.metadata;

INSERT INTO public.script_media (script_id, asset_id, type, file_url, subtitle_url, duration_sec, metadata)
VALUES (
    'snow-village',
    'bgm_snow_night',
    'bgm',
    '/media/snow-village/bgm_snow_night.mp3',
    NULL,
    90,
    '{"loop":true,"volume":0.35,"trigger_on":"prologue"}'::jsonb
)
ON CONFLICT (script_id, asset_id) DO UPDATE
SET type = EXCLUDED.type,
    file_url = EXCLUDED.file_url,
    subtitle_url = EXCLUDED.subtitle_url,
    duration_sec = EXCLUDED.duration_sec,
    metadata = EXCLUDED.metadata;

INSERT INTO public.script_knowledge (
    script_id,
    source_type,
    source_id,
    chunk_index,
    chunk_text,
    embedding,
    metadata
)
SELECT
    'snow-village',
    'script_context',
    'phase1_seed_context',
    0,
    '雪乡案发夜，破碎灯笼、煤灰手套和后门脚印共同指向饭店后院的异常行动。',
    array_prepend(1::real, array_fill(0::real, ARRAY[1023]))::vector,
    '{"stage_visible":"act1_investigation","visibility":"dm_only","character_id":"dm"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM public.script_knowledge
    WHERE script_id = 'snow-village'
      AND source_type = 'script_context'
      AND source_id = 'phase1_seed_context'
      AND chunk_index = 0
);
