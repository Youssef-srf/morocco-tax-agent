from pathlib import Path

import pytest
from fakes import BagOfWords, ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from morocco_tax_agent.agent.graph import DISCLAIMER, build_graph
from morocco_tax_agent.api import app, get_graph
from morocco_tax_agent.index.chunks import load_chunks
from morocco_tax_agent.index.store import InMemoryRetriever

client = TestClient(app)


@pytest.fixture
def scripted_graph():
    retriever = InMemoryRetriever(
        load_chunks(Path("data/processed/cgi_2026_ir_articles.jsonl")), BagOfWords()
    )
    model = ScriptedChatModel(script=[AIMessage("Réponse.")], calls=[])
    app.dependency_overrides[get_graph] = lambda: build_graph(model, retriever)
    yield
    app.dependency_overrides.clear()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ask(scripted_graph):
    response = client.post("/ask", json={"question": "Quel est le barème ?"})
    assert response.status_code == 200
    assert response.json() == {"answer": f"Réponse.\n\n{DISCLAIMER}"}


def test_ask_rejects_empty_question(scripted_graph):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_net_salary_is_unavailable_until_official_rates_are_loaded():
    response = client.post("/net-salary", json={"gross_monthly": 10000, "dependents": 1})
    assert response.status_code == 503
    assert "CNSS/AMO rates for 2026" in response.json()["detail"]


def test_net_salary_validates_input():
    assert client.post("/net-salary", json={"gross_monthly": -5}).status_code == 422
