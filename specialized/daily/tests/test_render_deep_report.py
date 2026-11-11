import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "vendor"
    / "llm-inference-foundations"
    / "render_deep_report.py"
)


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_deep_report", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FormulaRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_renderer()

    def test_renders_structured_math(self):
        rendered = self.renderer.render_latex(
            r"O = \operatorname{softmax}\left(\frac{QK^\top}{\sqrt{D}}\right)V"
        )
        self.assertIn("mfrac", rendered)
        self.assertIn("msqrt", rendered)
        self.assertIn("<sup", rendered)
        self.assertIn("softmax", rendered)

    def test_script_base_stays_on_math_baseline(self):
        rendered = self.renderer.render_latex(r"Q_i")
        self.assertIn('<var>Q</var><sub class="mscript"><var>i</var></sub>', rendered)
        self.assertNotIn('<sub class="mscript"><var>Q</var>', rendered)

    def test_preserves_space_in_text_command(self):
        rendered = self.renderer.render_latex(r"s = -\infty \quad \text{if } j > i")
        self.assertIn("if</span>&#8201;", rendered)

    def test_rejects_unsupported_commands(self):
        with self.assertRaisesRegex(ValueError, "unsupported LaTeX command"):
            self.renderer.render_latex(r"\unknown{x}")

    def test_formula_block_is_not_rendered_as_code(self):
        rendered = self.renderer.render_block(
            {
                "type": "formula",
                "latex": r"I = \frac{F}{C}",
                "text": "arithmetic intensity = FLOPs / bytes",
            }
        )
        self.assertIn("<figure class='formula'>", rendered)
        self.assertIn("role='math'", rendered)
        self.assertNotIn("<code>", rendered)


if __name__ == "__main__":
    unittest.main()
