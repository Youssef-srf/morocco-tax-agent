"""Split the income-tax title (Titre II) of the official CGI PDF into articles.

Usage:
    uv run python -m morocco_tax_agent.sources.cgi data/raw/cgi_2026_fr.pdf --edition 2026

Design choices (the ones to explain in an interview):
- One chunk = one article. A tax answer must cite "article 73", so the unit
  we retrieve is the unit we cite. Long articles are split later, at
  indexing time, by paragraph (I.-, II.-), never mid-paragraph.
- Body text and footnotes are separated by font size (body 11-12 pt,
  footnotes, footnote calls, running header and page number below 9 pt).
  Footnote calls are glued to words ("Article 47290.-" is article 47 +
  footnote 290), so regexes alone would misread them.
- Footnotes are not thrown away: in the CGI they record which finance law
  last changed the article. They are kept as `amendments` metadata.
- The title boundaries are found by their headings ("L'IMPOT SUR LE REVENU"
  up to the next "TITRE"), not by page numbers, so the 2027 edition can be
  parsed without code changes.
- Article numbers must increase. A line that looks like a heading but
  would go backwards is body text, and a gap in the numbering fails loudly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pdfplumber
from pydantic import BaseModel

BODY_MIN_SIZE = 9.0  # pt; below = footnotes, calls, running header, page number
SUFFIXES = ["bis", "ter", "quater", "quinquies", "sexies", "septies", "octies"]

START_TITLE = re.compile(r"^L[’']IMPOT SUR LE REVENU$")
END_TITLE = re.compile(r"^TITRE\b")  # the next title (TVA) ends the income-tax title
ARTICLE = re.compile(
    rf"^Article\s+(\d+)(?:\s+({'|'.join(SUFFIXES)}))?\s*\.?\s*-\s*([A-ZÉÈÀÂÎÔ(].*)$"
)
CHAPTER = re.compile(r"^CHAPITRE\s+\S+")
SECTION = re.compile(r"^(?:Section|SECTION)\s+[IVX]+\s*\.?-\s*\S")
PARAGRAPH = re.compile(r"^Paragraphe\s+[IVX]+\s*\.?-\s*\S")
FOOTNOTE_START = re.compile(r"^(\d+)\s+(\D.*)$")


class Article(BaseModel):
    id: str  # "cgi-2026-art-42-bis"
    source: str = "CGI"
    edition: int
    number: int
    suffix: str | None = None
    label: str  # "Article 42 bis"
    title: str
    chapter: str | None = None
    section: str | None = None
    paragraph: str | None = None
    pdf_pages: list[int]
    text: str
    amendments: list[str] = []
    abrogated: bool = False

    @property
    def key(self) -> tuple[int, int]:
        return article_key(self.number, self.suffix)


def article_key(number: int, suffix: str | None) -> tuple[int, int]:
    return number, (SUFFIXES.index(suffix) + 1) if suffix else 0


# --------------------------------------------------------------------------- #
# Page reading
# --------------------------------------------------------------------------- #

def _is_body(obj: dict) -> bool:
    return obj.get("object_type") != "char" or obj["size"] >= BODY_MIN_SIZE


def _is_small(obj: dict) -> bool:
    return obj.get("object_type") == "char" and obj["size"] < BODY_MIN_SIZE


def read_page(page) -> tuple[list[dict], list[tuple[int, float]], dict[int, str]]:
    """Return (body lines with their top, footnote calls with their top, footnote texts)."""
    body = [
        {"text": line["text"].strip(), "top": line["top"]}
        for line in page.filter(_is_body).extract_text_lines()
        if line["text"].strip()
    ]

    small_lines = page.filter(_is_small).extract_text_lines()
    footnotes: dict[int, str] = {}
    footnote_top = float("inf")
    current = None
    for line in small_lines:
        text = line["text"].strip()
        m = FOOTNOTE_START.match(text)
        if m:
            current = int(m.group(1))
            footnotes[current] = m.group(2).strip()
            footnote_top = min(footnote_top, line["top"])
        elif current is not None and not text.isdigit():
            footnotes[current] += " " + text  # footnote wrapped on two lines

    calls = []
    for line in small_lines:
        if line["top"] >= footnote_top:
            continue
        for token in line["text"].split():
            if token.isdigit():
                calls.append((int(token), line["top"]))
    return body, calls, footnotes


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def _clean(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"[]\s*", "- ", text)  # bullets of the Symbol font, private Unicode area
    text = re.sub(r"[ \t]+([.,])", r"\1", text)  # "surplus ." left by a removed call
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def parse_income_tax_title(pdf_path: Path, edition: int) -> list[Article]:
    articles: list[dict] = []
    chapter = section = paragraph = None
    pending_heading: str | None = None  # "chapter" | "paragraph" title continued on next line
    inside = done = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            body, calls, footnotes = read_page(page)
            headings_on_page: list[tuple[float, dict]] = []

            for i, line in enumerate(body):
                text = line["text"]
                if not inside:
                    inside = bool(START_TITLE.match(text))
                    continue
                if END_TITLE.match(text):
                    done = True
                    break

                if pending_heading == "chapter":
                    chapter = f"{chapter} – {text}"
                    pending_heading = None
                    continue
                if pending_heading == "paragraph":
                    pending_heading = None
                    if not ARTICLE.match(text):
                        paragraph = f"{paragraph} {text}"
                        continue

                if CHAPTER.match(text):
                    chapter, section, paragraph = text, None, None
                    pending_heading = "chapter"
                    continue
                if SECTION.match(text):
                    section, paragraph = text, None
                    continue
                if PARAGRAPH.match(text):
                    paragraph = text
                    nxt = body[i + 1]["text"] if i + 1 < len(body) else ""
                    if nxt and nxt[0].islower():
                        pending_heading = "paragraph"
                    continue

                m = ARTICLE.match(text)
                if m:
                    number, suffix, title = int(m.group(1)), m.group(2), m.group(3).strip()
                    if not articles or article_key(number, suffix) > articles[-1]["key"]:
                        label = f"Article {number}" + (f" {suffix}" if suffix else "")
                        article = {
                            "key": article_key(number, suffix),
                            "number": number,
                            "suffix": suffix,
                            "label": label,
                            "title": title,
                            "chapter": chapter,
                            "section": section,
                            "paragraph": paragraph,
                            "pages": [page_no],
                            "lines": [],
                            "calls": [],
                        }
                        articles.append(article)
                        headings_on_page.append((line["top"], article))
                        continue

                if articles:
                    current = articles[-1]
                    current["lines"].append(text)
                    if page_no not in current["pages"]:
                        current["pages"].append(page_no)

            # Attach each footnote call to the article it appears in.
            for number, top in calls:
                owner = None
                for heading_top, article in headings_on_page:
                    if heading_top <= top + 4:  # calls sit slightly above the baseline
                        owner = article
                if owner is None and articles:
                    owner = next(
                        (a for a in reversed(articles) if a["pages"][0] < page_no), None
                    )
                if owner is not None and number in footnotes:
                    owner["calls"].append(footnotes[number])

            if done:
                break

    return [
        Article(
            id=f"cgi-{edition}-art-{a['number']}" + (f"-{a['suffix']}" if a["suffix"] else ""),
            edition=edition,
            number=a["number"],
            suffix=a["suffix"],
            label=a["label"],
            title=a["title"],
            chapter=a["chapter"],
            section=a["section"],
            paragraph=a["paragraph"],
            pdf_pages=a["pages"],
            text=_clean(a["lines"]),
            amendments=list(dict.fromkeys(a["calls"])),
            abrogated=a["title"].lower().startswith("(abrogé"),
        )
        for a in articles
    ]


def check_numbering(articles: list[Article]) -> list[int]:
    """Return the article numbers missing between the first and the last."""
    numbers = {a.number for a in articles}
    return [n for n in range(min(numbers), max(numbers) + 1) if n not in numbers]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--edition", type=int, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    out = args.out or Path("data/processed") / f"cgi_{args.edition}_ir_articles.jsonl"
    articles = parse_income_tax_title(args.pdf, args.edition)
    missing = check_numbering(articles)
    if missing:
        raise SystemExit(f"Numbering gap, articles not found: {missing}")

    sha256 = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for article in articles:
            record = article.model_dump() | {"source_sha256": sha256}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    longest = sorted(articles, key=lambda a: len(a.text), reverse=True)[:3]
    print(f"{len(articles)} articles ({articles[0].label} -> {articles[-1].label}), "
          f"{sum(a.abrogated for a in articles)} abrogés, written to {out}")
    print("Longest:", ", ".join(f"{a.label} ({len(a.text)} chars)" for a in longest))


if __name__ == "__main__":
    main()
