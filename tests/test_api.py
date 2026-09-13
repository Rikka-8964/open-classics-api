"""Tests for open-classics-api.

Run with:  python -m unittest discover -s tests -v

The suite covers the store in isolation plus the HTTP surface, so a broken
route or a ranking regression fails loudly instead of silently shipping.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402
from classics import ClassicsStore  # noqa: E402


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = ClassicsStore()

    def test_corpus_is_not_empty(self) -> None:
        self.assertGreater(len(self.store.works), 30)

    def test_ids_are_unique(self) -> None:
        ids = self.store.all_ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_work_has_required_fields(self) -> None:
        for work in self.store.works:
            for field in ("id", "title", "author", "dynasty", "genre", "content", "tags"):
                self.assertIn(field, work, f"{work.get('id')} is missing {field}")
            self.assertTrue(work["content"], f"{work['id']} has empty content")

    def test_search_by_title_ranks_exact_match_first(self) -> None:
        page = self.store.search(q="静夜思")
        self.assertGreater(page["total"], 0)
        self.assertEqual(page["items"][0]["title"], "静夜思")

    def test_search_by_author(self) -> None:
        page = self.store.search(q="杜甫")
        self.assertGreater(page["total"], 0)
        for item in page["items"]:
            self.assertEqual(item["author"], "杜甫")

    def test_search_matches_poem_body(self) -> None:
        page = self.store.search(q="润物细无声")
        self.assertEqual(page["items"][0]["title"], "春夜喜雨")

    def test_multi_term_query_is_and(self) -> None:
        both = self.store.search(q="李白 思乡")
        self.assertGreater(both["total"], 0)
        only_li = self.store.search(q="李白")
        self.assertLess(both["total"], only_li["total"])

    def test_dynasty_filter(self) -> None:
        page = self.store.search(dynasty="宋", limit=100)
        self.assertGreater(page["total"], 0)
        for item in page["items"]:
            self.assertEqual(item["dynasty"], "宋")

    def test_tag_filter(self) -> None:
        page = self.store.search(tag="思乡", limit=100)
        self.assertGreater(page["total"], 0)
        for item in page["items"]:
            self.assertIn("思乡", item["tags"])

    def test_pagination_does_not_overlap(self) -> None:
        first = self.store.search(limit=5, page=1)
        second = self.store.search(limit=5, page=2)
        ids_a = {i["id"] for i in first["items"]}
        ids_b = {i["id"] for i in second["items"]}
        self.assertEqual(ids_a & ids_b, set())

    def test_limit_is_clamped(self) -> None:
        page = self.store.search(limit=9999)
        self.assertLessEqual(page["limit"], 100)

    def test_unknown_query_returns_empty_page(self) -> None:
        page = self.store.search(q="zzzzzzzz")
        self.assertEqual(page["total"], 0)
        self.assertEqual(page["items"], [])

    def test_random_is_deterministic_with_seed(self) -> None:
        a = self.store.random(seed=42)
        b = self.store.random(seed=42)
        self.assertIsNotNone(a)
        self.assertEqual(a["id"], b["id"])

    def test_facets_and_stats(self) -> None:
        facets = self.store.facets()
        for key in ("authors", "dynasties", "genres", "tags"):
            self.assertTrue(facets[key], f"facet {key} is empty")
        stats = self.store.stats()
        self.assertEqual(stats["works"], len(self.store.works))
        self.assertGreater(stats["characters"], 0)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path: str):
        return json.loads(urlopen(f"http://127.0.0.1:{self.port}{path}").read().decode("utf-8"))

    def test_health(self) -> None:
        self.assertEqual(self.get("/api/health")["status"], "ok")

    def test_stats_endpoint(self) -> None:
        payload = self.get("/api/stats")
        self.assertIn("corpus", payload)
        self.assertIn("service", payload)

    def test_works_endpoint(self) -> None:
        payload = self.get("/api/works?q=%E6%98%8E%E6%9C%88")  # 明月
        self.assertGreater(payload["total"], 0)

    def test_work_by_id(self) -> None:
        payload = self.get("/api/works/tang-jingyesi")
        self.assertEqual(payload["title"], "静夜思")

    def test_missing_work_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self.get("/api/works/does-not-exist")
        self.assertEqual(ctx.exception.code, 404)

    def test_random_endpoint(self) -> None:
        payload = self.get("/api/random?seed=1")
        self.assertIn("id", payload)

    def test_facets_endpoint(self) -> None:
        payload = self.get("/api/tags")
        self.assertTrue(payload["items"])

    def test_openapi_document(self) -> None:
        payload = self.get("/api/openapi.json")
        self.assertEqual(payload["openapi"], "3.1.0")
        self.assertIn("/api/works", payload["paths"])

    def test_unknown_api_route_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self.get("/api/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_cors_header_present(self) -> None:
        resp = urlopen(f"http://127.0.0.1:{self.port}/api/health")
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")


if __name__ == "__main__":
    unittest.main(verbosity=2)
