-- multiplayer_rooms: MP-2 房间、匿名身份、邀请与选角持久化
-- 迁移保持旧单人会话可读写；多人房间的身份和私有状态只允许后端 service_role 访问。

-- ── 兼容扩展现有会话 ──

ALTER TABLE public.game_sessions
    ADD COLUMN mode TEXT NOT NULL DEFAULT 'legacy_single',
    ADD COLUMN revision BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN event_head_sequence BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN state_schema_version INTEGER,
    ADD COLUMN runtime_package_version TEXT,
    ADD COLUMN runtime_package_snapshot JSONB,
    ADD COLUMN runtime_package_sha256 TEXT,
    ADD COLUMN started_at TIMESTAMPTZ,
    ADD COLUMN closed_at TIMESTAMPTZ;

-- 多人 lobby 没有单一玩家角色；旧单人行仍由下面的 mode-aware CHECK 要求保留该值。
ALTER TABLE public.game_sessions
    ALTER COLUMN player_character_id DROP NOT NULL,
    DROP CONSTRAINT IF EXISTS game_sessions_status_check;

ALTER TABLE public.game_sessions
    ADD CONSTRAINT game_sessions_mode_check
        CHECK (mode IN ('legacy_single', 'multiplayer_v1')),
    ADD CONSTRAINT game_sessions_status_mode_check
        CHECK (
            (mode = 'legacy_single'
                AND status IN ('in_progress', 'paused', 'completed', 'abandoned'))
            OR
            (mode = 'multiplayer_v1'
                AND status IN ('lobby', 'active', 'completed', 'closed'))
        ),
    ADD CONSTRAINT game_sessions_character_mode_check
        CHECK (
            (mode = 'legacy_single' AND player_character_id IS NOT NULL)
            OR
            (mode = 'multiplayer_v1' AND player_character_id IS NULL)
        ),
    ADD CONSTRAINT game_sessions_revision_check
        CHECK (revision >= 0),
    ADD CONSTRAINT game_sessions_event_head_sequence_check
        CHECK (event_head_sequence >= 0),
    ADD CONSTRAINT game_sessions_state_schema_version_check
        CHECK (state_schema_version IS NULL OR state_schema_version > 0),
    ADD CONSTRAINT game_sessions_runtime_package_sha256_check
        CHECK (
            runtime_package_sha256 IS NULL
            OR runtime_package_sha256 ~ '^[0-9a-f]{64}$'
        ),
    ADD CONSTRAINT game_sessions_runtime_package_consistency_check
        CHECK (
            (
                runtime_package_version IS NULL
                AND runtime_package_snapshot IS NULL
                AND runtime_package_sha256 IS NULL
            )
            OR (
                runtime_package_version IS NOT NULL
                AND length(btrim(runtime_package_version)) > 0
                AND runtime_package_snapshot IS NOT NULL
                AND jsonb_typeof(runtime_package_snapshot) = 'object'
                AND runtime_package_sha256 IS NOT NULL
            )
        ),
    ADD CONSTRAINT game_sessions_multiplayer_runtime_check
        CHECK (
            mode <> 'multiplayer_v1'
            OR (
                state_schema_version = 2
                AND runtime_package_version IS NOT NULL
            )
        );

CREATE INDEX idx_game_sessions_mode_status_updated
    ON public.game_sessions(mode, status, updated_at DESC);

COMMENT ON COLUMN public.game_sessions.mode IS
    '运行模式：legacy_single 保持旧单人语义，multiplayer_v1 使用 GameStateV2 房间语义。';
COMMENT ON COLUMN public.game_sessions.revision IS
    '权威房间状态版本；每次成功的多人领域变更恰好递增一次。';
COMMENT ON COLUMN public.game_sessions.event_head_sequence IS
    '该房间已持久化事件的连续高水位；MP-3/MP-4 写入事件时推进。';
COMMENT ON COLUMN public.game_sessions.state_schema_version IS
    'state JSONB 的结构版本；multiplayer_v1 固定为 GameStateV2（版本 2）。';
COMMENT ON COLUMN public.game_sessions.runtime_package_version IS
    '创建多人房间时锁定的剧本包版本。';
COMMENT ON COLUMN public.game_sessions.runtime_package_snapshot IS
    '创建多人房间时保存的不可变、已验证运行包快照，避免活跃房间读取重新发布内容。';
COMMENT ON COLUMN public.game_sessions.runtime_package_sha256 IS
    'runtime_package_snapshot 规范化字节的十六进制小写 SHA-256。';
COMMENT ON COLUMN public.game_sessions.started_at IS
    '多人 lobby 原子启动为 active 的数据库时间；尚未启动时为空。';
COMMENT ON COLUMN public.game_sessions.closed_at IS
    '多人房间关闭的数据库时间；仍可继续或已正常完成时可为空。';
COMMENT ON COLUMN public.game_sessions.player_character_id IS
    '旧单人会话的角色 ID；multiplayer_v1 改由 room_character_assignments 表示并固定为空。';
COMMENT ON COLUMN public.game_sessions.status IS
    'legacy_single 使用旧状态集合；multiplayer_v1 使用 lobby/active/completed/closed。';

-- ── 房间成员与选角 ──

CREATE TABLE public.room_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL,
    room_role TEXT NOT NULL,
    membership_status TEXT NOT NULL DEFAULT 'joined',
    ready_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at TIMESTAMPTZ,
    CONSTRAINT room_members_role_check
        CHECK (room_role IN ('host', 'player')),
    CONSTRAINT room_members_status_check
        CHECK (membership_status IN ('joined', 'left', 'kicked')),
    CONSTRAINT room_members_presence_check
        CHECK (
            (membership_status = 'joined' AND left_at IS NULL)
            OR
            (membership_status IN ('left', 'kicked') AND left_at IS NOT NULL)
        ),
    CONSTRAINT room_members_ready_check
        CHECK (membership_status = 'joined' OR ready_at IS NULL),
    CONSTRAINT uq_room_members_session_principal UNIQUE (session_id, principal_id),
    CONSTRAINT uq_room_members_id_session UNIQUE (id, session_id),
    CONSTRAINT uq_room_members_identity UNIQUE (id, session_id, principal_id)
);

CREATE INDEX idx_room_members_session_status_joined
    ON public.room_members(session_id, membership_status, joined_at, id);
CREATE UNIQUE INDEX uq_room_members_joined_host
    ON public.room_members(session_id)
    WHERE room_role = 'host' AND membership_status = 'joined';

CREATE TABLE public.room_character_assignments (
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    member_id UUID NOT NULL,
    character_id TEXT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_room_character_assignments PRIMARY KEY (session_id, member_id),
    CONSTRAINT uq_room_character_assignments_session_character
        UNIQUE (session_id, character_id),
    CONSTRAINT fk_room_character_assignments_member
        FOREIGN KEY (member_id, session_id)
        REFERENCES public.room_members(id, session_id)
        ON DELETE CASCADE,
    CONSTRAINT room_character_assignments_character_check
        CHECK (length(btrim(character_id)) > 0)
);

-- ── 邀请、开始时成员锁定与跨房身份保留 ──

CREATE TABLE public.room_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    created_by_member_id UUID NOT NULL,
    token_hash BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    max_uses SMALLINT NOT NULL DEFAULT 1,
    uses_count SMALLINT NOT NULL DEFAULT 0,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_room_invites_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_room_invites_creator
        FOREIGN KEY (created_by_member_id, session_id)
        REFERENCES public.room_members(id, session_id)
        ON DELETE CASCADE,
    CONSTRAINT room_invites_token_hash_check
        CHECK (octet_length(token_hash) = 32),
    CONSTRAINT room_invites_max_uses_check
        CHECK (max_uses > 0),
    CONSTRAINT room_invites_uses_count_check
        CHECK (uses_count >= 0 AND uses_count <= max_uses),
    CONSTRAINT room_invites_expiry_check
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_room_invites_session_expiry
    ON public.room_invites(session_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE public.room_required_members (
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    ordinal SMALLINT NOT NULL,
    member_id UUID NOT NULL,
    character_id TEXT NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_room_required_members PRIMARY KEY (session_id, ordinal),
    CONSTRAINT uq_room_required_members_session_member UNIQUE (session_id, member_id),
    CONSTRAINT uq_room_required_members_session_character UNIQUE (session_id, character_id),
    CONSTRAINT fk_room_required_members_member
        FOREIGN KEY (member_id, session_id)
        REFERENCES public.room_members(id, session_id)
        ON DELETE CASCADE,
    CONSTRAINT room_required_members_ordinal_check
        CHECK (ordinal >= 0),
    CONSTRAINT room_required_members_character_check
        CHECK (length(btrim(character_id)) > 0)
);

CREATE INDEX idx_room_required_members_session_ordinal
    ON public.room_required_members(session_id, ordinal);

CREATE TABLE public.room_principal_reservations (
    principal_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    member_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_room_principal_reservations_session_member
        UNIQUE (session_id, member_id),
    CONSTRAINT fk_room_principal_reservations_member
        FOREIGN KEY (member_id, session_id, principal_id)
        REFERENCES public.room_members(id, session_id, principal_id)
        ON DELETE CASCADE
);

-- ── 服务端专属访问边界 ──

ALTER TABLE public.room_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.room_character_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.room_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.room_required_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.room_principal_reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.room_members
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_full_access" ON public.room_character_assignments
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_full_access" ON public.room_invites
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_full_access" ON public.room_required_members
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_full_access" ON public.room_principal_reservations
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE
    public.room_members,
    public.room_character_assignments,
    public.room_invites,
    public.room_required_members,
    public.room_principal_reservations
FROM anon, authenticated;

GRANT ALL PRIVILEGES ON TABLE
    public.room_members,
    public.room_character_assignments,
    public.room_invites,
    public.room_required_members,
    public.room_principal_reservations
TO service_role;

COMMENT ON TABLE public.room_members IS
    '多人房间成员身份；principal_id 只来自服务端验证后的 JWT sub，不使用昵称或连接 ID 认领。';
COMMENT ON COLUMN public.room_members.id IS '稳定房间成员 UUID，也是多人状态中的 member_id。';
COMMENT ON COLUMN public.room_members.session_id IS '所属 multiplayer_v1 game_sessions 房间。';
COMMENT ON COLUMN public.room_members.principal_id IS '服务端验证后的 JWT sub；身份删除不会删除历史成员。';
COMMENT ON COLUMN public.room_members.room_role IS '房间权限角色：host 或 player；host 同时占一个玩家席位。';
COMMENT ON COLUMN public.room_members.membership_status IS '成员生命周期：joined、left 或 kicked。';
COMMENT ON COLUMN public.room_members.ready_at IS '完成选角后由本人确认 ready 的时间；重选或离开必须清空。';
COMMENT ON COLUMN public.room_members.joined_at IS '成员首次加入房间的数据库时间。';
COMMENT ON COLUMN public.room_members.left_at IS '成员离开或被移出 lobby 的数据库时间。';
COMMENT ON POLICY "service_role_full_access" ON public.room_members IS
    '只有受信任的后端 service_role 可解析和维护房间成员身份。';

COMMENT ON TABLE public.room_character_assignments IS
    'lobby 选角投影；数据库唯一约束裁决同房并发抢角，不外键到可重新导入的剧本内容表。';
COMMENT ON COLUMN public.room_character_assignments.session_id IS '所属多人房间。';
COMMENT ON COLUMN public.room_character_assignments.member_id IS '执行本人选角的房间成员。';
COMMENT ON COLUMN public.room_character_assignments.character_id IS '房间锁定运行包中的可玩角色 ID。';
COMMENT ON COLUMN public.room_character_assignments.assigned_at IS '当前选角写入时间。';
COMMENT ON POLICY "service_role_full_access" ON public.room_character_assignments IS
    '只有受信任的后端 service_role 可读取和变更选角。';

COMMENT ON TABLE public.room_invites IS
    '短时房间邀请；只存 SHA-256 token hash，不保存或返回原始 token。';
COMMENT ON COLUMN public.room_invites.id IS '邀请内部 UUID。';
COMMENT ON COLUMN public.room_invites.session_id IS '邀请所属多人房间。';
COMMENT ON COLUMN public.room_invites.created_by_member_id IS '创建邀请的房间成员，首版应为 joined host。';
COMMENT ON COLUMN public.room_invites.token_hash IS '原始邀请 token 的 32 字节 SHA-256。';
COMMENT ON COLUMN public.room_invites.expires_at IS '邀请绝对过期时间。';
COMMENT ON COLUMN public.room_invites.max_uses IS '邀请最多成功接受次数。';
COMMENT ON COLUMN public.room_invites.uses_count IS '邀请已成功接受次数。';
COMMENT ON COLUMN public.room_invites.revoked_at IS '房主撤销、房间启动或关闭邀请的时间。';
COMMENT ON COLUMN public.room_invites.created_at IS '邀请创建时间。';
COMMENT ON POLICY "service_role_full_access" ON public.room_invites IS
    '只有受信任的后端 service_role 可校验和维护邀请 hash。';

COMMENT ON TABLE public.room_required_members IS
    '游戏原子开始时按 joined_at、member UUID 固定的参与者与角色集合；掉线不会删除。';
COMMENT ON COLUMN public.room_required_members.session_id IS '已开始的多人房间。';
COMMENT ON COLUMN public.room_required_members.ordinal IS '从 0 开始的规范成员顺序。';
COMMENT ON COLUMN public.room_required_members.member_id IS '开始时锁定的成员 UUID。';
COMMENT ON COLUMN public.room_required_members.character_id IS '开始时锁定的角色 ID。';
COMMENT ON COLUMN public.room_required_members.locked_at IS '原子开始事务锁定成员集合的时间。';
COMMENT ON POLICY "service_role_full_access" ON public.room_required_members IS
    '只有受信任的后端 service_role 可读取和锁定 required member 集合。';

COMMENT ON TABLE public.room_principal_reservations IS
    'principal 的未完成房间占用；principal_id 主键在并发创建/接受邀请时强制一人一局。';
COMMENT ON COLUMN public.room_principal_reservations.principal_id IS '被占用的 JWT sub。';
COMMENT ON COLUMN public.room_principal_reservations.session_id IS 'principal 当前未完成的多人房间。';
COMMENT ON COLUMN public.room_principal_reservations.member_id IS '该 principal 在房间中的成员 UUID。';
COMMENT ON COLUMN public.room_principal_reservations.created_at IS '占用记录创建时间。';
COMMENT ON POLICY "service_role_full_access" ON public.room_principal_reservations IS
    '只有受信任的后端 service_role 可维护跨房 principal 占用。';
