"""The calculator against worked examples published by the DGI.

The reference numbers come from data/processed/dgi_examples.json, where each
one must appear in a verbatim excerpt of the official note (checked below), so
no expected value is our own computation.

- Note circulaire 733 (LF 2023), exemple 1: gross salary -> net taxable income.
  Its professional expenses rule and CNSS/AMO rates are those of 2026 (both
  checked against the CGI 2026 and cnss.ma in tests/test_rates.py); only its
  income tax used the 2023 scale, so the tax line is not used.
- Note circulaire 736 (LF 2025): gross tax on a net taxable income. The 2025
  scale is unchanged in 2026 (CGI 2026 article 73-I, tests/test_rates.py).

Known gap: in exemple 1 the expenses base excludes housing (an allowance in
cash), as article 59 requires; the calculator applies the rate to the whole
taxable gross. Both hit the 35,000 cap here, so the example cannot catch it.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from morocco_tax_agent.rates import load_rates
from morocco_tax_agent.tools.salary import compute_net_salary, scale_tax

EXAMPLES = json.loads(Path("data/processed/dgi_examples.json").read_text(encoding="utf-8"))["examples"]
BY_ID = {e["id"]: e for e in EXAMPLES}


def amount(text: str) -> Decimal:
    """'2 851.20' -> Decimal('2851.20'), as printed by the DGI."""
    return Decimal(text.replace(" ", ""))


@pytest.mark.parametrize("example", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_expected_values_are_printed_in_the_official_excerpt(example):
    excerpts = " ".join(example["excerpts"])
    expected = list(example.get("expected_annual", {}).values()) + list(example.get("scale", {}).values())
    for value in expected:
        assert f"{value} DH" in excerpts or f"({value} x" in excerpts, value


def test_gross_to_net_taxable_matches_dgi_note_733():
    ex = BY_ID["nc733-ex1"]
    inputs = {k: Decimal(v) / 12 for k, v in ex["annual_inputs"].items() if k != "dependents"}
    r = compute_net_salary(
        inputs["gross"], ex["annual_inputs"]["dependents"],
        contributable_gross=inputs["contributable_gross"], taxable_gross=inputs["taxable_gross"],
    )
    expected = ex["expected_annual"]
    for name in ("CNSS long terme", "CNSS court terme", "AMO"):
        assert abs(r.contributions[name] * 12 - amount(expected[name])) <= 1, name
    assert abs(r.professional_expenses * 12 - amount(expected["professional_expenses"])) <= 1
    # 1 MAD tolerance: we round each monthly contribution, the DGI rounds the yearly total
    assert abs(r.net_taxable * 12 - amount(expected["net_taxable"])) <= 1


@pytest.mark.parametrize("example", [e for e in EXAMPLES if "scale" in e], ids=lambda e: e["id"])
def test_scale_matches_dgi_note_736(example):
    brackets = load_rates(2026).income_tax.brackets
    assert scale_tax(amount(example["scale"]["net_taxable"]), brackets) == amount(example["scale"]["tax"])
