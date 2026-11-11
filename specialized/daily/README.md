# Daily AI Inference Reports

This repository is a self-contained Codex skill for generating two nightly LLM-inference HTML reports:

- `inference-radar-YYYY-MM-DD.html`
- `llm-inference-foundations-YYYY-MM-DD.html`

## Requirements

- Python 3.10 or newer
- Codex, for model curation and technical analysis

No third-party Python packages are required.

## Usage

From the repository root:

```bash
python3 scripts/run_daily.py prepare --date YYYY-MM-DD
python3 scripts/run_daily.py inspect --date YYYY-MM-DD
```

Codex then curates the two JSON files in `work/`. After curation:

```bash
python3 scripts/run_daily.py render --date YYYY-MM-DD
```

Generated HTML files are written to `reports/`.

All acquisition, candidate preparation, and rendering scripts are bundled under `scripts/vendor/`; the skill does not depend on scripts from other installed skills.

## Generation timing

Each run records timing in `work/daily-run-metrics-YYYY-MM-DD.json`. The file preserves successful and failed `prepare`/`render` events, derives the latest successful phase durations, calculates end-to-end generation time and curation gap, and marks `performance_status` as `ok`, `slow`, or `unavailable`. Runs at or above 600 seconds are marked `slow`, but rendering is not failed for being slow.

The `render` command returns a `timing` object and `metrics_path`. Both HTML report headers show the render duration, end-to-end duration, and performance status.

## Formula rendering

Deep foundations formula blocks use schema version 4. Each formula provides a `latex` expression and an optional plain-text accessibility label. Rendering is implemented with embedded CSS and a small Python parser; no MathJax, KaTeX, JavaScript, or network assets are required.

Run the bundled tests with:

```bash
python3 -m unittest discover -s tests
```
