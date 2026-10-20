"""Articles -> chunks for retrieval.

One chunk = one article, so the unit we retrieve is the unit we cite. Only
articles longer than MAX_CHARS are split, at their own paragraph markers
(I.-, then A.-, then 1°-), never inside a paragraph. As in the article
splitter, markers must follow their sequence (I, II, III...), so a body line
that happens to start with "II-B ci-dessus" is not taken for a paragraph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

MAX_CHARS = 8000  # articles longer than this are split
PACK_CHARS = 2000  # small consecutive paragraphs of a split article are merged up to this
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

# Each level: a regex capturing the marker at the start of a line, and the
# function giving the marker expected after a given one.
LEVELS: list[tuple[re.Pattern, Callable[[str | None], str]]] = [
    (re.compile(r"^([IVX]+)\s*\.?\s*-", re.M),
     lambda prev: ROMAN[ROMAN.index(prev) + 1] if prev else "I"),
    (re.compile(r"^([A-H])\s*\.?\s*-", re.M),
     lambda prev: chr(ord(prev) + 1) if prev else "A"),
    (re.compile(r"^(\d+)\s*°", re.M),
     lambda prev: str(int(prev) + 1) if prev else "1"),
]


class Chunk(BaseModel):
    id: str  # "cgi-2026-art-73#2"
    article_id: str
    edition: int
    label: str  # "Article 73"
    title: str
    part: str | None = None  # "I-II" when the article is split: first-last marker
    chapter: str | None = None
    section: str | None = None
    pdf_pages: list[int]
    amendments: list[str]
    text: str

    def embedding_text(self) -> str:
        """Text sent to the embedding model: the headings give the context."""
        heading = f"{self.label} - {self.title}"
        context = " / ".join(h for h in (self.chapter, self.section) if h)
        return f"{heading}\n{context}\n{self.text}" if context else f"{heading}\n{self.text}"


def split_units(text: str, level: int = 0) -> list[tuple[str | None, str]]:
    """Split text into (marker, unit) at the first level whose markers follow their sequence."""
    if level >= len(LEVELS):
        return [(None, text)]
    regex, following = LEVELS[level]
    starts, markers, expected = [], [], following(None)
    for m in regex.finditer(text):
        if m.group(1) == expected:
            starts.append(m.start())
            markers.append(m.group(1))
            expected = following(m.group(1))
    if len(starts) < 2:
        return split_units(text, level + 1)

    units: list[tuple[str | None, str]] = []
    if text[: starts[0]].strip():  # preamble before the first marker
        units.append((None, text[: starts[0]].strip()))
    bounds = starts[1:] + [len(text)]
    for marker, start, end in zip(markers, starts, bounds):
        unit = text[start:end].strip()
        if len(unit) > MAX_CHARS:  # too long: go one level down inside it
            units += [(marker if sub is None else f"{marker}-{sub}", t)
                      for sub, t in split_units(unit, level + 1)]
        else:
            units.append((marker, unit))
    return units


def pack(units: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    """Merge consecutive units while the result stays under PACK_CHARS."""
    packed: list[tuple[list[str], list[str]]] = []
    for marker, text in units:
        if packed and len("\n".join(packed[-1][1])) + 1 + len(text) <= PACK_CHARS:
            packed[-1][1].append(text)
            if marker:
                packed[-1][0].append(marker)
        else:
            packed.append(([marker] if marker else [], [text]))
    return [
        ("-".join(dict.fromkeys([m[0], m[-1]])) if m else None, "\n".join(t))
        for m, t in packed
    ]


def article_chunks(article: dict) -> list[Chunk]:
    common = dict(
        article_id=article["id"], edition=article["edition"], label=article["label"],
        title=article["title"], chapter=article["chapter"], section=article["section"],
        pdf_pages=article["pdf_pages"], amendments=article["amendments"],
    )
    text = article["text"]
    if len(text) <= MAX_CHARS:
        return [Chunk(id=article["id"], text=text, **common)]
    return [
        Chunk(id=f"{article['id']}#{i}", part=part, text=part_text, **common)
        for i, (part, part_text) in enumerate(pack(split_units(text)), start=1)
    ]


def load_chunks(jsonl: Path) -> list[Chunk]:
    articles = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    return [chunk for a in articles if not a["abrogated"] for chunk in article_chunks(a)]
