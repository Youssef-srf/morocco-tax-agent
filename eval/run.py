"""Run the evaluation cases and print one score per metric.

    uv run --env-file .env python eval/run.py                    # next batch
    uv run --env-file .env python eval/run.py --max-new 10       # bigger batch
    uv run --env-file .env python eval/run.py --retrieval-only   # no generation quota used

Only cases whose expected value is filled are run. Ground truth is checkable
without trusting its author: tests/test_eval_cases.py checks every evidence
quote against the official text.

The free Gemini tier allows few requests per day, so agent answers are cached
in eval/cache.jsonl, keyed by model + system prompt + question: a question
already asked costs no quota, and changing the model or the prompt invalidates
it. Each run asks the agent at most --max-new uncached questions (each uses 2
or 3 requests); run it again the next day to continue. On a per-minute limit
it waits and retries; on the daily limit it stops and keeps what it has.

- ir / retrieval@5: the expected article among the first 5 passages.
- ir / cited: the agent's answer cites the expected article ("article 74").
- out_of_scope / refusal: the answer refers to an official source and the agent
  did not search the tax code, iff a refusal is expected.
- salary: the calculator net is within 1 MAD of an official or real payslip net.

Detailed results are written to eval/results/<date>.json.
"""

import argparse
import hashlib
import json
import re
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from morocco_tax_agent.agent.graph import (
    GEMINI_MODEL, SYSTEM_PROMPT, default_graph, default_retriever,
)
from morocco_tax_agent.tools.salary import compute_net_salary

CASES = Path(__file__).parent / "cases.jsonl"
CACHE = Path(__file__).parent / "cache.jsonl"
RESULTS = Path(__file__).parent / "results"
OFFICIAL_LINKS = ("tax.gov.ma", "cnss.ma")


class DailyQuotaExhausted(Exception):
    pass


class AnswerCache:
    """Agent answers on disk, one JSON line each, keyed by model + system prompt + question."""

    def __init__(self, path: Path, model: str, prompt: str) -> None:
        self.path, self.model = path, model
        self.prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        self.entries = {e["key"]: e for e in map(json.loads, lines)}

    def key(self, question: str) -> str:
        return hashlib.sha256(f"{self.model}\n{self.prompt_hash}\n{question}".encode()).hexdigest()

    def get(self, question: str) -> dict | None:
        return self.entries.get(self.key(question))

    def put(self, question: str, answer: str, tools: list[str]) -> None:
        entry = {"key": self.key(question), "model": self.model, "prompt": self.prompt_hash,
                 "question": question, "answer": answer, "tools": tools,
                 "date": date.today().isoformat()}
        self.entries[entry["key"]] = entry
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ask_with_retry(graph, question: str, retries: int = 3) -> tuple[str, list[str]]:
    """Wait out per-minute limits; raise DailyQuotaExhausted on the daily one."""
    for attempt in range(retries + 1):
        try:
            return run_agent(graph, question)
        except Exception as error:  # the Gemini client raises its own rate-limit classes
            message = str(error)
            if "RESOURCE_EXHAUSTED" not in message:
                raise
            if "PerDay" in message or attempt == retries:
                raise DailyQuotaExhausted(message[:300]) from error
            delay = re.search(r"retry in ([\d.]+)s", message)
            time.sleep(float(delay.group(1)) + 1 if delay else 60)


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
    parser.add_argument("--max-new", type=int, default=6,
                        help="max uncached questions asked to the agent in this run")
    args = parser.parse_args()

    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    retriever = default_retriever()
    graph = default_graph(retriever)
    cache = AnswerCache(CACHE, GEMINI_MODEL, SYSTEM_PROMPT)
    budget = 0 if args.retrieval_only else args.max_new
    scores: dict[str, list[bool]] = {}
    details = []
    skipped: list[str] = []
    asked = 0

    def agent(case: dict) -> tuple[str, list[str]] | None:
        """Cached answer, or a new one within the batch budget; None if neither (skipped, not failed)."""
        nonlocal budget, asked
        if (hit := cache.get(case["question"])) is not None:
            return hit["answer"], hit["tools"]
        if budget <= 0:
            skipped.append(case["id"])
            return None
        try:
            answer, tools = ask_with_retry(graph, case["question"])
        except DailyQuotaExhausted:
            print(f"Daily Gemini quota exhausted at {case['id']}: the rest waits for the next run")
            budget = 0
            skipped.append(case["id"])
            return None
        budget -= 1
        asked += 1
        cache.put(case["question"], answer, tools)
        return answer, tools

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
    print(f"\nModel {GEMINI_MODEL}: {asked} new agent answers in this run, "
          f"{len(cache.entries)} in the cache.")
    if skipped:
        print(f"Agent not run yet on {len(skipped)} cases (next run): {', '.join(skipped)}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{date.today().isoformat()}.json"
    out.write_text(json.dumps({"model": GEMINI_MODEL, "summary": summary,
                               "skipped_agent": skipped, "details": details},
                              ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="\n")
    print(f"\nDetails written to {out}")


if __name__ == "__main__":
    main()
