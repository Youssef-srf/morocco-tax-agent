"""HTTP API (FastAPI), deployed as a Docker Space on Hugging Face (free tier).

    uv run uvicorn morocco_tax_agent.api:app --reload

- POST /ask: question in French -> answer of the agent, with the cited articles.
  Rate-limited per client IP and globally, to stay within the free Gemini quota.
- POST /net-salary: the calculator alone, without the LLM (deterministic, no quota).
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from morocco_tax_agent.agent.graph import ask, default_graph
from morocco_tax_agent.ratelimit import RateLimiter
from morocco_tax_agent.tools.salary import MissingRatesError, SalaryBreakdown, compute_net_salary

MINUTE, DAY = 60, 24 * 3600
QUOTA_MESSAGE = (
    "Le quota gratuit de l'API Gemini est épuisé pour le moment : l'assistant ne peut plus "
    "répondre aux questions. Réessayez plus tard (le quota quotidien est remis à zéro à minuit, "
    "heure du Pacifique). Le calculateur de salaire net (/net-salary) reste disponible."
)

app = FastAPI(title="morocco-tax-agent", version="0.1.0")
app.state.ip_limiter = RateLimiter([
    (int(os.environ.get("ASK_LIMIT_PER_MINUTE", 3)), MINUTE),
    (int(os.environ.get("ASK_LIMIT_PER_DAY", 15)), DAY),
])
app.state.global_limiter = RateLimiter([(int(os.environ.get("ASK_LIMIT_GLOBAL_PER_DAY", 80)), DAY)])


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


def client_ip(request: Request) -> str:
    """Behind the Hugging Face proxy, the client is the last X-Forwarded-For entry
    (the one the proxy appended; earlier entries can be forged by the client)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def too_many(wait: float, message: str) -> HTTPException:
    seconds = math.ceil(wait)
    return HTTPException(status_code=429, detail=message.format(seconds=seconds),
                         headers={"Retry-After": str(seconds)})


def limit_ask(request: Request) -> None:
    if (wait := request.app.state.ip_limiter.hit(client_ip(request))) is not None:
        raise too_many(wait, "Trop de questions depuis votre adresse : réessayez dans {seconds} s. "
                             "Le calculateur /net-salary reste disponible.")
    if (wait := request.app.state.global_limiter.hit("*")) is not None:
        raise too_many(wait, "La démo a atteint sa limite quotidienne de questions (quota gratuit "
                             "Gemini) : réessayez dans {seconds} s. Le calculateur /net-salary "
                             "reste disponible.")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", dependencies=[Depends(limit_ask)])
def ask_question(body: Question, graph=Depends(get_graph)) -> Answer:
    try:
        return Answer(answer=ask(graph, body.question))
    except Exception as error:  # the Gemini client raises its own rate-limit classes
        if "RESOURCE_EXHAUSTED" in str(error):
            raise HTTPException(status_code=503, detail=QUOTA_MESSAGE) from error
        raise


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
