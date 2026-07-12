"""构建按权限筛选的 RAG 检索 SQL 并解码其结果行。"""

from collections.abc import Sequence

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql.elements import TextClause

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping
from engine.rag.models import RagChunk, RagSourceType, RetrievedChunk


def build_retrieval_sql() -> TextClause:
    """使用强制剧本和可见性筛选构建混合检索查询。"""
    return text(
        """
        WITH scored AS (
            SELECT
                id::text,
                script_id,
                source_type,
                source_id,
                chunk_index,
                chunk_text,
                metadata,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS vector_score,
                ts_rank_cd(
                    to_tsvector('simple', chunk_text),
                    websearch_to_tsquery('simple', :query)
                ) AS keyword_score
            FROM script_knowledge
            WHERE embedding IS NOT NULL
              -- 权限模型第8节: 剧本隔离, 只能查询当前 session 的 script_id。
              AND script_id = :script_id
              -- 权限模型第8节: 阶段可见性, 玩家不能查到未来 stage 的知识。
              AND COALESCE((metadata ->> 'stage_order')::int, 0) <= :current_stage_order
              -- 权限模型第8节: DM 可读私密材料; 玩家只读 public 或本角色私有知识。
              AND (
                    :is_dm
                    OR metadata ->> 'visibility' = 'public'
                    OR (
                        metadata ->> 'visibility' = 'character_only'
                        AND metadata ->> 'character_id' = :character_id
                    )
                  )
              -- 权限模型第8节: 玩家侧 clue 必须先解锁, 未解锁线索不进入候选集。
              AND (
                    :is_dm
                    OR source_type <> 'clue'
                    OR source_id = ANY(CAST(:unlocked_clue_ids AS text[]))
                  )
        )
        SELECT
            id,
            script_id,
            source_type,
            source_id,
            chunk_index,
            chunk_text,
            metadata,
            vector_score,
            keyword_score,
            (vector_score * 0.7 + keyword_score * 0.5) AS score
        FROM scored
        ORDER BY score DESC, COALESCE((metadata ->> 'importance')::int, 0) DESC
        LIMIT :limit
        """,
    ).bindparams(bindparam("unlocked_clue_ids", type_=ARRAY(Text)))


def row_to_result(row: RowMapping) -> RetrievedChunk:
    """将一条已校验 SQL 行解码为类型化检索结果。"""
    metadata = _row_metadata(row.get("metadata"))
    chunk = RagChunk(
        script_id=_required_text(row.get("script_id")),
        source_type=_source_type(row.get("source_type")),
        source_id=_required_text(row.get("source_id")),
        chunk_index=_required_int(row.get("chunk_index")),
        text=_required_text(row.get("chunk_text")),
        metadata=metadata,
    )
    return RetrievedChunk(
        id=_optional_text(row.get("id")),
        chunk=chunk,
        vector_score=_required_float(row.get("vector_score")),
        keyword_score=_required_float(row.get("keyword_score")),
        score=_required_float(row.get("score")),
    )


def vector_literal(values: Sequence[float]) -> str:
    """按照 pgvector 的方括号文本输入格式编码向量。"""
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _row_metadata(value: JsonValue | None) -> JsonMapping:
    if isinstance(value, dict):
        return value
    return {}


def _source_type(value: JsonValue | None) -> RagSourceType:
    text_value = _required_text(value)
    match text_value:
        case "character_knowledge":
            return "character_knowledge"
        case "clue":
            return "clue"
        case "script_context":
            return "script_context"
        case "evidence":
            return "evidence"
        case _:
            raise ValueError(f"unexpected RAG source_type: {text_value}")


def _required_text(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    raise ValueError("expected text value")


def _optional_text(value: JsonValue | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("expected optional text value")


def _required_int(value: JsonValue | None) -> int:
    if isinstance(value, int):
        return value
    raise ValueError("expected int value")


def _required_float(value: JsonValue | None) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise ValueError("expected float value")
