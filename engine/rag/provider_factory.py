"""解析 RAG 索引和检索使用的已配置嵌入提供方。"""

from engine.api.config import Settings, get_settings
from engine.rag.embeddings import DashScopeEmbeddingProvider, DeterministicEmbeddingProvider
from engine.rag.models import EmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """创建已校验配置选定的确定性或 OpenAI 提供方。"""
    resolved_settings = settings or get_settings()
    match resolved_settings.rag_embedding_provider:
        case "deterministic":
            return DeterministicEmbeddingProvider(resolved_settings.rag_embedding_dimensions)
        case "dashscope":
            return DashScopeEmbeddingProvider(
                model=resolved_settings.rag_dashscope_embedding_model,
                dimensions=resolved_settings.rag_embedding_dimensions,
                api_key=resolved_settings.dashscope_api_key,
                base_url=resolved_settings.dashscope_base_url,
            )
