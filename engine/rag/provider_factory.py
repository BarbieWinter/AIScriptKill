from typing import assert_never

from engine.api.config import Settings, get_settings
from engine.rag.embeddings import DeterministicEmbeddingProvider, OpenAIEmbeddingProvider
from engine.rag.models import EmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved_settings = settings or get_settings()
    match resolved_settings.rag_embedding_provider:
        case "deterministic":
            return DeterministicEmbeddingProvider(resolved_settings.rag_embedding_dimensions)
        case "openai":
            return OpenAIEmbeddingProvider(
                model=resolved_settings.rag_openai_embedding_model,
                dimensions=resolved_settings.rag_embedding_dimensions,
                api_key=resolved_settings.openai_api_key,
            )
        case unreachable:
            assert_never(unreachable)
