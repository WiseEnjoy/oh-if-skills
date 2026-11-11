import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest


VENDOR = Path(__file__).resolve().parents[1] / "scripts" / "vendor" / "inference-radar"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    # Sibling imports (prepare_candidates imports build_report) resolve inside vendor/.
    vendor_dir = str(path.parent)
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    spec.loader.exec_module(module)
    return module


class SourceRegistryTests(unittest.TestCase):
    """Source registries must stay duplicate-free and mutually consistent."""

    @classmethod
    def setUpClass(cls):
        cls.fetch_updates = load(VENDOR / "fetch_updates.py", "test_fetch_updates")
        cls.fetch_web = load(VENDOR / "fetch_web_sources.py", "test_fetch_web_sources")
        cls.build_report = load(VENDOR / "build_report.py", "test_build_report")
        cls.quality_audit = load(VENDOR / "quality_audit.py", "test_quality_audit")
        cls.prepare = load(VENDOR / "prepare_candidates.py", "test_prepare_candidates")

    def test_no_duplicate_source_keys(self):
        for name, sources in (
            ("fetch_updates", self.fetch_updates.SOURCES),
            ("fetch_web_sources", self.fetch_web.SOURCES),
        ):
            keys = [source["key"] for source in sources]
            duplicates = [key for key in set(keys) if keys.count(key) > 1]
            self.assertEqual(duplicates, [], f"{name} duplicate keys: {duplicates}")

    def test_reference_engine_sources_registered(self):
        expected = {"tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp"}
        fetch_keys = {source["key"] for source in self.fetch_updates.SOURCES}
        self.assertTrue(expected <= fetch_keys, f"missing engine sources: {expected - fetch_keys}")
        self.assertTrue(expected <= self.build_report.TIER_SOURCES["tier2"])
        self.assertTrue(expected <= self.quality_audit.CATEGORY_SOURCES["engines"])
        for key in expected:
            self.assertIn(key, self.build_report.SOURCE_WEIGHT)

    def test_reference_web_sources_registered(self):
        expected = {"huggingface-papers", "semianalysis", "interconnects", "qwen-blog"}
        fetch_keys = {source["key"] for source in self.fetch_web.SOURCES}
        self.assertTrue(expected <= fetch_keys, f"missing web sources: {expected - fetch_keys}")
        for key in expected:
            source = next(s for s in self.fetch_web.SOURCES if s["key"] == key)
            category = source["category"]
            self.assertIn(key, self.quality_audit.CATEGORY_SOURCES[category])
            self.assertIn(key, self.prepare.BROAD_SOURCE_KEYS)

    def test_body_excerpt_in_public_fields(self):
        self.assertIn("body_excerpt", self.prepare.public_fields({"score": 0, "theme": "", "tier": "", "duplicate_count": 1}))


class BodyExcerptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fetch_updates = load(VENDOR / "fetch_updates.py", "test_fetch_updates_body")

    def test_strip_code_blocks_removes_fences_and_collapses_whitespace(self):
        raw = "## Context\nRepro on A3:\n```python\nraise ValueError('boom')\n```\nSee  **dtype** fp8.\n"
        cleaned = self.fetch_updates.strip_code_blocks(raw)
        self.assertNotIn("raise ValueError", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("Repro on A3:", cleaned)
        self.assertIn("dtype", cleaned)

    def test_normalize_common_item_keeps_excerpt(self):
        raw = {
            "id": 1,
            "number": 42,
            "title": "[fix] stale float in cached graph",
            "url": "https://github.com/pytorch/pytorch/issues/42",
            "state": "open",
            "created_at": "2026-09-22T01:00:50Z",
            "body": "Steps:\n```\nmini repro\n```\nFix by marking scalars as graph inputs.",
        }
        source = {"key": "pytorch", "name": "PyTorch", "category": "frameworks"}
        cutoff = self.fetch_updates.now_utc().replace(year=2025)
        item = self.fetch_updates.normalize_common_item(raw, item_type="issue", source=source, cutoff=cutoff)
        self.assertIsNotNone(item)
        self.assertIn("Fix by marking scalars as graph inputs.", item["body_excerpt"])
        self.assertNotIn("mini repro", item["body_excerpt"])


class MergeInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_report = load(VENDOR / "build_report.py", "test_build_report_merge")

    def test_token_presence_survives_inputs_without_that_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            github_input = root / "github.json"
            cann_input = root / "cann.json"
            github_input.write_text(json.dumps({"github_token_present": True}), encoding="utf-8")
            cann_input.write_text(json.dumps({"gitcode_token_present": True}), encoding="utf-8")

            merged = self.build_report.merge_inputs([github_input, cann_input])

        self.assertTrue(merged["github_token_present"])
        self.assertTrue(merged["gitcode_token_present"])


class HistoryMarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markers = load(VENDOR / "history_markers.py", "test_history_markers")

    def test_seen_flag_hits_exact_repeat_and_misses_new_item(self):
        seen_keys = {("pytorch", self.markers._normalize("[pt2] stale float"))}
        seen_urls = {"https://github.com/pytorch/pytorch/issues/197889"}
        candidates = [
            {"source_key": "pytorch", "title": "[pt2] stale float", "url": "https://other.example/x"},
            {"source_key": "pytorch", "title": "different title", "url": seen_urls.pop()},
            {"source_key": "pytorch", "title": "brand new", "url": "https://example.com/new"},
        ]
        self.markers.apply_history_markers(candidates, seen_keys, seen_urls | {"https://github.com/pytorch/pytorch/issues/197889"})
        self.assertTrue(candidates[0]["seen_before"])
        self.assertTrue(candidates[1]["seen_before"])
        self.assertFalse(candidates[2]["seen_before"])
        self.assertIn("curation_hint", candidates[0])


class ParallelFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fetch_updates = load(VENDOR / "fetch_updates.py", "test_fetch_updates_parallel")
        cls.fetch_web = load(VENDOR / "fetch_web_sources.py", "test_fetch_web_parallel")

    def test_workers_argument_is_wired(self):
        updates_args = self.fetch_updates.parse_args.__doc__ or ""
        # parse_args uses argparse; verify the flag exists instead of invoking it.
        import argparse
        parser = argparse.ArgumentParser()
        self.fetch_updates.parse_args  # attribute exists
        source_text = (VENDOR / "fetch_updates.py").read_text(encoding="utf-8")
        self.assertIn("--workers", source_text)
        self.assertIn("ThreadPoolExecutor", source_text)
        web_text = (VENDOR / "fetch_web_sources.py").read_text(encoding="utf-8")
        self.assertIn("--workers", web_text)
        self.assertIn("ThreadPoolExecutor", web_text)


if __name__ == "__main__":
    unittest.main()
