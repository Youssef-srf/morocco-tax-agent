"""Run the evaluation cases and print one score per metric.

    uv run --env-file .env python eval/run.py                    # everything
    uv run --env-file .env python eval/run.py --retrieval-only   # no generation quota used

Only cases whose expected value is filled are run. Ground truth is checkable
without trusting its author: tests/test_eval_cases.py checks every evidence
quote against the official text.

- ir / retrieval@5: the expected article among the first 5 passages.
- ir / cited: the agent's answer cites the expected article ("article 74").
- out_of_scope / refusal: the answer refers to an official source and the agent
  did not search the tax code, iff a refusal is expected.
- salary: the calculator net is within 1 MAD of an official or real payslip net.

Detailed results are written to eval/results/<date>.json.
"""

import argparse
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from morocco_tax_agent.agent.graph import default_graph, default_retriever
from morocco_tax_agent.tools.salary import compute_net_salary

CASES = Path(__file__).parent / "cases.jsonl"
RESULTS = Path(__file__).parent / "results"
OFFICIAL_LINKS = ("tax.gov.ma", "cnss.ma")


def run_agent(graph, question: str) -> tuple[str, list[str]]:
    messages = graph.invoke({"messages": [HumanMessage(question)]}, {"recursion_limit": 12})["messages"]
    tools = [call["name"] for m in messages if isinstance(m, AIMessage) for call in m.tool_calls]
    return messages[-1].text, tools


def cites(answer: str, label: str) -> bool:
    """'Article 42 bis' is cited if the answer says 'article 42 bis' (or 'article 42-bis')."""
    number = re.escape(label.removeprefix("Article ")).replace(r"\ ", r"[\s-]")
    return re.search(rf"\barticle\s+{number}(?![\d])", answer, re.IGNORECASE) is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true", help="skip the agent (no LLM calls)")
    args = parser.parse_args()

    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    retriever = default_retriever()
    graph = default_graph(retriever)
    agent_enabled = not args.retrieval_only
    scores: dict[str, list[bool]] = {}
    details = []
    skipped: list[str] = []

    def agent(case: dict) -> tuple[str, list[str]] | None:
        """Run the agent, or None once the LLM quota is exhausted (counted as skipped, not failed)."""
        nonlocal agent_enabled
        if not agent_enabled:
            skipped.append(case["id"])
            return None
        try:
            return run_agent(graph, case["question"])
        except Exception as error:  # the Gemini client raises its own rate-limit class
            if "RESOURCE_EXHAUSTED" not in str(error):
                raise
            print(f"LLM quota exhausted at {case['id']}: agent metrics stop here")
            agent_enabled = False
            skipped.append(case["id"])
            return None

    def record(metric: str, case: dict, ok: bool, **extra) -> None:
        scores.setdefault(metric, []).append(ok)
        details.append({"metric": metric, "id": case["id"], "ok": ok, **extra})
        if not ok:
            print(f"FAIL {metric:22} {case['id']}: {extra}")

    for case in cases:
        block = case["block"]
        if block == "ir" and case.get("expected_article"):
            labels = [h.chunk.label for h in retriever.search(case["question"], k=5)]
            record("ir / retrieval@5", case, case["expected_article"] in labels, top5=labels)
            if (result := agent(case)) is None:
                continue
            answer, tools = result
            record("ir / cited", case, cites(answer, case["expected_article"]),
                   expected=case["expected_article"], tools=tools, answer=answer)
        elif block == "out_of_scope" and case.get("expected_refusal") is not None:
            if (result := agent(case)) is None:
                continue
            answer, tools = result
            refused = any(link in answer for link in OFFICIAL_LINKS) and "search_tax_code" not in tools
            record("out_of_scope / refusal", case, refused == case["expected_refusal"],
                   tools=tools, answer=answer)
        elif block == "salary" and case.get("expected_net") is not None:
            net = compute_net_salary(
                case["gross_monthly"], case.get("dependents", 0),
                contributable_gross=case.get("contributable_gross"),
                taxable_gross=case.get("taxable_gross"),
            ).net_monthly
            record("salary / net ±1 MAD", case,
                   abs(net - Decimal(str(case["expected_net"]))) <= 1, net=str(net))

    print()
    summary = {}
    for metric, results in scores.items():
        summary[metric] = f"{sum(results)}/{len(results)}"
        print(f"{metric:24} {sum(results)}/{len(results)} ({sum(results) / len(results):.0%})")
    if not scores:
        print("No case has an expected value yet.")
    if skipped:
        print(f"Agent not run on {len(skipped)} cases: {', '.join(skipped)}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{date.today().isoformat()}.json"
    out.write_text(json.dumps({"summary": summary, "skipped_agent": skipped, "details": details},
                              ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="\n")
    print(f"\nDetails written to {out}")


if __name__ == "__main__":
    main()
