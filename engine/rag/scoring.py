from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import log, sqrt
from typing import Final

from engine.rag.models import EmbeddingVector, RagIndexRecord, RetrievedChunk

VECTOR_WEIGHT: Final = 0.7
BM25_WEIGHT: Final = 0.5
BM25_K1: Final = 1.5
BM25_B: Final = 0.75


@dataclass(frozen=True, slots=True)
class Bm25Corpus:
    documents: tuple[tuple[str, ...], ...]
    average_length: float


def score_records(
    query: str,
    query_embedding: EmbeddingVector,
    records: Sequence[RagIndexRecord],
) -> tuple[RetrievedChunk, ...]:
    keyword_scores = bm25_keyword_scores(query, tuple(record.chunk.text for record in records))
    return tuple(
        _score_record(query_embedding, record, keyword_score)
        for record, keyword_score in zip(records, keyword_scores, strict=True)
    )


def rescore_with_bm25(
    query: str,
    candidates: Sequence[RetrievedChunk],
) -> tuple[RetrievedChunk, ...]:
    keyword_scores = bm25_keyword_scores(query, tuple(result.chunk.text for result in candidates))
    return tuple(
        RetrievedChunk(
            id=result.id,
            chunk=result.chunk,
            vector_score=result.vector_score,
            keyword_score=keyword_score,
            score=_combined_score(result.vector_score, keyword_score),
        )
        for result, keyword_score in zip(candidates, keyword_scores, strict=True)
    )


def _score_record(
    query_embedding: EmbeddingVector,
    record: RagIndexRecord,
    keyword_score: float,
) -> RetrievedChunk:
    vector_score = cosine_similarity(query_embedding, record.embedding)
    return RetrievedChunk(
        id=None,
        chunk=record.chunk,
        vector_score=vector_score,
        keyword_score=keyword_score,
        score=_combined_score(vector_score, keyword_score),
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def bm25_keyword_scores(query: str, texts: Sequence[str]) -> tuple[float, ...]:
    query_terms = tuple(dict.fromkeys(search_tokens(query)))
    tokenized_documents = tuple(search_tokens(text_value) for text_value in texts)
    if len(query_terms) == 0 or len(tokenized_documents) == 0:
        return tuple(0.0 for _ in texts)
    corpus = _bm25_corpus(tokenized_documents)
    raw_scores = tuple(
        _bm25_score(query_terms, document_tokens, corpus) for document_tokens in tokenized_documents
    )
    max_score = max(raw_scores)
    if max_score <= 0.0:
        return tuple(0.0 for _ in texts)
    return tuple(score / max_score for score in raw_scores)


def search_tokens(text_value: str) -> tuple[str, ...]:
    normalized = text_value.casefold()
    words = tuple(word for word in normalized.split() if word)
    bigrams = tuple(normalized[index : index + 2] for index in range(max(len(normalized) - 1, 0)))
    return (*words, *bigrams, *tuple(normalized))


def embedding_vector(values: Sequence[float]) -> EmbeddingVector:
    return tuple(float(value) for value in values)


def _combined_score(vector_score: float, keyword_score: float) -> float:
    return vector_score * VECTOR_WEIGHT + keyword_score * BM25_WEIGHT


def _bm25_corpus(documents: tuple[tuple[str, ...], ...]) -> Bm25Corpus:
    token_count = sum(len(document) for document in documents)
    average_length = token_count / len(documents)
    return Bm25Corpus(documents=documents, average_length=average_length)


def _bm25_score(
    query_terms: tuple[str, ...],
    document_tokens: tuple[str, ...],
    corpus: Bm25Corpus,
) -> float:
    if len(document_tokens) == 0:
        return 0.0
    frequencies = Counter(document_tokens)
    score = 0.0
    for term in query_terms:
        term_frequency = frequencies[term]
        if term_frequency > 0:
            idf = _inverse_document_frequency(term, corpus)
            length_norm = 1 - BM25_B + BM25_B * len(document_tokens) / corpus.average_length
            numerator = term_frequency * (BM25_K1 + 1)
            denominator = term_frequency + BM25_K1 * length_norm
            score += idf * numerator / denominator
    return score


def _inverse_document_frequency(term: str, corpus: Bm25Corpus) -> float:
    document_frequency = sum(1 for document in corpus.documents if term in document)
    document_count = len(corpus.documents)
    return log(1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
