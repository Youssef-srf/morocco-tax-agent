"""Embeddings and vector search over the CGI chunks (PostgreSQL + pgvector).

- Rows are versioned by edition: reindexing 2027 does not touch 2026.
- A question naming an article ("article 73") gets that article first, by
  exact lookup: citing the right article must not depend on embeddings.
- `InMemoryRetriever` has the same interface, for tests and for local runs
  without a database.
"""

from __future__ import annotations

import math
import os
import re
from typing import Protocol

from pydantic import BaseModel

from morocco_tax_agent.index.chunks import Chunk

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = 768
ARTICLE_MENTION = re.compile(
    r"\barticle\s+(\d+)(?:\s+(bis|ter|quater|quinquies))?\b", re.IGNORECASE
)


class Hit(BaseModel):
    chunk: Chunk
    score: float  # cosine similarity, 1.0 for an exact article lookup


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class Retriever(Protocol):
    def search(self, query: str, k: int = 5) -> list[Hit]: ...


class GeminiEmbedder:
    def __init__(self, model: str = EMBEDDING_MODEL, dim: int = EMBEDDING_DIM) -> None:
        from google import genai

        self.client, self.model, self.dim = genai.Client(), model, dim

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 100):  # API batch limit
            response = self.client.models.embed_content(
                model=self.model, contents=texts[i:i + 100], config=config
            )
            vectors += [e.values for e in response.embeddings]
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


def mentioned_articles(query: str) -> list[str]:
    """'article 42 bis et article 73' -> ['Article 42 bis', 'Article 73']"""
    return [
        f"Article {n}" + (f" {s.lower()}" if s else "") for n, s in ARTICLE_MENTION.findall(query)
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def _merge(exact: list[Chunk], similar: list[Hit], k: int) -> list[Hit]:
    hits = [Hit(chunk=c, score=1.0) for c in exact]
    seen = {c.id for c in exact}
    hits += [h for h in similar if h.chunk.id not in seen]
    return hits[:k]


class InMemoryRetriever:
    def __init__(self, chunks: list[Chunk], embedder: Embedder) -> None:
        self.chunks, self.embedder = chunks, embedder
        self.vectors = embedder.embed_documents([c.embedding_text() for c in chunks])

    def search(self, query: str, k: int = 5) -> list[Hit]:
        labels = mentioned_articles(query)
        exact = [c for c in self.chunks if c.label in labels]
        q = self.embedder.embed_query(query)
        similar = sorted(
            (Hit(chunk=c, score=_cosine(q, v)) for c, v in zip(self.chunks, self.vectors)),
            key=lambda h: h.score, reverse=True,
        )
        return _merge(exact, similar, k)


SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    id          text PRIMARY KEY,
    article_id  text NOT NULL,
    edition     int NOT NULL,
    label       text NOT NULL,
    title       text NOT NULL,
    part        text,
    chapter     text,
    section     text,
    pdf_pages   int[] NOT NULL,
    amendments  text[] NOT NULL,
    text        text NOT NULL,
    embedding   vector({EMBEDDING_DIM}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_edition_label_idx ON chunks (edition, label);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
"""
COLUMNS = ["id", "article_id", "edition", "label", "title", "part", "chapter", "section",
           "pdf_pages", "amendments", "text"]


class PgVectorStore:
    def __init__(self, dsn: str, embedder: Embedder, edition: int = 2026) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.embedder, self.edition = embedder, edition

    def create_schema(self) -> None:
        self.conn.execute(SCHEMA)

    def index(self, chunks: list[Chunk]) -> int:
        """Replace the chunks of each edition present in `chunks`."""
        from pgvector import Vector

        vectors = self.embedder.embed_documents([c.embedding_text() for c in chunks])
        with self.conn.transaction():
            for edition in {c.edition for c in chunks}:
                self.conn.execute("DELETE FROM chunks WHERE edition = %s", (edition,))
            with self.conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO chunks ({', '.join(COLUMNS)}, embedding) "
                    f"VALUES ({', '.join(['%s'] * (len(COLUMNS) + 1))})",
                    [[getattr(c, col) for col in COLUMNS] + [Vector(v)]
                     for c, v in zip(chunks, vectors)],
                )
        return len(chunks)

    def _rows(self, sql: str, params: tuple) -> list[tuple[Chunk, float]]:
        rows = self.conn.execute(sql, params).fetchall()
        return [(Chunk(**dict(zip(COLUMNS, row[:-1]))), float(row[-1])) for row in rows]

    def search(self, query: str, k: int = 5) -> list[Hit]:
        from pgvector import Vector

        cols = ", ".join(COLUMNS)
        exact = [c for c, _ in self._rows(
            f"SELECT {cols}, 1.0 FROM chunks WHERE edition = %s AND label = ANY(%s) ORDER BY id",
            (self.edition, mentioned_articles(query)),
        )]
        q = Vector(self.embedder.embed_query(query))
        similar = [Hit(chunk=c, score=s) for c, s in self._rows(
            f"SELECT {cols}, 1 - (embedding <=> %s) FROM chunks WHERE edition = %s "
            "ORDER BY embedding <=> %s LIMIT %s",
            (q, self.edition, q, k),
        )]
        return _merge(exact, similar, k)
