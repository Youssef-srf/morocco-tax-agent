"""The agent: a LangGraph loop between Gemini and two tools.

    START -> agent -> (tool calls?) -> tools -> agent ... -> finalize -> END

- `search_tax_code` returns CGI passages with their article label, so the
  answer can cite the exact article.
- `compute_net_salary` does the arithmetic: the LLM never computes.
- `finalize` appends the disclaimer in code, so it cannot be forgotten.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from morocco_tax_agent.index.store import Retriever
from morocco_tax_agent.tools.salary import MissingRatesError, compute_net_salary

DISCLAIMER = "Information générale, pas un conseil fiscal ou juridique."
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ARTICLES_JSONL = Path("data/processed/cgi_2026_ir_articles.jsonl")

SYSTEM_PROMPT = """Tu es un assistant d'information fiscale pour les salariés au Maroc.

Périmètre : l'impôt sur le revenu des salariés (Code général des impôts 2026, articles 21 à 86),
les cotisations CNSS/AMO du salarié, et le calcul du salaire net à partir du brut.

Règles :
1. Pour toute question de droit fiscal, appelle d'abord `search_tax_code`, puis réponds uniquement
   à partir des passages renvoyés. Cite l'article exact, par exemple « (CGI 2026, article 73-I) ».
   Si les passages ne contiennent pas la réponse, dis-le : n'invente jamais un article ou un taux.
2. Pour tout calcul de salaire ou d'impôt, appelle `compute_net_salary`. Ne fais jamais de calcul
   toi-même ; reprends les montants de l'outil. Si l'outil signale une erreur, explique-la.
3. Hors périmètre (TVA, impôt sur les sociétés, droits d'enregistrement, auto-entrepreneur, Code du
   travail, ou cas personnel complexe) : refuse poliment en une ou deux phrases et renvoie vers la
   source officielle : https://www.tax.gov.ma pour la fiscalité, https://www.cnss.ma pour la CNSS.
4. Réponds en français, de façon brève et précise. N'ajoute pas d'avertissement : il est ajouté
   automatiquement."""


def make_tools(retriever: Retriever) -> list[BaseTool]:
    @tool
    def search_tax_code(query: str) -> str:
        """Cherche dans le Code général des impôts 2026 (impôt sur le revenu, articles 21 à 86).
        Renvoie les 5 passages les plus pertinents avec leur numéro d'article."""
        hits = retriever.search(query, k=5)
        return "\n\n".join(
            f"[{h.chunk.label}{f' ({h.chunk.part})' if h.chunk.part else ''} - {h.chunk.title}"
            f" | CGI {h.chunk.edition}, pages PDF {h.chunk.pdf_pages[0]}-{h.chunk.pdf_pages[-1]}]\n"
            f"{h.chunk.text}"
            for h in hits
        )

    @tool("compute_net_salary")
    def compute_net_salary_tool(
        gross_monthly: float,
        dependents: int = 0,
        contributable_gross: float | None = None,
        taxable_gross: float | None = None,
    ) -> str:
        """Calcule le salaire net mensuel d'un salarié à partir du brut mensuel (en dirhams) et du
        nombre de personnes à charge (conjoint et enfants, article 74). Si l'utilisateur donne le
        brut cotisable CNSS ou le brut imposable de son bulletin (plus bas que le brut à cause
        d'indemnités exonérées), passe-les ; sinon laisse-les vides. Renvoie le détail en JSON."""
        try:
            breakdown = compute_net_salary(
                gross_monthly, dependents,
                contributable_gross=contributable_gross, taxable_gross=taxable_gross,
            )
        except (MissingRatesError, ValueError) as error:
            return f"ERREUR : {error}"
        return json.dumps(breakdown.model_dump(mode="json"), ensure_ascii=False)

    return [search_tax_code, compute_net_salary_tool]


def build_graph(model: BaseChatModel, retriever: Retriever):
    tools = make_tools(retriever)
    llm = model.bind_tools(tools)

    def agent(state: MessagesState) -> dict:
        return {"messages": [llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])]}

    def finalize(state: MessagesState) -> dict:
        last = state["messages"][-1]
        text = last.text.rstrip()
        if text.endswith(DISCLAIMER):
            return {}
        return {"messages": [AIMessage(content=f"{text}\n\n{DISCLAIMER}", id=last.id)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "finalize"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


def ask(graph, question: str) -> str:
    result = graph.invoke({"messages": [HumanMessage(question)]}, {"recursion_limit": 12})
    return result["messages"][-1].text


def default_retriever() -> Retriever:
    """pgvector when DATABASE_URL is set, else an in-memory index of the JSONL."""
    from morocco_tax_agent.index.chunks import load_chunks
    from morocco_tax_agent.index.store import GeminiEmbedder, InMemoryRetriever, PgVectorStore

    embedder = GeminiEmbedder()
    if os.environ.get("DATABASE_URL"):
        return PgVectorStore(os.environ["DATABASE_URL"], embedder)
    return InMemoryRetriever(load_chunks(ARTICLES_JSONL), embedder)


def default_graph(retriever: Retriever | None = None):
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)
    return build_graph(model, retriever or default_retriever())
