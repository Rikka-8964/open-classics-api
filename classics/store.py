"""In-memory corpus store with explicit relevance ranking."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Iterable

__version__ = "0.1.0"

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(os.path.dirname(_HERE), "data", "works.json")

# Relevance weights. Deliberately explicit so ranking is easy to reason about.
W_TITLE_EXACT = 1000
W_TITLE_PARTIAL = 300
W_AUTHOR = 200
W_TAG_EXACT = 160
W_TAG_PARTIAL = 120
W_CONTENT = 100
W_NOTE = 40
W_GENRE = 60
W_DYNASTY = 60


def _norm(value: Any) -> str:
    """Normalise text for comparison: lowercase, collapse whitespace."""
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


class ClassicsStore:
    """Loads the corpus once and answers queries against it.

    The store is read-only after construction, which makes it safe to share
    across threads — the HTTP layer relies on this.
    """

    def __init__(self, data_path: str | None = None) -> None:
        self.data_path = data_path or DEFAULT_DATA_PATH
        with open(self.data_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        self.meta: dict[str, Any] = raw.get("meta", {})
        self.works: list[dict[str, Any]] = raw.get("works", [])

        # Pre-compute the searchable text of every work exactly once.
        self._by_id: dict[str, dict[str, Any]] = {}
        self._search_index: dict[str, dict[str, str]] = {}
        for work in self.works:
            wid = work["id"]
            self._by_id[wid] = work
            self._search_index[wid] = {
                "title": _norm(work.get("title")),
                "author": _norm(work.get("author")),
                "dynasty": _norm(work.get("dynasty")),
                "genre": _norm(work.get("genre")),
                "content": _norm("".join(work.get("content", []))),
                "note": _norm(work.get("note")),
                "tags": " ".join(_norm(t) for t in work.get("tags", [])),
            }

    # ------------------------------------------------------------------ basics

    def get(self, work_id: str) -> dict[str, Any] | None:
        return self._by_id.get(work_id)

    def all_ids(self) -> list[str]:
        return [w["id"] for w in self.works]

    def facets(self) -> dict[str, list[dict[str, Any]]]:
        """Value counts for every filterable dimension."""
        return {
            "authors": self._count("author"),
            "dynasties": self._count("dynasty"),
            "genres": self._count("genre"),
            "tags": self._count_flat("tags"),
        }

    def _count(self, field: str) -> list[dict[str, Any]]:
        counter = Counter(w.get(field, "") for w in self.works)
        return [
            {"value": value, "count": count}
            for value, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def _count_flat(self, field: str) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for work in self.works:
            counter.update(work.get(field, []))
        return [
            {"value": value, "count": count}
            for value, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def stats(self) -> dict[str, Any]:
        facets = self.facets()
        total_lines = sum(len(w.get("content", [])) for w in self.works)
        total_chars = sum(len("".join(w.get("content", []))) for w in self.works)
        return {
            "works": len(self.works),
            "authors": len(facets["authors"]),
            "dynasties": len(facets["dynasties"]),
            "genres": len(facets["genres"]),
            "tags": len(facets["tags"]),
            "lines": total_lines,
            "characters": total_chars,
            "dataset_version": self.meta.get("version"),
            "dataset_license": self.meta.get("license"),
        }

    # ------------------------------------------------------------------ search

    def _score(self, work_id: str, terms: list[str]) -> int:
        """Score one work against a list of query terms.

        Every term must match somewhere (logical AND); the returned score is the
        sum of the per-term best-match weights. A work that fails to match any
        single term scores 0 and is dropped.
        """
        idx = self._search_index[work_id]
        total = 0
        for term in terms:
            best = 0
            if idx["title"] == term:
                best = W_TITLE_EXACT
            elif term in idx["title"]:
                best = W_TITLE_PARTIAL
            if term in idx["author"]:
                best = max(best, W_AUTHOR)
            if term in idx["tags"]:
                best = max(best, W_TAG_EXACT if term == idx["tags"] else W_TAG_PARTIAL)
            if term in idx["content"]:
                best = max(best, W_CONTENT)
            if term in idx["genre"]:
                best = max(best, W_GENRE)
            if term in idx["dynasty"]:
                best = max(best, W_DYNASTY)
            if term in idx["note"]:
                best = max(best, W_NOTE)
            if best == 0:
                return 0
            total += best
        return total

    def search(
        self,
        q: str | None = None,
        author: str | None = None,
        dynasty: str | None = None,
        genre: str | None = None,
        tag: str | None = None,
        page: int = 1,
        limit: int = 20,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        """Filter + rank + paginate. Returns a JSON-serialisable page object."""
        candidates: Iterable[dict[str, Any]] = self.works

        # Cheap exact-match filters first, so scoring only runs on survivors.
        if author:
            wanted = _norm(author)
            candidates = [w for w in candidates if _norm(w.get("author")) == wanted]
        if dynasty:
            wanted = _norm(dynasty)
            candidates = [w for w in candidates if _norm(w.get("dynasty")) == wanted]
        if genre:
            wanted = _norm(genre)
            candidates = [w for w in candidates if _norm(w.get("genre")) == wanted]
        if tag:
            wanted = _norm(tag)
            candidates = [
                w for w in candidates if wanted in [_norm(t) for t in w.get("tags", [])]
            ]

        candidates = list(candidates)
        terms = _norm(q).split() if q else []

        if terms:
            scored = []
            for work in candidates:
                score = self._score(work["id"], terms)
                if score > 0:
                    scored.append((score, work))
            scored.sort(key=lambda pair: (-pair[0], pair[1]["title"]))
            ordered = [work for _, work in scored]
        else:
            ordered = sorted(candidates, key=lambda w: (w.get("dynasty", ""), w.get("author", ""), w.get("title", "")))

        if sort == "title":
            ordered = sorted(ordered, key=lambda w: w.get("title", ""))
        elif sort == "author":
            ordered = sorted(ordered, key=lambda w: (w.get("author", ""), w.get("title", "")))
        elif sort == "dynasty":
            ordered = sorted(ordered, key=lambda w: (w.get("dynasty", ""), w.get("author", "")))

        total = len(ordered)
        page = max(1, int(page or 1))
        limit = max(1, min(int(limit or 20), 100))
        start = (page - 1) * limit
        window = ordered[start : start + limit]

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if total else 0,
            "items": [self._summary(w) for w in window],
        }

    @staticmethod
    def _summary(work: dict[str, Any]) -> dict[str, Any]:
        """Compact representation used in list endpoints."""
        return {
            "id": work["id"],
            "title": work.get("title"),
            "author": work.get("author"),
            "dynasty": work.get("dynasty"),
            "genre": work.get("genre"),
            "tags": work.get("tags", []),
            "excerpt": "".join(work.get("content", []))[:40],
        }

    def random(self, tag: str | None = None, dynasty: str | None = None, seed: int | None = None) -> dict[str, Any] | None:
        """Return one random work, optionally constrained."""
        import random as _random

        pool = self.works
        if tag:
            wanted = _norm(tag)
            pool = [w for w in pool if wanted in [_norm(t) for t in w.get("tags", [])]]
        if dynasty:
            wanted = _norm(dynasty)
            pool = [w for w in pool if _norm(w.get("dynasty")) == wanted]
        if not pool:
            return None
        rng = _random.Random(seed) if seed is not None else _random
        return rng.choice(pool)
