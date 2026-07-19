"""声明后端自有持久化使用的 SQLAlchemy 表元数据。"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# ── Supabase public 模式元数据 ──

metadata = MetaData()


# ── 剧本包结构表 ──

script_packages = Table(
    "script_packages",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("config", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

script_stages = Table(
    "script_stages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("stage_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("definition", JSONB, nullable=False),
)

script_characters = Table(
    "script_characters",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("character_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("definition", JSONB, nullable=False),
    Column("is_playable", Boolean, nullable=False),
    Column("is_dm_alter_ego", Boolean, nullable=False),
    Column("sort_order", Integer, nullable=False),
)

script_character_chapters = Table(
    "script_character_chapters",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("chapter_id", Text, nullable=False),
    Column("character_id", Text, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("title", Text, nullable=False),
    Column("visibility", Text, nullable=False),
    Column("release", JSONB, nullable=False),
    Column("stage_min", Text),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["script_id", "character_id"],
        ["script_characters.script_id", "script_characters.character_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["script_id", "stage_min"],
        ["script_stages.script_id", "script_stages.stage_id"],
    ),
    UniqueConstraint(
        "script_id",
        "chapter_id",
        name="uq_script_character_chapters_script_chapter",
    ),
)

script_clues = Table(
    "script_clues",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("clue_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("round_id", Text, nullable=False),
    Column("image_url", Text),
    Column("description", Text, nullable=False),
    Column("is_key", Boolean, nullable=False),
    Column("importance", Integer, nullable=False),
    Column("metadata", JSONB, nullable=False),
)

script_evidences = Table(
    "script_evidences",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("evidence_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("image_url", Text),
    Column("description_surface", Text, nullable=False),
    Column("description_deep", Text),
    Column("type", Text, nullable=False),
    Column("metadata", JSONB, nullable=False),
)

script_scenes = Table(
    "script_scenes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("scene_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("background_url", Text),
    Column("definition", JSONB, nullable=False),
)

script_media = Table(
    "script_media",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("asset_id", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("file_url", Text, nullable=False),
    Column("subtitle_url", Text),
    Column("duration_sec", Float()),
    Column("metadata", JSONB, nullable=False),
)

script_endings = Table(
    "script_endings",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("ending_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("condition", JSONB, nullable=False),
    Column("on_trigger", JSONB, nullable=False),
    Column("metadata", JSONB, nullable=False),
)

script_dm_guides = Table(
    "script_dm_guides",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("guide_key", Text, nullable=False),
    Column("content", JSONB, nullable=False),
)

script_knowledge = Table(
    "script_knowledge",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("source_type", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("chunk_text", Text, nullable=False),
    Column("embedding", Vector(1024)),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint(
        "script_id",
        "source_type",
        "source_id",
        "chunk_index",
        name="uq_script_knowledge_chunk",
    ),
)


# ── 游戏运行时表 ──

game_sessions = Table(
    "game_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("script_id", Text, ForeignKey("script_packages.id"), nullable=False),
    Column("player_id", UUID(as_uuid=True)),
    Column("player_character_id", Text),
    Column("state", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("mode", Text, nullable=False, server_default=text("'legacy_single'")),
    Column("revision", BigInteger, nullable=False, server_default=text("0")),
    Column("event_head_sequence", BigInteger, nullable=False, server_default=text("0")),
    Column("state_schema_version", Integer),
    Column("runtime_package_version", Text),
    Column("runtime_package_snapshot", JSONB),
    Column("runtime_package_sha256", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "mode IN ('legacy_single', 'multiplayer_v1')",
        name="game_sessions_mode_check",
    ),
    CheckConstraint(
        "(mode = 'legacy_single' AND status IN "
        "('in_progress', 'paused', 'completed', 'abandoned')) OR "
        "(mode = 'multiplayer_v1' AND status IN "
        "('lobby', 'active', 'completed', 'closed'))",
        name="game_sessions_status_mode_check",
    ),
    CheckConstraint(
        "(mode = 'legacy_single' AND player_character_id IS NOT NULL) OR "
        "(mode = 'multiplayer_v1' AND player_character_id IS NULL)",
        name="game_sessions_character_mode_check",
    ),
    CheckConstraint("revision >= 0", name="game_sessions_revision_check"),
    CheckConstraint(
        "event_head_sequence >= 0",
        name="game_sessions_event_head_sequence_check",
    ),
    CheckConstraint(
        "state_schema_version IS NULL OR state_schema_version > 0",
        name="game_sessions_state_schema_version_check",
    ),
    CheckConstraint(
        "runtime_package_sha256 IS NULL OR runtime_package_sha256 ~ '^[0-9a-f]{64}$'",
        name="game_sessions_runtime_package_sha256_check",
    ),
    CheckConstraint(
        "(runtime_package_version IS NULL "
        "AND runtime_package_snapshot IS NULL "
        "AND runtime_package_sha256 IS NULL) OR "
        "(runtime_package_version IS NOT NULL "
        "AND length(btrim(runtime_package_version)) > 0 "
        "AND runtime_package_snapshot IS NOT NULL "
        "AND jsonb_typeof(runtime_package_snapshot) = 'object' "
        "AND runtime_package_sha256 IS NOT NULL)",
        name="game_sessions_runtime_package_consistency_check",
    ),
    CheckConstraint(
        "mode <> 'multiplayer_v1' OR "
        "(state_schema_version = 2 AND runtime_package_version IS NOT NULL)",
        name="game_sessions_multiplayer_runtime_check",
    ),
)

Index(
    "idx_game_sessions_mode_status_updated",
    game_sessions.c.mode,
    game_sessions.c.status,
    game_sessions.c.updated_at.desc(),
)

room_members = Table(
    "room_members",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("principal_id", UUID(as_uuid=True), nullable=False),
    Column("room_role", Text, nullable=False),
    Column("membership_status", Text, nullable=False, server_default=text("'joined'")),
    Column("ready_at", DateTime(timezone=True)),
    Column("joined_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("left_at", DateTime(timezone=True)),
    CheckConstraint("room_role IN ('host', 'player')", name="room_members_role_check"),
    CheckConstraint(
        "membership_status IN ('joined', 'left', 'kicked')",
        name="room_members_status_check",
    ),
    CheckConstraint(
        "(membership_status = 'joined' AND left_at IS NULL) OR "
        "(membership_status IN ('left', 'kicked') AND left_at IS NOT NULL)",
        name="room_members_presence_check",
    ),
    CheckConstraint(
        "membership_status = 'joined' OR ready_at IS NULL",
        name="room_members_ready_check",
    ),
    UniqueConstraint(
        "session_id",
        "principal_id",
        name="uq_room_members_session_principal",
    ),
    UniqueConstraint("id", "session_id", name="uq_room_members_id_session"),
    UniqueConstraint(
        "id",
        "session_id",
        "principal_id",
        name="uq_room_members_identity",
    ),
)

Index(
    "idx_room_members_session_status_joined",
    room_members.c.session_id,
    room_members.c.membership_status,
    room_members.c.joined_at,
    room_members.c.id,
)
Index(
    "uq_room_members_joined_host",
    room_members.c.session_id,
    unique=True,
    postgresql_where=text("room_role = 'host' AND membership_status = 'joined'"),
)

room_character_assignments = Table(
    "room_character_assignments",
    metadata,
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("member_id", UUID(as_uuid=True), nullable=False),
    Column("character_id", Text, nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    PrimaryKeyConstraint(
        "session_id",
        "member_id",
        name="pk_room_character_assignments",
    ),
    UniqueConstraint(
        "session_id",
        "character_id",
        name="uq_room_character_assignments_session_character",
    ),
    ForeignKeyConstraint(
        ["member_id", "session_id"],
        ["room_members.id", "room_members.session_id"],
        name="fk_room_character_assignments_member",
        ondelete="CASCADE",
    ),
    CheckConstraint(
        "length(btrim(character_id)) > 0",
        name="room_character_assignments_character_check",
    ),
)

room_invites = Table(
    "room_invites",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_by_member_id", UUID(as_uuid=True), nullable=False),
    Column("token_hash", LargeBinary, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("max_uses", SmallInteger, nullable=False, server_default=text("1")),
    Column("uses_count", SmallInteger, nullable=False, server_default=text("0")),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("token_hash", name="uq_room_invites_token_hash"),
    ForeignKeyConstraint(
        ["created_by_member_id", "session_id"],
        ["room_members.id", "room_members.session_id"],
        name="fk_room_invites_creator",
        ondelete="CASCADE",
    ),
    CheckConstraint("octet_length(token_hash) = 32", name="room_invites_token_hash_check"),
    CheckConstraint("max_uses > 0", name="room_invites_max_uses_check"),
    CheckConstraint(
        "uses_count >= 0 AND uses_count <= max_uses",
        name="room_invites_uses_count_check",
    ),
    CheckConstraint("expires_at > created_at", name="room_invites_expiry_check"),
)

Index(
    "idx_room_invites_session_expiry",
    room_invites.c.session_id,
    room_invites.c.expires_at,
    postgresql_where=text("revoked_at IS NULL"),
)

room_required_members = Table(
    "room_required_members",
    metadata,
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", SmallInteger, nullable=False),
    Column("member_id", UUID(as_uuid=True), nullable=False),
    Column("character_id", Text, nullable=False),
    Column("locked_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    PrimaryKeyConstraint("session_id", "ordinal", name="pk_room_required_members"),
    UniqueConstraint(
        "session_id",
        "member_id",
        name="uq_room_required_members_session_member",
    ),
    UniqueConstraint(
        "session_id",
        "character_id",
        name="uq_room_required_members_session_character",
    ),
    ForeignKeyConstraint(
        ["member_id", "session_id"],
        ["room_members.id", "room_members.session_id"],
        name="fk_room_required_members_member",
        ondelete="CASCADE",
    ),
    CheckConstraint("ordinal >= 0", name="room_required_members_ordinal_check"),
    CheckConstraint(
        "length(btrim(character_id)) > 0",
        name="room_required_members_character_check",
    ),
)

Index(
    "idx_room_required_members_session_ordinal",
    room_required_members.c.session_id,
    room_required_members.c.ordinal,
)

room_principal_reservations = Table(
    "room_principal_reservations",
    metadata,
    Column("principal_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("member_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint(
        "session_id",
        "member_id",
        name="uq_room_principal_reservations_session_member",
    ),
    ForeignKeyConstraint(
        ["member_id", "session_id", "principal_id"],
        [
            "room_members.id",
            "room_members.session_id",
            "room_members.principal_id",
        ],
        name="fk_room_principal_reservations_member",
        ondelete="CASCADE",
    ),
)

session_checkpoints = Table(
    "session_checkpoints",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False),
    Column("thread_ts", Text, nullable=False),
    Column("parent_ts", Text),
    Column("state", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("command_id", UUID(as_uuid=True)),
    Column("command_attempt", Integer),
    UniqueConstraint(
        "session_id",
        "thread_ts",
        name="uq_session_checkpoints_session_thread_ts",
    ),
    CheckConstraint(
        "(command_id IS NULL AND command_attempt IS NULL) OR "
        "(command_id IS NOT NULL AND command_attempt IS NOT NULL AND command_attempt > 0)",
        name="session_checkpoints_command_attempt_check",
    ),
)

Index(
    "idx_session_checkpoints_session_command",
    session_checkpoints.c.session_id,
    session_checkpoints.c.command_id,
    session_checkpoints.c.created_at.desc(),
    postgresql_where=session_checkpoints.c.command_id.is_not(None),
)

Index(
    "idx_session_checkpoints_session_command_attempt",
    session_checkpoints.c.session_id,
    session_checkpoints.c.command_id,
    session_checkpoints.c.command_attempt,
    session_checkpoints.c.thread_ts.desc(),
    postgresql_where=session_checkpoints.c.command_id.is_not(None),
)

session_command_receipts = Table(
    "session_command_receipts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("actor_principal_id", UUID(as_uuid=True)),
    Column("actor_member_id", UUID(as_uuid=True)),
    Column("command_kind", Text, nullable=False, server_default=text("'player_action'")),
    Column("command_version", Integer, nullable=False, server_default=text("1")),
    Column("request_payload", JSONB, nullable=False),
    Column("request_sha256", Text, nullable=False),
    Column("expected_revision", BigInteger),
    Column("base_revision", BigInteger),
    Column("result_revision", BigInteger),
    Column("status", Text, nullable=False),
    Column("result", JSONB),
    Column("error_code", Text),
    Column("error_details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("base_checkpoint_id", Text),
    Column("base_state", JSONB),
    Column("base_state_sha256", Text),
    Column("checkpoint_id", Text),
    Column("state_sha256", Text),
    Column("event_sequence_from", BigInteger),
    Column("event_sequence_to", BigInteger),
    Column("attempt_count", Integer, nullable=False, server_default=text("1")),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("completed_at", DateTime(timezone=True)),
    UniqueConstraint(
        "session_id", "command_id", name="uq_session_command_receipts_session_command"
    ),
    ForeignKeyConstraint(
        ["actor_member_id", "session_id", "actor_principal_id"],
        ["room_members.id", "room_members.session_id", "room_members.principal_id"],
        name="fk_session_command_receipts_actor_member",
        ondelete="RESTRICT",
    ),
    CheckConstraint("length(btrim(command_kind)) > 0", name="session_command_receipts_kind_check"),
    CheckConstraint("command_version > 0", name="session_command_receipts_version_check"),
    CheckConstraint(
        "request_sha256 ~ '^[0-9a-f]{64}$'",
        name="session_command_receipts_request_hash_check",
    ),
    CheckConstraint(
        "status IN ('processing', 'succeeded', 'rejected', 'failed')",
        name="session_command_receipts_status_check",
    ),
    CheckConstraint(
        "((status = 'succeeded' AND result IS NOT NULL AND error_code IS NULL) OR "
        "(status IN ('rejected', 'failed') AND result IS NULL AND error_code IS NOT NULL) OR "
        "(status = 'processing' AND result IS NULL AND error_code IS NULL))",
        name="session_command_receipts_status_payload_check",
    ),
    CheckConstraint(
        "(expected_revision IS NULL OR expected_revision >= 0) AND "
        "(base_revision IS NULL OR base_revision >= 0) AND "
        "(result_revision IS NULL OR result_revision >= 0)",
        name="session_command_receipts_revision_check",
    ),
    CheckConstraint("attempt_count > 0", name="session_command_receipts_attempt_check"),
    CheckConstraint(
        "((event_sequence_from IS NULL AND event_sequence_to IS NULL) OR "
        "(event_sequence_from IS NOT NULL AND event_sequence_to IS NOT NULL AND "
        "event_sequence_from > 0 AND event_sequence_to >= event_sequence_from))",
        name="session_command_receipts_event_range_check",
    ),
    CheckConstraint(
        "state_sha256 IS NULL OR state_sha256 ~ '^[0-9a-f]{64}$'",
        name="session_command_receipts_state_hash_check",
    ),
    CheckConstraint(
        "base_state_sha256 IS NULL OR base_state_sha256 ~ '^[0-9a-f]{64}$'",
        name="session_command_receipts_base_state_hash_check",
    ),
    CheckConstraint(
        "(base_state IS NULL AND base_state_sha256 IS NULL) OR "
        "(base_state IS NOT NULL AND jsonb_typeof(base_state) = 'object' "
        "AND base_state_sha256 IS NOT NULL)",
        name="session_command_receipts_base_state_check",
    ),
    CheckConstraint(
        "((actor_member_id IS NULL AND actor_principal_id IS NULL) OR "
        "(actor_member_id IS NOT NULL AND actor_principal_id IS NOT NULL))",
        name="session_command_receipts_actor_check",
    ),
    CheckConstraint(
        "status = 'processing' OR completed_at IS NOT NULL",
        name="session_command_receipts_completed_check",
    ),
    CheckConstraint(
        "(status = 'processing' AND lease_expires_at IS NOT NULL) OR "
        "(status <> 'processing' AND lease_expires_at IS NULL)",
        name="session_command_receipts_processing_lease_check",
    ),
)
Index(
    "uq_session_command_receipts_one_processing",
    session_command_receipts.c.session_id,
    unique=True,
    postgresql_where=text("status = 'processing'"),
)
Index(
    "idx_session_command_receipts_processing",
    session_command_receipts.c.session_id,
    session_command_receipts.c.status,
    session_command_receipts.c.lease_expires_at,
    postgresql_where=session_command_receipts.c.status == "processing",
)
Index(
    "idx_session_command_receipts_session_created",
    session_command_receipts.c.session_id,
    session_command_receipts.c.created_at.desc(),
)

session_events = Table(
    "session_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("sequence", BigInteger, nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", Text, nullable=False),
    Column("event_version", Integer, nullable=False, server_default=text("1")),
    Column("payload", JSONB, nullable=False),
    Column("state_sha256", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("session_id", "sequence", name="uq_session_events_session_sequence"),
    UniqueConstraint("session_id", "command_id", name="uq_session_events_session_command"),
    ForeignKeyConstraint(
        ["session_id", "command_id"],
        ["session_command_receipts.session_id", "session_command_receipts.command_id"],
        name="fk_session_events_command",
        ondelete="CASCADE",
    ),
    CheckConstraint("sequence > 0", name="session_events_sequence_check"),
    CheckConstraint("revision >= 0", name="session_events_revision_check"),
    CheckConstraint("length(btrim(event_type)) > 0", name="session_events_type_check"),
    CheckConstraint("event_version > 0", name="session_events_version_check"),
    CheckConstraint(
        "state_sha256 IS NULL OR state_sha256 ~ '^[0-9a-f]{64}$'",
        name="session_events_state_hash_check",
    ),
)
Index("idx_session_events_session_sequence", session_events.c.session_id, session_events.c.sequence)

session_checkpoint_writes = Table(
    "session_checkpoint_writes",
    metadata,
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("game_sessions.id"),
        primary_key=True,
    ),
    Column("checkpoint_id", Text, primary_key=True),
    Column("task_id", Text, primary_key=True),
    Column("write_idx", Integer, primary_key=True),
    Column("channel", Text, nullable=False),
    Column("value", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

chat_messages = Table(
    "chat_messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("character_id", Text),
    Column("text", Text, nullable=False),
    Column("emotion", Text),
    Column("metadata", JSONB, nullable=False),
    Column("engine_message_id", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "session_id",
        "engine_message_id",
        name="uq_chat_messages_session_engine_message",
    ),
)

session_discoveries = Table(
    "session_discoveries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False),
    Column("entity_type", Text, nullable=False),
    Column("entity_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("discovered_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "session_id",
        "entity_type",
        "entity_id",
        name="uq_session_discoveries_session_entity",
    ),
)

final_submissions = Table(
    "final_submissions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False),
    Column("suspect", Text, nullable=False),
    Column("motive", Text),
    Column("key_evidences", ARRAY(Text), nullable=False),
    Column("deduction", Text),
    Column("score", Integer),
    Column("result", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

reviews = Table(
    "reviews",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False),
    Column("score", Integer, nullable=False),
    Column("max_score", Integer, nullable=False),
    Column("rating", Text),
    Column("breakdown", JSONB, nullable=False),
    Column("truth_summary", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
