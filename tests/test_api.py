from pathlib import Path

import pytest
from fakes import BagOfWords, ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from morocco_tax_agent.agent.graph import DISCLAIMER, build_graph
from morocco_tax_agent.api import QUOTA_MESSAGE, app, get_graph
from morocco_tax_agent.index.chunks import load_chunks
from morocco_tax_agent.index.store import InMemoryRetriever
from morocco_tax_agent.ratelimit import RateLimiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_limiters():
    """Each test starts with empty limiters (generous unless the test sets its own)."""
    app.state.ip_limiter = RateLimiter([(100, 60)])
    app.state.global_limiter = RateLimiter([(100, 60)])


@pytest.fixture
def scripted_graph():
    retriever = InMemoryRetriever(
        load_chunks(Path("data/processed/cgi_2026_ir_articles.jsonl")), BagOfWords()
    )
    model = ScriptedChatModel(script=[AIMessage("Réponse.")] * 10, calls=[])
    app.dependency_overrides[get_graph] = lambda: build_graph(model, retriever)
    yield
    app.dependency_overrides.clear()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_root_redirects_to_the_docs():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/docs"


def test_ask(scripted_graph):
    response = client.post("/ask", json={"question": "Quel est le barème ?"})
    assert response.status_code == 200
    assert response.json() == {"answer": f"Réponse.\n\n{DISCLAIMER}"}


def test_ask_rejects_empty_question(scripted_graph):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def ask_from(ip: str):
    return client.post("/ask", json={"question": "Quel est le barème ?"},
                       headers={"X-Forwarded-For": ip})


def test_ask_is_limited_per_ip(scripted_graph):
    app.state.ip_limiter = RateLimiter([(2, 60)])
    assert [ask_from("1.1.1.1").status_code for _ in range(2)] == [200, 200]
    blocked = ask_from("1.1.1.1")
    assert blocked.status_code == 429
    assert blocked.json()["detail"].startswith("Trop de questions depuis votre adresse")
    assert 0 < int(blocked.headers["Retry-After"]) <= 60
    assert ask_from("2.2.2.2").status_code == 200  # another visitor is not blocked


def test_forged_forwarded_for_does_not_bypass_the_limit(scripted_graph):
    # the proxy appends the real client last; a client-supplied first entry is ignored
    app.state.ip_limiter = RateLimiter([(1, 60)])
    assert ask_from("forged-1, 1.1.1.1").status_code == 200
    assert ask_from("forged-2, 1.1.1.1").status_code == 429


def test_ask_has_a_global_daily_cap(scripted_graph):
    app.state.global_limiter = RateLimiter([(2, 86400)])
    assert [ask_from(ip).status_code for ip in ("a", "b", "c")] == [200, 200, 429]
    assert "limite quotidienne" in ask_from("d").json()["detail"]


def test_ask_explains_when_the_gemini_quota_is_exhausted():
    class QuotaExhausted:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")

    app.dependency_overrides[get_graph] = QuotaExhausted
    try:
        response = client.post("/ask", json={"question": "Quel est le barème ?"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["detail"] == QUOTA_MESSAGE


def test_net_salary():
    response = client.post("/net-salary", json={"gross_monthly": 10000, "dependents": 2})
    assert response.status_code == 200
    assert response.json()["net_monthly"] == "9003.64"


def test_net_salary_with_payslip_bases():
    response = client.post("/net-salary", json={
        "gross_monthly": 10500, "contributable_gross": 10000, "taxable_gross": 10000,
    })
    assert response.json()["net_monthly"] == "9403.64"


@pytest.mark.parametrize("body", [
    {"gross_monthly": -5},
    {"gross_monthly": 10000, "taxable_gross": 12000},
])
def test_net_salary_validates_input(body):
    assert client.post("/net-salary", json=body).status_code == 422
