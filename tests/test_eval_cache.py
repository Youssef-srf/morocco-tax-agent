import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))
from run import AnswerCache, cites  # noqa: E402


def test_cache_survives_a_new_run(tmp_path):
    path = tmp_path / "cache.jsonl"
    AnswerCache(path, "model-a", "prompt").put("Q ?", "Réponse (article 73).", ["search_tax_code"])
    hit = AnswerCache(path, "model-a", "prompt").get("Q ?")
    assert hit["answer"] == "Réponse (article 73)." and hit["tools"] == ["search_tax_code"]


def test_changing_model_or_prompt_invalidates_the_cache(tmp_path):
    path = tmp_path / "cache.jsonl"
    AnswerCache(path, "model-a", "prompt").put("Q ?", "R", [])
    assert AnswerCache(path, "model-b", "prompt").get("Q ?") is None
    assert AnswerCache(path, "model-a", "prompt v2").get("Q ?") is None
    assert AnswerCache(path, "model-a", "prompt").get("Autre ?") is None


def test_cites():
    assert cites("(CGI 2026, article 73-I)", "Article 73")
    assert cites("l'Article 42 bis prévoit", "Article 42 bis")
    assert not cites("article 730", "Article 73")
    assert not cites("aucune référence", "Article 73")
