from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.request import urlopen

from orca_gitcode_linker import linker

SHA = "6f900976935624274dc1609e80d17d19058d74a9"


def raw_pull(number: int, state: str, branch: str, updated: str, **extra: Any) -> dict[str, Any]:
    pull = {
        "number": number,
        "title": f"PR {number}",
        "state": state,
        "draft": False,
        "html_url": f"https://gitcode.com/acme/app/merge_requests/{number}",
        "updated_at": updated,
        "head": {"ref": branch, "label": branch, "sha": SHA},
        "base": {"ref": "main"},
        "mergeable": True,
    }
    pull.update(extra)
    return pull


class MappingTests(unittest.TestCase):
    def test_merged_state_is_closed_and_merged(self) -> None:
        mapped = linker.map_pull("acme", "app", raw_pull(7, "merged", "feat/a", "2026-11-25T10:00:00+08:00"))
        assert mapped is not None
        self.assertEqual(mapped["state"], "closed")
        self.assertTrue(mapped["merged"])
        self.assertEqual(mapped["head"]["ref"], "feat/a")
        self.assertEqual(mapped["html_url"], "https://gitcode.com/acme/app/merge_requests/7")

    def test_open_draft_and_fallback_url(self) -> None:
        raw = raw_pull(8, "open", "feat/b", "2026-11-25T10:00:00+08:00", draft=True)
        raw.pop("html_url")
        mapped = linker.map_pull("acme", "app", raw)
        assert mapped is not None
        self.assertEqual(mapped["state"], "open")
        self.assertFalse(mapped["merged"])
        self.assertTrue(mapped["draft"])
        self.assertEqual(mapped["html_url"], "https://gitcode.com/acme/app/pulls/8")

    def test_invalid_rows_are_skipped(self) -> None:
        self.assertIsNone(linker.map_pull("acme", "app", {}))
        self.assertIsNone(linker.map_pull("acme", "app", {"number": 1, "title": ""}))
        self.assertIsNone(linker.map_pull("acme", "app", {"number": "1", "title": "x"}))


class CacheTests(unittest.TestCase):
    def test_list_filters_states_and_sorts_recent_first(self) -> None:
        rows = [
            raw_pull(1, "closed", "old", "2026-01-01T00:00:00+08:00"),
            raw_pull(2, "merged", "newer", "2026-11-25T10:00:00+08:00", merged_at="2026-11-25T10:00:00+08:00"),
            raw_pull(3, "open", "active", "2026-11-26T10:00:00+08:00"),
        ]
        calls: list[dict[str, str]] = []

        def fetch(_path: str, params: dict[str, str]) -> Any:
            calls.append(dict(params))
            return rows

        config = linker.LinkerConfig(token="t", fork_pr_source="origin", fetch=fetch)
        cache = linker.TtlCache(60)
        meta_cache = linker.TtlCache(60)
        source_map = linker.TtlCache(60)
        closed = linker.load_pulls(config, cache, meta_cache, source_map, "acme", "app", "closed", 1, 50)
        self.assertEqual([pull["number"] for pull in closed], [2, 1])
        self.assertEqual(calls[0]["state"], "all")
        open_pulls = linker.load_pulls(config, cache, meta_cache, source_map, "acme", "app", "open", 1, 50)
        self.assertEqual([pull["number"] for pull in open_pulls], [3])
        self.assertEqual(calls[1]["state"], "open")
        linker.load_pulls(config, cache, meta_cache, source_map, "acme", "app", "closed", 1, 50)
        self.assertEqual(len(calls), 2)

    def test_fork_reads_parent_and_resolves_detail(self) -> None:
        origin_rows = [raw_pull(10, "open", "fork-only", "2026-11-25T10:00:00+08:00")]
        parent_rows = [
            raw_pull(
                1350,
                "merged",
                "fix/windows-drag-drop-after-install",
                "2026-11-20T10:00:00+08:00",
                merged_at="2026-11-20T10:00:00+08:00",
            )
        ]
        paths: list[str] = []

        def fetch(path: str, _params: dict[str, str]) -> Any:
            paths.append(path)
            if path == "/repos/acme/app":
                return {"fork": True, "parentfull_name": "upstream/app"}
            if path == "/repos/upstream/app":
                return {"fork": False}
            if path == "/repos/acme/app/pulls":
                return origin_rows
            if path == "/repos/upstream/app/pulls":
                return parent_rows
            if path == "/repos/upstream/app/pulls/1350":
                return parent_rows[0]
            raise AssertionError(path)

        config = linker.LinkerConfig(token="t", fetch=fetch)
        cache = linker.TtlCache(60)
        meta_cache = linker.TtlCache(60)
        source_map = linker.TtlCache(60)
        pulls = linker.load_pulls(config, cache, meta_cache, source_map, "acme", "app", "all", 1, 50)
        self.assertEqual([pull["number"] for pull in pulls], [10, 1350])
        detail = linker.load_pull(config, cache, meta_cache, source_map, "acme", "app", 1350)
        self.assertEqual(detail["head"]["ref"], "fix/windows-drag-drop-after-install")
        self.assertEqual(source_map.get("acme/app:1350"), "upstream/app")
        self.assertEqual(paths.count("/repos/acme/app"), 1)


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rows = [
            raw_pull(1, "open", "feat/a", "2026-11-25T10:00:00+08:00"),
            raw_pull(2, "merged", "feat/b", "2026-11-24T10:00:00+08:00", merged_at="2026-11-24T10:00:00+08:00"),
        ]

        def fetch(path: str, _params: dict[str, str]) -> Any:
            if path == "/repos/acme/app":
                return {"fork": False}
            if path.endswith("/pulls"):
                return rows
            if path.endswith("/pulls/1"):
                return rows[0]
            if path.endswith("/pulls/99"):
                raise linker.UpstreamError(404, "GitCode resource not found")
            raise AssertionError(path)

        cls.server = linker.LinkerServer(("127.0.0.1", 0), linker.LinkerConfig(token="t", fetch=fetch))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def get(self, path: str) -> tuple[int, Any]:
        try:
            with urlopen(self.base + path, timeout=5) as response:
                return response.status, json.loads(response.read())
        except Exception as error:  # noqa: BLE001 - test helper reads HTTPError status
            return error.code, json.loads(error.read())

    def test_health_version_and_user(self) -> None:
        status, payload = self.get("/api/v1/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = self.get("/api/v1/version")
        self.assertEqual(status, 200)
        self.assertEqual(payload["version"], "1.22.0")
        status, payload = self.get("/api/v1/user")
        self.assertEqual(status, 200)
        self.assertEqual(payload["login"], "gitcode")

    def test_list_and_detail(self) -> None:
        status, payload = self.get("/api/v1/repos/acme/app/pulls?state=all&page=1&limit=50")
        self.assertEqual(status, 200)
        self.assertEqual([pull["number"] for pull in payload], [1, 2])
        status, payload = self.get("/api/v1/repos/acme/app/pulls/1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["number"], 1)
        status, payload = self.get("/api/v1/repos/acme/app/pulls/99")
        self.assertEqual(status, 404)

    def test_status_is_neutral(self) -> None:
        status, payload = self.get(f"/api/v1/repos/acme/app/commits/{SHA}/status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "")
        self.assertEqual(payload["statuses"], [])

    def test_invalid_routes(self) -> None:
        self.assertEqual(self.get("/api/v1/repos/../app/pulls")[0], 400)
        self.assertEqual(self.get("/api/v1/repos/acme/app/pulls?state=bogus")[0], 400)
        self.assertEqual(self.get("/api/v1/repos/acme/app/commits/nope/status")[0], 400)
        self.assertEqual(self.get("/api/v1/nope")[0], 404)


class TokenTests(unittest.TestCase):
    def test_explicit_and_environment(self) -> None:
        self.assertEqual(linker.resolve_token("abc", None), ("abc", "--token"))
        with mock.patch.dict(os.environ, {"GC_TOKEN": "env"}, clear=True):
            self.assertEqual(linker.resolve_token(None, None), ("env", "GC_TOKEN"))

    def test_token_file_and_gc_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token"
            token_file.write_text("file-token\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(linker.resolve_token(None, str(token_file)), ("file-token", str(token_file)))
            config_dir = Path(directory) / ".config" / "gc"
            config_dir.mkdir(parents=True)
            (config_dir / "config.json").write_text(
                json.dumps({"accounts": {"alice": "account-token"}, "active_account": "alice"}),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(linker.Path, "home", return_value=Path(directory)),
            ):
                self.assertEqual(linker.resolve_token(None, None), ("account-token", str(config_dir / "config.json")))


if __name__ == "__main__":
    unittest.main()
