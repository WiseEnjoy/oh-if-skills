import importlib.util
import json
import sys
from pathlib import Path
import unittest


VENDOR = Path(__file__).resolve().parents[1] / "scripts" / "vendor" / "inference-radar"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    vendor_dir = str(path.parent)
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    spec.loader.exec_module(module)
    return module


class SkillTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_tags = load(VENDOR / "skill_tags.py", "test_skill_tags")

    def test_map_domains_have_unique_tags_and_skills(self):
        skill_map = self.skill_tags.load_map()
        tags = self.skill_tags.valid_tags(skill_map)
        bare = {domain["tag"] for domain in skill_map["domains"]}
        self.assertEqual(len(bare), len(skill_map["domains"]), "duplicate domain tags")
        self.assertTrue(all(tag in tags for tag in bare))

    def test_pair_tags_reduce_to_domain(self):
        self.assertEqual(self.skill_tags.normalize_tag("quantization/mxfp"), "quantization")
        self.assertEqual(self.skill_tags.normalize_tag("kv-cache"), "kv-cache")

    def test_validate_item_tags_rejects_unknown(self):
        skill_map = self.skill_tags.load_map()
        self.assertEqual(self.skill_tags.validate_item_tags({"skill_tags": ["quantization/mxfp"]}, skill_map), [])
        bad = self.skill_tags.validate_item_tags({"skill_tags": ["not-a-domain"]}, skill_map)
        self.assertEqual(bad, ["not-a-domain"])

    def test_coverage_aggregates_and_reports_zero_domains(self):
        skill_map = self.skill_tags.load_map()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inference-radar-curated-2026-09-22.json"
            path.write_text(json.dumps({
                "date": "2026-09-22",
                "items": [
                    {"title": "a", "url": "https://a", "skill_tags": ["quantization/mxfp"]},
                    {"title": "b", "url": "https://b", "skill_tags": ["quantization", "profiling/tooling"]},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            coverage = self.skill_tags.coverage_from_curated_dirs([path], skill_map)
        by_tag = {d["tag"]: d for d in coverage["domains"]}
        self.assertEqual(by_tag["quantization"]["read_count"], 2)
        self.assertEqual(by_tag["profiling"]["read_count"], 1)
        self.assertEqual(by_tag["kv-cache"]["read_count"], 0)
        self.assertIn("kv-cache", coverage["zero_coverage_domains"])
        self.assertEqual(coverage["total_tagged_items"], 3)


class VerificationLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = load(VENDOR / "verification_ledger.py", "test_verification_ledger")

    def test_update_appends_and_carries(self):
        ledger = {"schema_version": 1, "actions": [
            {"title": "old action", "detail": "do the thing carefully and thoroughly", "evidence_urls": ["https://a"],
             "added_at": "2026-09-20", "last_seen_at": "2026-09-20", "status": "open"},
        ]}
        today_actions = [
            {"title": "new action", "detail": "a brand new action for today with enough detail",
             "evidence_urls": ["https://b"]},
            {"title": "old action", "detail": "do the thing carefully and thoroughly", "evidence_urls": ["https://a"]},
        ]
        updated, carried = self.ledger.update(ledger, today_actions, "2026-09-22")
        titles = [a["title"] for a in updated["actions"]]
        self.assertEqual(titles, ["old action", "new action"], "re-raised action must not duplicate")
        self.assertEqual([c["title"] for c in carried], ["old action"])
        self.assertEqual(updated["actions"][0]["last_seen_at"], "2026-09-22")

    def test_auto_drop_after_max_age(self):
        ledger = {"schema_version": 1, "actions": [
            {"title": "stale", "detail": "this action has been open for far too long now",
             "evidence_urls": [], "added_at": "2026-08-25", "status": "open"},
        ]}
        updated, carried = self.ledger.update(ledger, [], "2026-09-22")
        self.assertEqual(updated["actions"][0]["status"], "dropped")
        self.assertEqual(carried, [])

    def test_close_by_title_substring(self):
        ledger = {"schema_version": 1, "actions": [
            {"title": "建立量化精度回归清单", "detail": "collect golden inputs and thresholds",
             "evidence_urls": [], "added_at": "2026-09-21", "status": "open"},
        ]}
        self.assertTrue(self.ledger.close(ledger, "量化精度回归", "2026-09-22"))
        self.assertEqual(ledger["actions"][0]["status"], "done")

    def test_stats_counts(self):
        ledger = {"schema_version": 1, "actions": [
            {"title": "a", "detail": "x", "status": "open", "added_at": "2026-09-19"},
            {"title": "b", "detail": "y", "status": "done", "added_at": "2026-09-18"},
        ]}
        stats = self.ledger.stats(ledger, "2026-09-22")
        self.assertEqual(stats["open"], 1)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["oldest_open_days"], 3)


if __name__ == "__main__":
    unittest.main()
