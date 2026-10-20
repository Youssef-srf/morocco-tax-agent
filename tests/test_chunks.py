from pathlib import Path

import pytest

from morocco_tax_agent.index.chunks import MAX_CHARS, load_chunks, pack, split_units

ARTICLES = Path("data/processed/cgi_2026_ir_articles.jsonl")


@pytest.fixture(scope="module")
def chunks():
    return load_chunks(ARTICLES)


def test_short_articles_stay_whole(chunks):
    whole = [c for c in chunks if "#" not in c.id]
    assert {c.label for c in chunks} - {c.label for c in whole} == {"Article 57", "Article 73"}
    assert all(c.id == c.article_id and c.part is None for c in whole)


def test_abrogated_articles_are_not_indexed(chunks):
    labels = {c.label for c in chunks}
    assert "Article 42" not in labels and "Article 82 ter" not in labels


def test_no_chunk_exceeds_max_and_no_text_is_lost(chunks):
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    a57 = [c for c in chunks if c.label == "Article 57"]
    joined = "".join("".join(c.text.split()) for c in a57)
    assert "1°-lesindemnités" in joined and "27°-lespensionsderetraite" in joined
    assert [c.part for c in a57][0].startswith("1")


def test_article_73_scale_is_its_own_chunk(chunks):
    a73 = {c.part: c for c in chunks if c.label == "Article 73"}
    assert list(a73) == ["I", "II", "III"]
    assert a73["I"].text.startswith("I.- Barème de calcul")
    assert a73["I"].text.endswith("- 37% pour le surplus.")


def test_markers_must_follow_their_sequence():
    # "II-B ci-dessus" inside paragraph II is body text, not a new paragraph
    text = "I.- one\nII.- two\nII-B ci-dessus continues\nIII.- three"
    assert [m for m, _ in split_units(text)] == ["I", "II", "III"]


def test_pack_never_splits_a_unit():
    units = [("1", "a" * 1500), ("2", "b" * 400), ("3", "c" * 1500)]
    assert [(m, len(t)) for m, t in pack(units)] == [("1-2", 1901), ("3", 1500)]


def test_embedding_text_carries_the_headings(chunks):
    a59 = next(c for c in chunks if c.label == "Article 59")
    first_line, context, *_ = a59.embedding_text().splitlines()
    assert first_line == "Article 59 - Déductions"
    assert "Revenus salariaux" in context
