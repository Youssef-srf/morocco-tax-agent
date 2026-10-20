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
| Serve | `api.py`, `app/streamlit_app.py` | FastAPI (`/ask`, `/net-salary`) for Cloud Run; Streamlit for the local demo. |

## Sources
Official texts only (law 2-00, art. 8, excludes official legislative texts from copyright). Versions and SHA-256 in `data/raw/manifest.json`.

- CGI 2026 (tax.gov.ma), income-tax title: articles 21 to 86, PDF pages 57 to 142.
- CNSS/AMO employee rates: **not loaded yet** (see Limitations).

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
`eval/cases.jsonl` holds the cases, `eval/run.py` scores them (retrieval hit@5 for income tax, refusal for out-of-scope questions, ±1 MAD against real payslips for the calculator). The expected answers are filled by hand from the official texts and real payslips, never by the model.

## Limitations
- CNSS/AMO employee rates are not in `rates/2026.yaml` yet: the official image on cnss.ma has no figures. The calculator refuses to run until they are added from an official document.
- Tax-exempt allowances (art. 57), benefits in kind and the professions of art. 59-I-B/C are not handled by the calculator.
- Labor Code and self-employed status: planned for v2.
