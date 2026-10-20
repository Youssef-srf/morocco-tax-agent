"""Run the evaluation cases and print one score per block.

    uv run --env-file .env python eval/run.py

Only cases whose expected value is filled are run: the ground truth (expected
article, net of a real payslip) comes from Youssef, never from the model.

- ir: retrieval hit@5, the expected article among the first 5 passages.
- out_of_scope: the answer refers the user to an official source.
- salary: the calculator net is within 1 MAD of the real payslip net.
"""

import json
from decimal import Decimal
from pathlib import Path

from morocco_tax_agent.agent.graph import ask, default_graph, default_retriever
from morocco_tax_agent.tools.salary import compute_net_salary

CASES = Path(__file__).parent / "cases.jsonl"
OFFICIAL_LINKS = ("tax.gov.ma", "cnss.ma")


def main() -> None:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    retriever = default_retriever()
    graph = None
    scores: dict[str, list[bool]] = {}

    for case in cases:
        block = case["block"]
        if block == "ir" and case.get("expected_article"):
            labels = [h.chunk.label for h in retriever.search(case["question"], k=5)]
            ok = case["expected_article"] in labels
        elif block == "out_of_scope" and case.get("expected_refusal"):
            graph = graph or default_graph(retriever)
            ok = any(link in ask(graph, case["question"]) for link in OFFICIAL_LINKS)
        elif block == "salary" and case.get("expected_net") is not None:
            net = compute_net_salary(case["gross_monthly"], case.get("dependents", 0)).net_monthly
            ok = abs(net - Decimal(str(case["expected_net"]))) <= 1
        else:
            continue
        scores.setdefault(block, []).append(ok)
        if not ok:
            print(f"FAIL {case['id']}: {case['question'] if 'question' in case else case}")

    for block, results in scores.items():
        print(f"{block:14} {sum(results)}/{len(results)} ({sum(results) / len(results):.0%})")
    if not scores:
        print("No case has an expected value yet: fill eval/cases.jsonl first.")


if __name__ == "__main__":
    main()
