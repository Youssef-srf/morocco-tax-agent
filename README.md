# morocco-tax-agent

> An AI assistant for Moroccan tax and labor questions: it answers from the official texts (General Tax Code, Labor Code, CNSS rates), cites the exact article, and computes net salary and income tax with tested tools.

**Status:** work in progress — v1 (income tax for employees + CNSS/AMO) due Nov 2, 2026

## What it does
- *"Which tax rate applies to a net taxable income of 200,000 MAD per year?"* → search in the 2026 General Tax Code, with the article cited
- *"Does the 6,000 MAD ceiling apply to AMO?"* → answer from the official CNSS rates
- *"Gross 12,000 MAD, married, 2 children: what is my net salary?"* → tested calculator, with the CNSS, AMO and income tax breakdown

Every answer ends with: *General information, not tax or legal advice.*

## Stack
Gemini · LangGraph · PostgreSQL + pgvector · FastAPI · Streamlit · Docker · GCP Cloud Run

## Sources
<!-- official texts only: versions, SHA-256 in data/raw/manifest.json, legal basis (law 2-00, art. 8) -->

## Run locally
uv sync