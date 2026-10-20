# casa-immo-agent

> An AI agent that answers questions about the Casablanca real-estate market by choosing the right tool: SQL over property listings, RAG over official documents, or a price model. Every answer cites its sources.

**Status:** work in progress, week 1/4 (data pipeline)

## What it does
- *"What's the median price per m² for an apartment in Maarif?"* → SQL on listings
- *"What fees should I expect when buying an apartment?"* → RAG on official documents, with citations
- *"How much is a 90 m² flat with parking in Bourgogne worth?"* → price model, with a range

## Stack
Gemini · LangGraph · PostgreSQL + pgvector · FastAPI · Docker · GCP Cloud Run

## Data
<!-- step 2: sources, what was respected (robots.txt, ToS, no personal data) -->

## Run locally
uv sync