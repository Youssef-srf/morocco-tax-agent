"""Retrieval mechanics, with a bag-of-words embedder instead of Gemini.

The PostgreSQL test runs only when TEST_DATABASE_URL points to a database
with the pgvector extension (for example: docker compose up db).
"""

import os
from pathlib import Path

import pytest
from fakes import BagOfWords

from morocco_tax_agent.index.chunks import load_chunks
from morocco_tax_agent.index.store import InMemoryRetriever, PgVectorStore, mentioned_articles

ARTICLES = Path("data/processed/cgi_2026_ir_articles.jsonl")


@pytest.fixture(scope="module")
def chunks():
    return load_chunks(ARTICLES)


def test_mentioned_articles():
    assert mentioned_articles("Que dit l'Article 42 BIS et l'article 73 ?") == [
        "Article 42 bis", "Article 73"
    ]
    assert mentioned_articles("quel est le barème ?") == []


def test_named_article_comes_first(chunks):
    hits = InMemoryRetriever(chunks, BagOfWords()).search("que prévoit l'article 74 ?", k=5)
    assert hits[0].chunk.label == "Article 74" and hits[0].score == 1.0
    assert len({h.chunk.id for h in hits}) == len(hits) == 5


def test_similarity_search_finds_the_scale(chunks):
    hits = InMemoryRetriever(chunks, BagOfWords()).search(
        "barème de calcul de l'impôt sur le revenu, tranche exonérée", k=5
    )
    assert "cgi-2026-art-73#1" in [h.chunk.id for h in hits]


@pytest.mark.skipif("TEST_DATABASE_URL" not in os.environ, reason="no test database")
def test_pgvector_store_roundtrip(chunks):
    store = PgVectorStore(os.environ["TEST_DATABASE_URL"], BagOfWords())
    store.create_schema()
    assert store.index(chunks) == len(chunks)
    assert store.index(chunks) == len(chunks)  # reindexing replaces, never duplicates
    count = store.conn.execute("SELECT count(*) FROM chunks WHERE edition = 2026").fetchone()[0]
    assert count == len(chunks)
    hits = store.search("que prévoit l'article 74 ?", k=3)
    assert hits[0].chunk.label == "Article 74"
