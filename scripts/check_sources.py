"""Quality check of the official source PDFs before indexing.

Usage:
    uv run python scripts/check_sources.py data/raw/*.pdf

For each PDF, reports:
  - pages, share of pages with extractable text (low share => scanned, needs OCR)
  - typical OCR artifacts (Roman numerals read as "Ill", "I'" instead of "l'")
  - "Article N" headings found, and gaps in the numbering
  - pages where pdfplumber detects tables, with a preview of the first ones

Writes data/raw/manifest.json (file, sha256, size, pages, check date) so each
answer of the assistant can later be traced to an exact version of a source.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import pdfplumber

MIN_CHARS_TEXT_PAGE = 200  # below this, a page is probably an image or blank
ARTICLE_RE = re.compile(
    r"^\s*Art(?:icle|\.)\s+(premier|1er|\d+)(?:\s*[-.]?\s*(bis|ter|quater|quinquies))?\b",
    re.IGNORECASE | re.MULTILINE,
)
OCR_ARTIFACTS = [
    (re.compile(r"\bIll\b"), "'Ill' (III mal lu)"),
    (re.compile(r"\bI'[a-zé]"), "\"I'\" au lieu de \"l'\""),
    (re.compile(r"\b[a-z]+[0O][a-z]+\b"), "chiffre 0/O au milieu d'un mot"),
]
TABLE_KEYWORDS = ("barème", "bareme", "taux", "tranche", "plafond")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def article_number(match: re.Match) -> int:
    raw = match.group(1).lower()
    return 1 if raw in ("premier", "1er") else int(raw)


def check(path: Path) -> dict:
    report: dict = {"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}
    text_pages, chars, articles, table_pages, artifacts = 0, [], [], [], {}
    previews: list[str] = []

    with pdfplumber.open(path) as pdf:
        report["pages"] = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            chars.append(len(text))
            if len(text) >= MIN_CHARS_TEXT_PAGE:
                text_pages += 1
            articles += [article_number(m) for m in ARTICLE_RE.finditer(text)]
            for regex, label in OCR_ARTIFACTS:
                n = len(regex.findall(text))
                if n:
                    artifacts[label] = artifacts.get(label, 0) + n
            tables = page.find_tables()
            if tables:
                table_pages.append(i)
                lowered = text.lower()
                if len(previews) < 3 and any(k in lowered for k in TABLE_KEYWORDS):
                    rows = tables[0].extract()[:4]
                    previews.append(f"page {i}: " + json.dumps(rows, ensure_ascii=False))

    n = max(report["pages"], 1)
    unique = sorted(set(articles))
    gaps = sorted(set(range(1, unique[-1] + 1)) - set(unique)) if unique else []
    report.update(
        text_page_ratio=round(text_pages / n, 3),
        median_chars_per_page=sorted(chars)[len(chars) // 2] if chars else 0,
        ocr_artifacts=artifacts,
        article_headings_found=len(articles),
        distinct_articles=len(unique),
        highest_article=unique[-1] if unique else None,
        missing_article_numbers=len(gaps),
        first_missing=gaps[:20],
        table_pages=len(table_pages),
        first_table_pages=table_pages[:20],
        table_previews=previews,
    )
    return report


def verdict(r: dict) -> str:
    if r["text_page_ratio"] < 0.5:
        return "SCANNÉ : OCR nécessaire avant indexation"
    if r["ocr_artifacts"]:
        return "TEXTE OK, mais issu d'un OCR : nettoyer avant de découper par article"
    if r["distinct_articles"] == 0:
        return "TEXTE OK, mais aucun titre 'Article N' détecté : vérifier le format"
    return "OK"


def main(paths: list[str]) -> None:
    if not paths:
        sys.exit("Usage: python scripts/check_sources.py data/raw/*.pdf")
    # PowerShell does not expand "data/raw/*.pdf": expand the patterns here.
    files = sorted({f for pattern in paths for f in Path().glob(pattern)} or set(map(Path, paths)))
    paths = [str(f) for f in files]
    reports = []
    for p in map(Path, paths):
        with p.open("rb") as f:
            head = f.read(5)
        if head != b"%PDF-":
            print(f"\n=== {p.name} ===\nverdict                  PAS UN PDF ({p.stat().st_size} octets) : "
                  "le serveur a renvoyé autre chose (page HTML ?). Retélécharge depuis le navigateur.")
            continue
        r = check(p)
        r["verdict"] = verdict(r)
        reports.append(r)
        print(f"\n=== {r['file']} ===")
        for key in (
            "verdict", "pages", "text_page_ratio", "median_chars_per_page", "ocr_artifacts",
            "distinct_articles", "highest_article", "missing_article_numbers", "first_missing",
            "table_pages", "first_table_pages",
        ):
            print(f"{key:24} {r[key]}")
        for preview in r["table_previews"]:
            print(f"{'table preview':24} {preview[:300]}")

    manifest = Path(paths[0]).parent / "manifest.json"
    manifest.write_text(
        json.dumps({"checked_on": date.today().isoformat(), "sources": reports},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nManifest written to {manifest}")


if __name__ == "__main__":
    main(sys.argv[1:])
