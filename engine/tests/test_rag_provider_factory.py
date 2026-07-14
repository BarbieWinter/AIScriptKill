from engine.api.config import Settings
from engine.rag.embeddings import DashScopeEmbeddingProvider, DeterministicEmbeddingProvider
from engine.rag.provider_factory import create_embedding_provider


def test_create_embedding_provider_uses_deterministic_backend_for_local_default() -> None:
    settings = Settings(RAG_EMBEDDING_PROVIDER="deterministic")

    provider = create_embedding_provider(settings)

    assert isinstance(provider, DeterministicEmbeddingProvider)
    assert len(provider.embed_query("本地测试")) == 1024


def test_create_embedding_provider_uses_dashscope_v4_for_production() -> None:
    settings = Settings(
        RAG_EMBEDDING_PROVIDER="dashscope",
        DASHSCOPE_API_KEY="test-key",
    )

    provider = create_embedding_provider(settings)

    assert isinstance(provider, DashScopeEmbeddingProvider)
