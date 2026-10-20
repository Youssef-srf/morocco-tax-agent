"""Every value of rates/2026.yaml must appear verbatim in the official CGI text.

Each test rebuilds the sentence of the CGI from the YAML values and looks for
it in the article text extracted from the PDF (data/processed, versioned).
A typo in the YAML, or a change in the next edition, makes the test fail.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from morocco_tax_agent.rates import load_rates

ARTICLES = Path("data/processed/cgi_2026_ir_articles.jsonl")


@pytest.fixture(scope="module")
def cgi() -> dict[str, str]:
    """Article label -> text, with whitespace normalised (line breaks of the PDF)."""
    rows = [json.loads(line) for line in ARTICLES.read_text(encoding="utf-8").splitlines()]
    return {r["label"]: " ".join(r["text"].split()) for r in rows}


@pytest.fixture(scope="module")
def rates():
    return load_rates(2026).income_tax


def pct(value: Decimal) -> str:
    return f"{value.normalize():f}%"


def dotted(value: Decimal) -> str:
    """40001 -> '40.001', the thousands separator used in article 73."""
    return f"{int(value):,}".replace(",", ".")


def spaced(value: Decimal) -> str:
    """78000 -> '78 000', the thousands separator used in articles 59 and 73."""
    return f"{int(value):,}".replace(",", " ")


def test_income_tax_brackets_match_article_73(cgi, rates):
    text = cgi["Article 73"]
    first, *others = rates.brackets
    assert first.percent == 0
    assert f"jusqu'à {spaced(first.up_to)} dirhams est exonérée" in text

    lower = first.up_to
    for bracket in others:
        if bracket.up_to is None:
            assert f"{pct(bracket.percent)} pour le surplus." in text
        else:
            sentence = (f"{pct(bracket.percent)} pour la tranche du revenu allant de "
                        f"{dotted(lower + 1)} à {dotted(bracket.up_to)} dirhams")
            assert sentence in text
            lower = bracket.up_to


def test_professional_expenses_match_article_59(cgi, rates):
    text = cgi["Article 59"]
    pe = rates.professional_expenses
    assert f"A.- {pct(pe.percent_up_to_threshold)} pour les personnes ne relevant pas" in text
    assert f"n’excède pas soixante dix huit mille ({spaced(pe.threshold)}) dirhams" in text
    assert f"Ce taux est fixé à {pct(pe.percent_above_threshold)} pour les personnes" in text
    assert f"excéder trente-cinq mille ({spaced(pe.cap)}) dirhams" in text


def test_family_reduction_matches_article_74(cgi, rates):
    text = cgi["Article 74"]
    fr = rates.family_reduction
    assert f"une somme de six cents ({fr.per_dependent}) dirhams par personne à charge" in text
    assert f"ne peut pas dépasser trois mille six cents ({fr.cap}) dirhams" in text


def test_family_reduction_was_set_by_finance_law_2026():
    rows = [json.loads(line) for line in ARTICLES.read_text(encoding="utf-8").splitlines()]
    a74 = next(r for r in rows if r["label"] == "Article 74")
    assert any("50-25" in note and "2026" in note for note in a74["amendments"])


def test_unknown_year_is_refused():
    with pytest.raises(ValueError, match="No rates for 1999"):
        load_rates(1999)
