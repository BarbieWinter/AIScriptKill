"""声明后端自有持久化使用的 SQLAlchemy 表元数据。"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
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
    Column("player_character_id", Text, nullable=False),
    Column("state", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
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
    UniqueConstraint(
        "session_id",
        "thread_ts",
        name="uq_session_checkpoints_session_thread_ts",
    ),
)

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
