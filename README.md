# morocco-tax-agent

> An AI assistant for Moroccan employees' tax questions: it answers from the official General Tax Code (CGI 2026), cites the exact article, and computes net salary with tested tools.

**Status:** work in progress — v1 (income tax for employees + CNSS/AMO) due Nov 2, 2026.

## What it does
- *"Which tax rate applies to a net taxable income of 200,000 MAD per year?"* → search in the 2026 General Tax Code, with the article cited
- *"Does the 6,000 MAD ceiling apply to AMO?"* → answer from the official CNSS rates
- *"Gross 12,000 MAD, married, 2 children: what is my net salary?"* → tested calculator, with the CNSS, AMO and income tax breakdown
- Out of scope (VAT, corporate tax, registration duties…): a polite refusal and a link to the official source

Every answer ends with: *Information générale, pas un conseil fiscal ou juridique.*

## How it works

```
CGI PDF ──► article splitter ──► 74 articles (JSONL) ──► chunks ──► pgvector
                                                                        │
question ──► LangGraph agent (Gemini) ──► search_tax_code ──────────────┘
                     │
                     └──────────────────► compute_net_salary ◄── rates/2026.yaml
```

| Step | Code | Key choice |
| --- | --- | --- |
| Split the CGI | `sources/cgi.py` | One chunk = one article (the unit we cite). Body vs footnotes by font size; footnotes kept as amendment history. Title bounds found by headings, numbering checked. |
| Chunk | `index/chunks.py` | Articles over 8,000 characters (57, 73) split at their own markers (I.-, A.-, 1°-), never mid-paragraph. |
| Retrieve | `index/store.py` | pgvector, versioned by edition. A question naming an article gets it by exact lookup first. |
| Compute | `tools/salary.py` | The LLM never computes. Rates are versioned by year and each value is checked verbatim against the official text. |
| Agent | `agent/graph.py` | Explicit LangGraph: agent ⇄ tools, then a `finalize` node that appends the disclaimer in code. |
| Serve | `api.py`, `app/streamlit_app.py` | FastAPI (`/ask`, `/net-salary`) as a Hugging Face Docker Space, Neon for pgvector, free tiers only ([docs/deploy.md](docs/deploy.md)); `/ask` is rate-limited per IP and globally, and says so clearly when the free Gemini quota is exhausted. Streamlit for the local demo. |

## Sources
Official texts only (law 2-00, art. 8, excludes official legislative texts from copyright). Versions and SHA-256 in `data/raw/manifest.json`.

- CGI 2026 (tax.gov.ma), income-tax title: articles 21 to 86, PDF pages 57 to 142.
- CNSS/AMO employee rates (0.52% + 3.96% up to 6,000 MAD/month, AMO 2.26% uncapped): cnss.ma rates table and FAQ, verbatim excerpts in `data/processed/cnss_rates_sources.json`. Arrêté 1314.25 (Bulletin officiel n° 7443, 29 Sept 2025) excludes some allowances from the contribution base; it does not change these rates.

## Run locally

```bash
uv sync
cp .env.example .env            # then set GEMINI_API_KEY
uv run pytest -q
```

Rebuild the articles from the official PDF (download it from a browser into `data/raw/`):

```bash
uv run python scripts/check_sources.py data/raw/*.pdf
uv run python -m morocco_tax_agent.sources.cgi data/raw/cgi_2026_fr.pdf --edition 2026
```

Index into a local pgvector and start the API or the demo:

```bash
docker compose up -d db
uv run --env-file .env python -m morocco_tax_agent.index data/processed/cgi_2026_ir_articles.jsonl
uv run --env-file .env uvicorn morocco_tax_agent.api:app --reload
uv run --env-file .env --group ui streamlit run app/streamlit_app.py
```

Without `DATABASE_URL`, the agent embeds the articles in memory at startup.

## Evaluation
`eval/cases.jsonl` holds the cases, `eval/run.py` scores them: retrieval hit@5 and article cited in the answer for income tax, refusal for out-of-scope questions. Every expected article comes with a verbatim quote of the CGI, checked by `tests/test_eval_cases.py`. The calculator is checked against worked examples published by the DGI (`tests/test_official_examples.py`), never against its own numbers.

Agent answers are cached in `eval/cache.jsonl` (keyed by model, system prompt and question), so the evaluation runs in daily batches within the free Gemini quota:

```bash
uv run --env-file .env python eval/run.py --max-new 6
```

## Limitations
- The CNSS rates table comes from the March 2025 capture of cnss.ma: the live site no longer publishes it.
- Exempt allowances (arrêté 1314.25 for CNSS, CGI art. 57 for income tax) are not computed from rules: pass the payslip's "brut cotisable" and "brut imposable" as `contributable_gross` and `taxable_gross`.
- Benefits in kind and the professions of art. 59-I-B/C are not handled by the calculator.
- Labor Code and self-employed status: planned for v2.
