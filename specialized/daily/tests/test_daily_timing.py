import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = SKILL_ROOT / "scripts" / "run_daily.py"
RENDERER_PATHS = (
    SKILL_ROOT / "scripts" / "vendor" / "inference-radar" / "render_curated_report.py",
    SKILL_ROOT / "scripts" / "vendor" / "llm-inference-foundations" / "render_deep_report.py",
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TimingMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = load_module(WRAPPER_PATH, "test_daily_run_wrapper")

    def make_args(self, root: Path):
        return mock.Mock(
            date="2026-09-22",
            work_dir=root / "work",
            output_dir=root / "reports",
            radar_json=None,
            deep_json=None,
        )

    def test_successful_prepare_and_render_derive_end_to_end_timing(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = self.make_args(root)
            started = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

            self.wrapper.record_timing_event(
                args, "prepare", started, started + timedelta(seconds=100), 100, "success"
            )
            self.wrapper.record_timing_event(
                args,
                "render",
                started + timedelta(seconds=150),
                started + timedelta(seconds=180),
                30,
                "success",
            )

            path = args.work_dir / "daily-run-metrics-2026-09-22.json"
            metrics = self.wrapper.load_timing_metrics(path, args.date)
            self.assertEqual(len(metrics["events"]), 2)
            self.assertEqual(metrics["prepare_duration_seconds"], 100)
            self.assertEqual(metrics["render_duration_seconds"], 30)
            self.assertEqual(metrics["total_generation_seconds"], 180)
            self.assertEqual(metrics["curation_gap_seconds"], 50)
            self.assertEqual(metrics["performance_status"], "ok")
            self.assertIn("渲染 30.0 秒", self.wrapper.timing_display_text(metrics))

    def test_failed_render_is_recorded_and_does_not_invent_total_time(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = self.make_args(root)
            started = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
            self.wrapper.record_timing_event(
                args,
                "render",
                started,
                started + timedelta(seconds=2),
                2,
                "failed",
                "RuntimeError: renderer failed",
            )

            path = args.work_dir / "daily-run-metrics-2026-09-22.json"
            metrics = self.wrapper.load_timing_metrics(path, args.date)
            self.assertEqual(metrics["last_render"]["status"], "failed")
            self.assertEqual(metrics["last_render"]["error"], "RuntimeError: renderer failed")
            self.assertIsNone(metrics["render_duration_seconds"])
            self.assertIsNone(metrics["total_generation_seconds"])
            self.assertEqual(metrics["performance_status"], "unavailable")
            self.assertEqual(metrics["timing_unavailable_reason"], "prepare timing unavailable")

    def test_slow_end_to_end_run_is_flagged(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = self.make_args(root)
            started = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
            self.wrapper.record_timing_event(
                args, "prepare", started, started + timedelta(seconds=100), 100, "success"
            )
            self.wrapper.record_timing_event(
                args,
                "render",
                started + timedelta(seconds=600),
                started + timedelta(seconds=660),
                60,
                "success",
            )
            metrics = self.wrapper.load_timing_metrics(
                args.work_dir / "daily-run-metrics-2026-09-22.json", args.date
            )
            self.assertEqual(metrics["performance_status"], "slow")
            self.assertIn("性能：偏慢", self.wrapper.timing_display_text(metrics))

    def test_failure_cleanup_ignores_previous_html_without_placeholder(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "report.html"
            path.write_text("<p>previous report</p>", encoding="utf-8")
            self.wrapper.replace_generation_duration(
                path, "渲染失败 · 端到端未记录", required=False
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "<p>previous report</p>")


class RenderTimingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = load_module(WRAPPER_PATH, "test_daily_render_wrapper")

    def test_render_replaces_placeholder_and_reports_timing(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = mock.Mock(
                date="2026-09-22",
                work_dir=root / "work",
                output_dir=root / "reports",
                radar_json=None,
                deep_json=None,
            )
            args.work_dir.mkdir(parents=True)
            args.output_dir.mkdir(parents=True)
            radar_json = args.work_dir / "inference-radar-curated-2026-09-22.json"
            deep_json = args.work_dir / "llm-inference-foundations-deep-2026-09-22.json"
            radar_json.write_text(json.dumps({"actions": []}), encoding="utf-8")
            deep_json.write_text("{}", encoding="utf-8")

            prepare_started = self.wrapper.utc_now() - timedelta(seconds=5)
            self.wrapper.record_timing_event(
                args,
                "prepare",
                prepare_started,
                prepare_started + timedelta(seconds=1),
                1,
                "success",
            )

            def fake_run_process(command, timeout=None):
                output = Path(command[command.index("--output") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    f"<header><p>耗时：{self.wrapper.GENERATION_DURATION_PLACEHOLDER}</p></header>",
                    encoding="utf-8",
                )
                return {"command": command, "stdout": str(output), "stderr": ""}

            stdout = io.StringIO()
            with mock.patch.object(self.wrapper, "run_process", side_effect=fake_run_process):
                with mock.patch("sys.stdout", stdout):
                    self.assertEqual(self.wrapper.render(args), 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["timing"]["performance_status"], "ok")
            self.assertIsNotNone(payload["timing"]["total_generation_seconds"])
            self.assertEqual(payload["metrics_path"], str(args.work_dir / "daily-run-metrics-2026-09-22.json"))
            for html_path in (payload["radar_html"], payload["deep_html"]):
                content = Path(html_path).read_text(encoding="utf-8")
                self.assertNotIn(self.wrapper.GENERATION_DURATION_PLACEHOLDER, content)
                self.assertIn("渲染 ", content)
                self.assertIn("端到端 ", content)


class RendererTimingArgumentTests(unittest.TestCase):
    def test_both_renderers_accept_generation_duration_argument(self):
        for index, path in enumerate(RENDERER_PATHS):
            with self.subTest(renderer=path.name):
                renderer = load_module(path, f"test_timing_renderer_{index}")
                argv = [
                    "render.py",
                    "input.json",
                    "--output",
                    "output.html",
                    "--generation-duration-text",
                    "渲染 1.0 秒",
                ]
                with mock.patch.object(sys, "argv", argv):
                    args = renderer.parse_args()
                self.assertEqual(args.generation_duration_text, "渲染 1.0 秒")


if __name__ == "__main__":
    unittest.main()
