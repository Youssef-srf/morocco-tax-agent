"""Checks the article splitter against the official CGI 2026 PDF.

The PDF is not in the repo (data/raw is ignored), so these tests are skipped
when it is missing, for example in CI.
"""

import re
from pathlib import Path

import pytest

from morocco_tax_agent.sources.cgi import check_numbering, parse_income_tax_title

PDF = Path("data/raw/cgi_2026_fr.pdf")
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="official CGI PDF not downloaded")


@pytest.fixture(scope="module")
def articles():
    return parse_income_tax_title(PDF, edition=2026)


@pytest.fixture(scope="module")
def by_label(articles):
    return {a.label: a for a in articles}


def test_whole_income_tax_title_without_gaps(articles):
    assert articles[0].label == "Article 21"
    assert articles[-1].label == "Article 86"
    assert check_numbering(articles) == []
    assert len(articles) == 74


def test_bis_ter_quater_articles_are_kept(by_label):
    for label in ["Article 42 bis", "Article 42 ter", "Article 45 bis", "Article 70 bis",
                  "Article 82 bis", "Article 82 ter", "Article 82 quater", "Article 84 bis"]:
        assert label in by_label


def test_abrogated_articles_are_flagged(articles):
    assert {a.label for a in articles if a.abrogated} == {"Article 42", "Article 82 ter"}


def test_footnote_call_glued_to_article_number(by_label):
    # The PDF prints "Article 47290.-": article 47 followed by footnote 290.
    assert by_label["Article 47"].title.startswith("Exonération permanente")
    assert "Article 47290" not in by_label


def test_article_73_income_tax_scale(by_label):
    a73 = by_label["Article 73"]
    assert a73.title == "Taux de l’impôt"
    assert a73.chapter.startswith("CHAPITRE IV")
    assert "jusqu'à 40 000 dirhams est exonérée" in a73.text
    assert "- 37% pour le surplus." in a73.text
    assert any("60-24" in note for note in a73.amendments)  # finance law 2025 set the scale


def test_salary_articles_are_in_their_section(by_label):
    for label in ["Article 56", "Article 57", "Article 58", "Article 59", "Article 60"]:
        assert by_label[label].section == "Section III.- Revenus salariaux et assimilés"


def test_no_headers_footnotes_or_next_title_in_text(articles):
    for a in articles:
        assert "CODE GÉNÉRAL DES IMPÔTS" not in a.text, a.label
        assert not re.search(r"^TITRE\b", a.text, re.M), a.label
        assert not re.search(r"[a-zé’]\d{3}\b", a.text), a.label  # glued footnote call
        assert all(57 <= page <= 143 for page in a.pdf_pages), a.label
