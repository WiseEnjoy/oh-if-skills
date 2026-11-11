---
name: daily
description: "Generate the user's two nightly LLM inference HTML reports when asked for 日报, daily, reports, or 晚报; do not use for unrelated daily reports."
metadata:
  short-description: One-word nightly AI inference report trigger
---

# Daily AI Inference Reports

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| Python 3.10+ | `python3 --version` | 安装 Python 3.10+ |
| curl | `command -v curl` | 安装 curl |
| git | `command -v git` | 安装 git |

首次使用运行 `bash <skill-dir>/install.sh`。脚本幂等，依赖齐全时立即退出。

## 输出范式（所有技能统一）

对外输出遵循 [meta/user-communication](../meta/user-communication/SKILL.md)：先讲背景与结论，只写可验证的事实和数字，不写“已优化”“应该没问题”这类无法验证的话。

## 10 分钟硬预算

整个日报任务必须在 10 分钟内完成。预算分配：

| 阶段 | 上限 | 超时动作 |
| --- | --- | --- |
| `prepare --fast` | 120 秒 | 复用已有采集文件，不再重试 |
| `inspect` | 10 秒 | 只看摘要，不逐条读全文 |
| 两个 JSON 的策展与撰写 | 360 秒 | 一次写完，不反复改结构 |
| `render` | 30 秒 | 失败则修 JSON 后只重跑一次 |
| 缓冲 | 80 秒 | 留给网络抖动和命令启动 |

执行纪律：

- 默认使用 `--fast`；只有用户明确要求全量质量时才去掉。
- 一次任务只允许一次 `prepare`、一次 `inspect`、一次 `render`。禁止中途用 `ls`、`cat`、`grep` 反复探查已生成的 JSON。
- 两个 JSON 一次写完再渲染，不要写完一个渲染一个。
- 播客源失败不重试：优先复用 `work/llm-inference-foundations-podcasts-YYYY-MM-DD.json`，没有就跳过播客并在报告里注明。
- 到第 8 分钟还没开始 `render`，立即复用现有输入渲染当前版本，并在最终回复里说明降级点。

This skill is self-contained. It bundles its own acquisition, candidate preparation, and rendering scripts under `scripts/vendor/`, so it can be archived or cloned as a standalone repository and used with only Codex and Python.

## Single-command gateway

Use this skill's shared wrapper for all network acquisition and final rendering. Do not invoke the underlying acquisition or rendering scripts directly for a normal daily run, and do not use separate `cat`, `ls`, `grep`, or ad hoc Python commands to inspect generated JSON.

Run from the repository root:

```bash
python3 scripts/run_daily.py
```

Acquire all inputs in one invocation:

```bash
python3 scripts/run_daily.py prepare \
  --date YYYY-MM-DD --fast
```

Inspect the concise candidate summaries in one invocation:

```bash
python3 scripts/run_daily.py inspect \
  --date YYYY-MM-DD
```

Codex then curates the two JSON files in memory or with an edit tool, without issuing additional shell commands for inspection. Use `inspect --full` only when the concise view is insufficient.

Respect the `seen_before` flag on candidates: it marks items already covered in a previous day's curated report. Skip them unless there is a material new development (state change, new evidence, meaningful follow-up). Prefer genuinely new signals over repeats; do not re-report an old item just because it is still active.

Candidates from repository sources carry a `body_excerpt` (the PR/issue description, code blocks stripped, up to 800 characters). Read it before writing 优化背景/具体优化/工程启示 — it usually contains the concrete reproduction, dtype/shape constraints, or reviewer discussion that the title alone does not show. Cite specifics from the body excerpt rather than restating the title.

Tag every curated radar item with `skill_tags`: an array of one or two values from `scripts/vendor/inference-radar/skill_map.json` — either a bare domain tag (`"quantization"`) or a domain/skill pair (`"quantization/mxfp"`). The renderer rejects unknown tags, so copy them from the map rather than inventing new ones. These tags feed the 能力覆盖热力图, which rolls up 30 days of coverage per domain; prefer the most specific pair the evidence supports.

Render both reports in one invocation:

```bash
python3 scripts/run_daily.py render \
  --date YYYY-MM-DD
```

The wrapper uses these conventional paths:

- `work/inference-radar-curated-YYYY-MM-DD.json`
- `work/llm-inference-foundations-deep-YYYY-MM-DD.json`
- `work/daily-run-metrics-YYYY-MM-DD.json`
- `reports/inference-radar-YYYY-MM-DD.html`
- `reports/llm-inference-foundations-YYYY-MM-DD.html`

Use `paths --date YYYY-MM-DD` only when a concise path listing is needed. Keep all daily workflow commands under the same wrapper prefix so permission prompts remain stable and minimal.

Verification actions are tracked in a persistent ledger (`work/verification-ledger.json`). `render` automatically appends today's actions and carries still-open older ones into the report's 未闭环的验证行动 section with their age. When the user says an action was completed, re-render after closing it: `python3 -c "import sys; sys.path.insert(0, 'scripts/vendor/inference-radar'); import verification_ledger, json; from pathlib import Path; p = Path('work/verification-ledger.json'); l = verification_ledger.load(p); verification_ledger.close(l, '<title substring>', '<today>'); p.write_text(json.dumps(l, ensure_ascii=False, indent=2))"` — then run `render` again.

Generation timing is recorded automatically in `work/daily-run-metrics-YYYY-MM-DD.json`. The file keeps `prepare` and `render` event history, including failures, and derives:

- `prepare_duration_seconds`
- `render_duration_seconds`
- `total_generation_seconds` from the latest successful `prepare` start to the latest successful `render` end
- `curation_gap_seconds`
- `performance_status` (`ok`, `slow`, or `unavailable`) using a 600-second slow threshold

Both report headers display the render duration, end-to-end duration, and performance status. In the final response, report the render duration and end-to-end duration from the `render` command output. If `performance_status` is `slow`, state the main bottleneck or data-health delay; do not fail rendering merely because it is slow.

Use the current Beijing date. Generate exactly two self-contained HTML files under `reports/`:

- `inference-radar-YYYY-MM-DD.html`
- `llm-inference-foundations-YYYY-MM-DD.html`

Do not create a scheduler and do not call an external LLM. Use each skill's acquisition pipeline where available, then use Codex for curation and technical explanation.

Quality outranks coverage. Broad intake may include domestic and international professional communities, recent hotspots, papers, vendor docs, and engineering blogs, but the final reports must stay focused on the LLM inference stack. Include only evidence-linked items that improve inference correctness, performance, memory, graph execution, or distributed-serving judgment. Do not pad sections with low-signal news, demos, marketing, training churn, application-layer work, or generic AI commentary.

HTML rendering uses a deterministic daily palette selected from several classic high-contrast themes. A same-day rerender must keep the same palette; palette variation must never change content or evidence. Each palette ships a matching dark variant; reports auto-follow the system color-scheme with a manual toggle, and both light and dark variants must keep WCAG AA contrast. Report pages embed a small amount of progressive-enhancement JavaScript (priority filter, section collapse, theme toggle, reading progress). It is inline and optional: with JavaScript disabled the reports must still be fully readable. Do not add CDN assets, external fonts, or framework JavaScript.

Deep foundations reports use formula schema version 4. Every formula block must provide a `latex` field and may provide a plain-text `text` field for assistive technology. Write one primary relationship per formula, use short symbols such as `F_{\mathrm{decode}}` and `C_{\mathrm{KV}}`, and explain symbols in the caption. The renderer supports only a self-contained LaTeX subset (`\frac`, `\sqrt`, subscripts/superscripts, `\sum`, `\exp`, `\operatorname`, `\mathrm`, `\text`, `\mathbb`, and common relations/operators); do not add MathJax, KaTeX, CDN assets, or JavaScript.

Report the two output paths and key data-health limitations when finished.

## Source registry

Repository sources (engines/frameworks/operators/communications) live in `scripts/vendor/inference-radar/fetch_updates.py`; web, community, paper, and blog sources live in `scripts/vendor/inference-radar/fetch_web_sources.py`. Both are plain lists — add a source by appending an entry, then register its key in `quality_audit.py` (`CATEGORY_SOURCES`) and, if it should survive low machine scores, `prepare_candidates.py` (`BROAD_SOURCE_KEYS`). Tier assignment and source weights live in `build_report.py` (`TIER_SOURCES`, `SOURCE_WEIGHT`). Never let a fetch failure of one new source block the others; the quality audit reports completeness separately from schema validity.

## Testing

Run the bundled tests after changing any renderer or palette:

```bash
python3 -m unittest discover -s tests
```

Palette changes must pass the contrast tests; renderer changes must keep the formula subset tests green.
