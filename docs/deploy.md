# Deployment (free tier only)

Rule: no spending. Never enable billing or create a paid resource; only free
tiers are used: Gemini API (free), Neon (free), Hugging Face Spaces (CPU basic, free).
The Dockerfile reads its port from `$PORT`, so it also runs on Cloud Run, but
the project does not deploy there.

## 1. Database: Neon (free)

1. Create a free account and project on https://neon.tech (no payment method).
2. Copy the connection string (`postgresql://...neon.tech/neondb?sslmode=require`).
3. Index the CGI into it from your machine (the `vector` extension is created
   by the indexer; Neon's free tier supports pgvector):

```bash
export DATABASE_URL='postgresql://...neon.tech/neondb?sslmode=require'
export GEMINI_API_KEY='...'
uv run python -m morocco_tax_agent.index data/processed/cgi_2026_ir_articles.jsonl
```

## 2. API: Hugging Face Docker Space (free)

1. On https://huggingface.co/new-space: SDK **Docker**, hardware **CPU basic (free)**.
2. In the Space settings, add the secrets `GEMINI_API_KEY`, `GEMINI_MODEL` and
   `DATABASE_URL` (the Neon string). Optional variables: `ASK_LIMIT_PER_MINUTE`
   (default 3), `ASK_LIMIT_PER_DAY` (15 per IP), `ASK_LIMIT_GLOBAL_PER_DAY` (80).
3. Create a write access token (https://huggingface.co/settings/tokens) and push:

```bash
scripts/deploy_hf_space.sh <hf-user>/morocco-tax-agent
```

The Space builds the image and serves the API on port 8080 (`app_port` in
`deploy/hf-space/README.md`); `/` redirects to the interactive docs.

## Limits of the free tier

- Gemini free tier: a small number of requests per day. `/ask` is limited per IP
  and globally, and answers HTTP 503 with a clear message when the quota is
  exhausted; `/net-salary` needs no quota and keeps working.
- A free Space sleeps after a period without visits and wakes up on the next one.
- Neon's free compute suspends when idle: the first query after a pause is slower.
