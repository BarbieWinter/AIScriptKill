from collections.abc import Sequence
from hashlib import blake2b
from math import sqrt

from pydantic import SecretStr

EMBEDDING_DIMENSIONS = 1024


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self._dimensions
        for token in _tokens(text):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        length = sqrt(sum(value * value for value in vector))
        if length == 0:
            return tuple(vector)
        return tuple(value / length for value in vector)


def _tokens(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    words = tuple(word for word in normalized.split() if word)
    if len(words) > 0:
        return words
    return tuple(normalized[index : index + 2] for index in range(max(len(normalized) - 1, 0)))


class DashScopeEmbeddingProvider:
    def __init__(
        self,
        model: str = "text-embedding-v4",
        dimensions: int = EMBEDDING_DIMENSIONS,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._embeddings = OpenAIEmbeddings(
            model=model,
            dimensions=dimensions,
            api_key=SecretStr(api_key) if api_key is not None else None,
            base_url=base_url,
        )

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self._embeddings.embed_documents(list(texts))

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embeddings.embed_query(text)
