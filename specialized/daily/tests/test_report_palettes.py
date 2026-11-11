import importlib.util
from pathlib import Path
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATHS = (
    SKILL_ROOT / "scripts" / "vendor" / "inference-radar" / "render_curated_report.py",
    SKILL_ROOT / "scripts" / "vendor" / "llm-inference-foundations" / "render_deep_report.py",
)


def load_renderer(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def contrast_ratio(first: str, second: str) -> float:
    def channel(value: str) -> float:
        return int(value, 16) / 255

    def luminance(color: str) -> float:
        channels = [channel(color[index:index + 2]) for index in (1, 3, 5)]
        normalized = [
            part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4
            for part in channels
        ]
        return 0.2126 * normalized[0] + 0.7152 * normalized[1] + 0.0722 * normalized[2]

    first_luminance = luminance(first)
    second_luminance = luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def interpolate_color(first: str, second: str, amount: float) -> str:
    channels = []
    for index in (1, 3, 5):
        start = int(first[index:index + 2], 16)
        end = int(second[index:index + 2], 16)
        channels.append(round(start + (end - start) * amount))
    return "#{:02x}{:02x}{:02x}".format(*channels)


class ReportPaletteTests(unittest.TestCase):
    def test_all_palettes_meet_high_contrast_requirements(self):
        for path in RENDERER_PATHS:
            with self.subTest(renderer=path.name):
                renderer = load_renderer(path)
                for palette in renderer.PALETTES:
                    with self.subTest(palette=palette["name"]):
                        self.assertGreaterEqual(contrast_ratio(palette["ink"], palette["card"]), 7)
                        self.assertGreaterEqual(contrast_ratio(palette["muted"], palette["card"]), 4.5)
                        self.assertGreaterEqual(contrast_ratio(palette["accent"], palette["card"]), 4.5)
                        self.assertGreaterEqual(contrast_ratio(palette["accent"], palette["soft"]), 4.5)
                        self.assertGreaterEqual(contrast_ratio("#ffffff", palette["header_end"]), 6)
                        self.assertGreaterEqual(contrast_ratio(palette["header_muted"], palette["header_end"]), 4.5)
                        if "code_bg" in palette:
                            self.assertGreaterEqual(contrast_ratio(palette["code_text"], palette["code_bg"]), 7)
                            self.assertGreaterEqual(contrast_ratio(palette["code_caption"], palette["code_bg"]), 4.5)

    def test_both_reports_use_the_same_daily_palette(self):
        renderers = [load_renderer(path) for path in RENDERER_PATHS]
        for date in ("2026-09-20", "2026-09-21", "2026-09-22"):
            palettes = {
                renderer.select_palette(date, "inference-radar")["name"]
                for renderer in renderers
            }
            self.assertEqual(len(palettes), 1, palettes)

    def test_dynamic_report_headers_always_keep_white_text_readable(self):
        for path in RENDERER_PATHS:
            with self.subTest(renderer=path.name):
                renderer = load_renderer(path)
                self.assertIn(
                    "background:linear-gradient(135deg,var(--header-start),var(--header-end)) !important",
                    renderer.HEADER_CSS,
                )
                self.assertIn("header h1{color:#fff !important", renderer.HEADER_CSS)
                header_pairs = {
                    (palette["header_start"], palette["header_end"])
                    for palette in renderer.PALETTES
                }
                self.assertEqual(len(header_pairs), len(renderer.PALETTES))
                for start, end in header_pairs:
                    for amount in range(11):
                        background = interpolate_color(start, end, amount / 10)
                        with self.subTest(background=background):
                            self.assertGreaterEqual(contrast_ratio("#ffffff", background), 7)
                            self.assertGreaterEqual(contrast_ratio("#f8fafc", background), 7)

    def test_daily_palette_selection_changes_across_days(self):
        renderer = load_renderer(RENDERER_PATHS[0])
        names = {
            renderer.select_palette(date, "inference-radar")["name"]
            for date in ("2026-09-20", "2026-09-21", "2026-09-22")
        }
        self.assertEqual(len(names), 3, names)

    def test_palette_variable_names_match_css_references(self):
        for path in RENDERER_PATHS:
            with self.subTest(renderer=path.name):
                renderer = load_renderer(path)
                for palette in renderer.PALETTES:
                    variables = renderer.palette_variables(palette)
                    with self.subTest(palette=palette["name"]):
                        self.assertIn(f"--header-start:{palette['header_start']}", variables)
                        self.assertIn(f"--header-end:{palette['header_end']}", variables)
                        self.assertNotIn("--header_start:", variables)
                        self.assertNotIn("--header_end:", variables)


if __name__ == "__main__":
    unittest.main()
