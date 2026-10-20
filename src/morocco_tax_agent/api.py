"""HTTP API (FastAPI), the entry point deployed on Cloud Run.

    uv run uvicorn morocco_tax_agent.api:app --reload

- POST /ask: question in French -> answer of the agent, with the cited articles.
- POST /net-salary: the calculator alone, without the LLM (deterministic).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from morocco_tax_agent.agent.graph import ask, default_graph
from morocco_tax_agent.tools.salary import MissingRatesError, SalaryBreakdown, compute_net_salary

app = FastAPI(title="morocco-tax-agent", version="0.1.0")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class Answer(BaseModel):
    answer: str


class SalaryRequest(BaseModel):
    gross_monthly: float = Field(gt=0)
    dependents: int = Field(default=0, ge=0)
    contributable_gross: float | None = Field(default=None, ge=0)  # "brut cotisable"
    taxable_gross: float | None = Field(default=None, ge=0)  # "brut imposable"


@lru_cache(maxsize=1)
def get_graph():
    return default_graph()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask_question(body: Question, graph=Depends(get_graph)) -> Answer:
    return Answer(answer=ask(graph, body.question))


@app.post("/net-salary")
def net_salary(body: SalaryRequest) -> SalaryBreakdown:
    try:
        return compute_net_salary(
            body.gross_monthly, body.dependents,
            contributable_gross=body.contributable_gross, taxable_gross=body.taxable_gross,
        )
    except MissingRatesError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
