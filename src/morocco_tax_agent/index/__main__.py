"""Index an edition of the CGI into PostgreSQL + pgvector.

Usage:
    uv run python -m morocco_tax_agent.index data/processed/cgi_2026_ir_articles.jsonl

Needs DATABASE_URL and GEMINI_API_KEY (see .env.example).
"""

import argparse
import os
from pathlib import Path

from morocco_tax_agent.index.chunks import load_chunks
from morocco_tax_agent.index.store import GeminiEmbedder, PgVectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()

    chunks = load_chunks(args.jsonl)
    store = PgVectorStore(os.environ["DATABASE_URL"], GeminiEmbedder())
    store.create_schema()
    print(f"{store.index(chunks)} chunks indexed from {args.jsonl}")


if __name__ == "__main__":
    main()
