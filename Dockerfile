# API image for Cloud Run: uvicorn serves morocco_tax_agent.api on $PORT.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PORT=8080
WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data/processed ./data/processed
RUN uv sync --frozen --no-dev

CMD ["sh", "-c", "uvicorn morocco_tax_agent.api:app --host 0.0.0.0 --port ${PORT}"]
