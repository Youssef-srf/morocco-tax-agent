"""Agent graph mechanics, with a scripted model instead of Gemini.

These tests check the plumbing (tool routing, disclaimer, error handling).
Answer quality is measured on eval/cases.jsonl with the real model.
"""

import json
from pathlib import Path

import pytest
from fakes import BagOfWords, ScriptedChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from morocco_tax_agent.agent.graph import DISCLAIMER, SYSTEM_PROMPT, ask, build_graph, make_tools
from morocco_tax_agent.index.chunks import load_chunks
from morocco_tax_agent.index.store import InMemoryRetriever

ARTICLES = Path("data/processed/cgi_2026_ir_articles.jsonl")


@pytest.fixture(scope="module")
def retriever():
    return InMemoryRetriever(load_chunks(ARTICLES), BagOfWords())


def tool_call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


def run(retriever, script, question="question"):
    model = ScriptedChatModel(script=script, calls=[])
    graph = build_graph(model, retriever)
    result = graph.invoke({"messages": [HumanMessage(question)]})
    return model, result["messages"]


def test_search_then_answer_with_disclaimer(retriever):
    model, messages = run(retriever, [
        tool_call("search_tax_code", query="barème article 73"),
        AIMessage("La tranche jusqu'à 40 000 DH est exonérée (CGI 2026, article 73-I)."),
    ])
    tool_output = next(m for m in messages if isinstance(m, ToolMessage)).content
    assert tool_output.startswith("[Article 73 (I) - Taux de l’impôt | CGI 2026")
    assert messages[-1].text.endswith(f"(CGI 2026, article 73-I).\n\n{DISCLAIMER}")
    assert model.calls[0][0].content == SYSTEM_PROMPT  # system prompt sent first


def test_disclaimer_is_not_duplicated(retriever):
    _, messages = run(retriever, [AIMessage(f"Hors périmètre.\n\n{DISCLAIMER}")])
    assert messages[-1].text.count(DISCLAIMER) == 1


def test_salary_tool_reports_missing_rates_instead_of_guessing(retriever):
    tools = {t.name: t for t in make_tools(retriever)}
    output = tools["compute_net_salary"].invoke({"gross_monthly": 10000, "dependents": 2})
    assert output.startswith("ERREUR : CNSS/AMO rates for 2026 are not loaded yet")


def test_salary_tool_returns_the_breakdown(retriever, monkeypatch):
    from morocco_tax_agent.agent import graph
    from morocco_tax_agent.rates import Contribution, SocialRates
    from morocco_tax_agent.tools import salary

    synthetic = SocialRates(source="synthetic", contributions=[Contribution(name="A", percent=4)])
    monkeypatch.setattr(graph, "compute_net_salary",
                        lambda g, d: salary.compute_net_salary(g, d, social=synthetic))
    tools = {t.name: t for t in make_tools(retriever)}
    output = json.loads(tools["compute_net_salary"].invoke({"gross_monthly": 10000}))
    assert output["net_monthly"] and output["articles"] == ["Article 59", "Article 73", "Article 74"]


def test_ask_returns_the_final_text(retriever):
    model = ScriptedChatModel(script=[AIMessage("Réponse.")], calls=[])
    assert ask(build_graph(model, retriever), "Bonjour") == f"Réponse.\n\n{DISCLAIMER}"
