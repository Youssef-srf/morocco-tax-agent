"""The evaluation's ground truth must be checkable without trusting whoever wrote it.

Each income-tax case gives an expected article and `evidence`, a verbatim quote
of the official text. This test fails if the quote is not found word for word
in that article of the CGI (only spaces and line breaks are normalised, since
the PDF wraps lines). Salary cases must name the official source of their net.
"""

import json
from pathlib import Path

import pytest

CASES = [json.loads(line) for line in Path("eval/cases.jsonl").read_text(encoding="utf-8").splitlines()]
ARTICLES = {
    row["label"]: " ".join(row["text"].split())
    for row in map(json.loads, Path("data/processed/cgi_2026_ir_articles.jsonl")
                   .read_text(encoding="utf-8").splitlines())
}


def by_block(block):
    return [pytest.param(c, id=c["id"]) for c in CASES if c["block"] == block]


@pytest.mark.parametrize("case", by_block("ir"))
def test_evidence_is_verbatim_in_expected_article(case):
    assert case["expected_article"] in ARTICLES, f"unknown article {case['expected_article']}"
    evidence = " ".join(case["evidence"].split())
    assert len(evidence) >= 20, "evidence too short to justify anything"
    assert evidence in ARTICLES[case["expected_article"]]


@pytest.mark.parametrize("case", by_block("out_of_scope"))
def test_out_of_scope_cases_say_whether_a_refusal_is_expected(case):
    assert isinstance(case["expected_refusal"], bool)


@pytest.mark.parametrize("case", by_block("salary"))
def test_salary_cases_cite_an_official_source(case):
    assert case["expected_net"] is not None and case["source"].startswith("http")


def test_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
