#!/usr/bin/env python3
"""Render a model-curated, deep LLM-inference foundations HTML brief."""

from __future__ import annotations

import argparse
import html
import json
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

ALLOWED_BLOCK_TYPES = {"paragraph", "formula", "list", "table", "callout", "code"}
SUPPORTED_SCHEMA_VERSIONS = {3, 4}
REQUIRED_TOP_KEYS = [
    "schema_version", "date", "phase", "title", "continuity", "learning_objectives",
    "sections", "practice", "podcast", "reflection", "data_health", "references",
]

LATEX_SYMBOLS = {
    "approx": '<span class="mrel">≈</span>',
    "times": '<span class="mbin">×</span>',
    "cdot": '<span class="mbin">·</span>',
    "le": '<span class="mrel">≤</span>',
    "ge": '<span class="mrel">≥</span>',
    "ne": '<span class="mrel">≠</span>',
    "in": '<span class="mrel">∈</span>',
    "infty": '<span class="mrm">∞</span>',
    "top": '<span class="mrm">⊤</span>',
    "sum": '<span class="mop mlarge">∑</span>',
    "to": '<span class="mrel">→</span>',
    "ldots": '<span class="mrm">…</span>',
    "dots": '<span class="mrm">…</span>',
}
LATEX_FUNCTIONS = {"exp", "log", "min", "max"}
LATEX_SPACING = {"!": "", ",": "&#8201;", ";": "&#8201;", " ": "&#8201;", "quad": "&#8195;", "qquad": "&#8195;&#8195;"}
LATEX_TEXT_COMMANDS = {"text", "mathrm", "operatorname"}
LATEX_ARG_COMMANDS = {"frac", "sqrt", "mathbb", "left", "right", *LATEX_TEXT_COMMANDS}
SUPPORTED_LATEX_COMMANDS = {*LATEX_SYMBOLS, *LATEX_FUNCTIONS, *LATEX_SPACING, *LATEX_ARG_COMMANDS}
MATHBB_SYMBOLS = {"R": "ℝ", "N": "ℕ", "Q": "ℚ", "C": "ℂ", "Z": "ℤ"}

PALETTES = [
    {
        "name": "ocean",
        "ink": "#111827", "muted": "#4b5563", "line": "#cbd5e1", "bg": "#f1f5f9",
        "card": "#ffffff", "accent": "#1d4ed8", "soft": "#e8eefc",
        "header_start": "#0f172a", "header_end": "#1e40af", "header_muted": "#f8fafc",
        "code_bg": "#0f172a", "code_text": "#f8fafc", "code_caption": "#bfdbfe",
        "dark": {
            "bg": "#0a1120", "card": "#101a2e", "ink": "#e6ecf8", "muted": "#9aa8c0",
            "line": "#2a3a5e", "soft": "#18233c", "accent": "#82aaff",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(154,168,192,.16)", "chip_text": "#c3cad6",
            "ok_bg": "rgba(74,222,128,.14)", "bad_bg": "rgba(248,113,113,.14)",
            "code_bg": "#060b16", "code_text": "#e6ecf8",
        },
    },
    {
        "name": "forest",
        "ink": "#10241a", "muted": "#43554a", "line": "#cbd8d0", "bg": "#f2f7f4",
        "card": "#ffffff", "accent": "#166534", "soft": "#e6f4ec",
        "header_start": "#072416", "header_end": "#14532d", "header_muted": "#f8fafc",
        "code_bg": "#072416", "code_text": "#f0fdf4", "code_caption": "#a7dcb9",
        "dark": {
            "bg": "#0a140f", "card": "#0f2018", "ink": "#e4f0e8", "muted": "#93b3a2",
            "line": "#244435", "soft": "#163024", "accent": "#7cd9a8",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(147,179,162,.15)", "chip_text": "#c6d8cd",
            "ok_bg": "rgba(74,222,128,.14)", "bad_bg": "rgba(248,113,113,.14)",
            "code_bg": "#050c08", "code_text": "#e4f0e8",
        },
    },
    {
        "name": "graphite",
        "ink": "#111827", "muted": "#4b5563", "line": "#d1d5db", "bg": "#f3f4f6",
        "card": "#ffffff", "accent": "#1f2937", "soft": "#e9eaee",
        "header_start": "#0b1120", "header_end": "#374151", "header_muted": "#f8fafc",
        "code_bg": "#0b1120", "code_text": "#f8fafc", "code_caption": "#cbd5e1",
        "dark": {
            "bg": "#0c0e11", "card": "#16191e", "ink": "#e8eaee", "muted": "#9aa2ad",
            "line": "#2c313a", "soft": "#1d222a", "accent": "#9db8dd",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(154,162,173,.15)", "chip_text": "#c8ccd4",
            "ok_bg": "rgba(74,222,128,.13)", "bad_bg": "rgba(248,113,113,.13)",
            "code_bg": "#07090c", "code_text": "#e8eaee",
        },
    },
]


HEADER_CSS = """<style>
header{background:linear-gradient(135deg,var(--header-start),var(--header-end)) !important;color:#fff !important;border-bottom:5px solid var(--accent)}
header h1{color:#fff !important;text-shadow:0 1px 2px rgba(0,0,0,.65)}
header p{color:#f8fafc !important}
</style>"""


def select_palette(date: str, report_type: str) -> dict[str, str]:
    """Pick one stable high-contrast palette per day for both report types."""
    digest = hashlib.sha256(date.encode("utf-8")).digest()
    return PALETTES[digest[0] % len(PALETTES)]


def palette_variables(palette: dict[str, str]) -> str:
    return ";".join(
        f"--{key.replace('_', '-')}:{value}"
        for key, value in palette.items()
        if key != "name" and key != "dark"
    )


def dark_palette_variables(dark: dict[str, str]) -> str:
    return ";".join(f"--{key.replace('_', '-')}:{value}" for key, value in dark.items())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--generation-duration-text",
        default="未记录",
        help="Readable report generation duration shown in the header",
    )
    return parser.parse_args()


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _read_command(expression: str, position: int) -> tuple[str, int]:
    if position >= len(expression) or expression[position] != "\\":
        raise ValueError("expected a LaTeX command")
    position += 1
    if position >= len(expression):
        raise ValueError("empty LaTeX command")
    if not expression[position].isalpha():
        return expression[position], position + 1
    start = position
    while position < len(expression) and expression[position].isalpha():
        position += 1
    return expression[start:position], position


def _read_raw_group(expression: str, position: int) -> tuple[str, int]:
    if position >= len(expression) or expression[position] != "{":
        raise ValueError("expected {")
    position += 1
    start = position
    depth = 1
    while position < len(expression):
        character = expression[position]
        if character == "\\":
            position += 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return expression[start:position], position + 1
        position += 1
    raise ValueError("unbalanced LaTeX group")


def _read_raw_argument(expression: str, position: int) -> tuple[str, int]:
    if position >= len(expression):
        raise ValueError("expected a LaTeX argument")
    if expression[position] == "{":
        return _read_raw_group(expression, position)
    if expression[position] == "\\":
        start = position
        _, position = _read_command(expression, position)
        return expression[start:position], position
    return expression[position], position + 1


def _read_plain_token(expression: str, position: int) -> tuple[str, int]:
    character = expression[position]
    if character.isalpha():
        start = position
        while position < len(expression) and expression[position].isalpha():
            position += 1
        return expression[start:position], position
    if character.isdigit():
        start = position
        while position < len(expression) and (expression[position].isdigit() or expression[position] == "."):
            position += 1
        return expression[start:position], position
    return character, position + 1


def _render_plain_token(token: str, upright: bool) -> str:
    if token in {"+", "-"}:
        return f'<span class="mbin">{e(token)}</span>'
    if token in {"=", "<", ">", "≤", "≥", "≠", "≈", "∈", "→"}:
        return f'<span class="mrel">{e(token)}</span>'
    if token in {"(", "[", ")", "]"}:
        return f'<span class="mdelim">{e(token)}</span>'
    if token.isalpha():
        if upright or len(token) > 1:
            return f'<span class="mrm">{e(token)}</span>'
        return f"<var>{e(token)}</var>"
    return f'<span class="mrm">{e(token)}</span>'


def _parse_math(expression: str, position: int = 0, end: int | None = None, upright: bool = False) -> str:
    if end is None:
        end = len(expression)
    nodes: list[str] = []
    while position < end:
        character = expression[position]
        if character.isspace():
            if upright:
                nodes.append("&#8201;")
            position += 1
        elif character == "{":
            group, position = _read_raw_group(expression, position)
            nodes.append(_parse_math(group, upright=upright))
        elif character == "}":
            raise ValueError("unexpected }")
        elif character == "~":
            nodes.append("&#8201;")
            position += 1
        elif character == "\\":
            command, position = _read_command(expression, position)
            if command in LATEX_SPACING:
                nodes.append(LATEX_SPACING[command])
            elif command in LATEX_SYMBOLS:
                nodes.append(LATEX_SYMBOLS[command])
            elif command in LATEX_FUNCTIONS:
                nodes.append(f'<span class="mop">{e(command)}</span>')
            elif command in LATEX_TEXT_COMMANDS:
                argument, position = _read_raw_argument(expression, position)
                nodes.append(f'<span class="mrm">{_parse_math(argument, upright=True)}</span>')
            elif command == "frac":
                numerator, position = _read_raw_argument(expression, position)
                denominator, position = _read_raw_argument(expression, position)
                nodes.append(
                    '<span class="mfrac">'
                    f'<span class="mnum">{_parse_math(numerator, upright=upright)}</span>'
                    f'<span class="mden">{_parse_math(denominator, upright=upright)}</span>'
                    "</span>"
                )
            elif command == "sqrt":
                argument, position = _read_raw_argument(expression, position)
                nodes.append(
                    '<span class="msqrt"><span class="msqrt-sign">√</span>'
                    f'<span class="msqrt-body">{_parse_math(argument, upright=upright)}</span></span>'
                )
            elif command == "mathbb":
                argument, position = _read_raw_argument(expression, position)
                if argument not in MATHBB_SYMBOLS:
                    raise ValueError(f"unsupported \\mathbb{{{argument}}}")
                nodes.append(f'<span class="mbb">{e(MATHBB_SYMBOLS[argument])}</span>')
            elif command in {"left", "right"}:
                argument, position = _read_raw_argument(expression, position)
                nodes.append(f'<span class="mdelim">{e(argument)}</span>')
            else:
                raise ValueError(f"unsupported LaTeX command: \\{command}")
        elif character in "_^":
            position += 1
            script, position = _read_raw_argument(expression, position)
            if not nodes:
                raise ValueError("subscript/superscript has no base")
            base = nodes.pop()
            tag = "sub" if character == "_" else "sup"
            nodes.append(f'{base}<{tag} class="mscript">{_parse_math(script, upright=upright)}</{tag}>')
        else:
            token, position = _read_plain_token(expression, position)
            nodes.append(_render_plain_token(token, upright))
    return "".join(nodes)


def render_latex(expression: str) -> str:
    """Render the report's intentionally small, self-contained LaTeX subset."""
    if not expression.strip():
        raise ValueError("formula LaTeX must not be empty")
    return _parse_math(expression)


def validate(data: dict[str, Any]) -> None:
    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            raise ValueError(f"missing top-level key: {key}")
    schema_version = data["schema_version"]
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("deep foundations report schema_version must be 3 or 4")
    datetime.strptime(data["date"], "%Y-%m-%d")
    if not (1 <= int(data["phase"]) <= 4):
        raise ValueError("phase must be 1..4")
    continuity = data.get("continuity")
    if not isinstance(continuity, dict):
        raise ValueError("continuity is required")
    for key in ("previous_topic", "today_focus", "next_topic", "connection"):
        if not continuity.get(key):
            raise ValueError(f"continuity missing {key}")
    if not data["title"] or len(data["learning_objectives"]) < 4:
        raise ValueError("title and at least four learning_objectives are required")
    if len(data["sections"]) < 10:
        raise ValueError("a deep foundations tutorial needs at least 10 content sections")
    if len(json.dumps(data, ensure_ascii=False)) < 18000:
        raise ValueError("deep foundations content is below the 18,000-character quality gate")

    block_types = [block.get("type") for section in data["sections"] for block in section["blocks"]]
    if sum(block_type == "formula" for block_type in block_types) < 4:
        raise ValueError("a deep tutorial needs at least four formula blocks")
    if sum(block_type == "table" for block_type in block_types) < 5:
        raise ValueError("a deep tutorial needs at least five table blocks")
    if not any(block_type == "code" for block_type in block_types):
        raise ValueError("a deep tutorial needs at least one code or pseudo-code block")

    section_ids: set[str] = set()
    for section_index, section in enumerate(data["sections"], 1):
        for key in ("id", "title", "summary", "blocks"):
            if not section.get(key):
                raise ValueError(f"section {section_index}: missing {key}")
        if len(section["summary"]) < 20:
            raise ValueError(f"section {section_index}: summary must be at least 20 characters")
        if section["id"] in section_ids:
            raise ValueError(f"section {section_index}: duplicate id")
        section_ids.add(section["id"])
        if not section["blocks"]:
            raise ValueError(f"section {section_index}: blocks must not be empty")
        if len(section["blocks"]) < 3:
            raise ValueError(f"section {section_index}: needs at least three substantive blocks")
        for block_index, block in enumerate(section["blocks"], 1):
            block_type = block.get("type")
            if block_type not in ALLOWED_BLOCK_TYPES:
                raise ValueError(f"section {section_index} block {block_index}: invalid type {block_type}")
            if block_type == "paragraph" and not block.get("text"):
                raise ValueError(f"section {section_index} block {block_index}: paragraph text is required")
            if block_type == "formula":
                latex = block.get("latex")
                if schema_version == 3 and not block.get("text"):
                    raise ValueError(f"section {section_index} block {block_index}: formula text is required")
                if schema_version == 4 and not latex:
                    raise ValueError(f"section {section_index} block {block_index}: formula latex is required")
                try:
                    render_latex(latex or block["text"])
                except ValueError as exc:
                    raise ValueError(f"section {section_index} block {block_index}: {exc}") from exc
            if block_type == "list" and not block.get("items"):
                raise ValueError(f"section {section_index} block {block_index}: list items are required")
            if block_type == "table":
                if not block.get("headers") or not block.get("rows"):
                    raise ValueError(f"section {section_index} block {block_index}: table headers/rows are required")
            if block_type == "callout" and not block.get("text"):
                raise ValueError(f"section {section_index} block {block_index}: callout text is required")

    practice = data["practice"]
    for key in ("title", "timebox", "steps", "deliverables", "success_criteria"):
        if not practice.get(key):
            raise ValueError(f"practice missing {key}")
    if len(practice["steps"]) < 3:
        raise ValueError("practice needs at least three steps")
    if len(practice["deliverables"]) < 2:
        raise ValueError("practice needs at least two deliverables")
    if len(practice["success_criteria"]) < 2:
        raise ValueError("practice needs at least two success criteria")

    podcast = data["podcast"]
    for key in ("title", "source", "published_at", "duration", "difficulty", "url", "reason", "questions"):
        if not podcast.get(key):
            raise ValueError(f"podcast missing {key}")
    parsed = urlparse(podcast["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("podcast URL is invalid")
    if not 2 <= len(podcast["questions"]) <= 5:
        raise ValueError("podcast must have 2–5 questions")

    if len(data["references"]) < 5:
        raise ValueError("a deep tutorial needs at least five references")
    for reference in data.get("references", []):
        if not reference.get("title") or not reference.get("url"):
            raise ValueError("reference requires title and URL")
        parsed = urlparse(reference["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid reference URL: {reference['url']}")


def render_block(block: dict[str, Any]) -> str:
    block_type = block["type"]
    if block_type == "paragraph":
        return f"<p>{e(block['text'])}</p>"
    if block_type == "formula":
        caption = f"<figcaption class='formula-caption'>{e(block['caption'])}</figcaption>" if block.get("caption") else ""
        latex = block.get("latex") or block.get("text", "")
        aria_label = block.get("text") or latex
        return (
            "<figure class='formula'>"
            f"<div class='math' role='math' aria-label='{e(aria_label)}'>{render_latex(latex)}</div>"
            f"{caption}</figure>"
        )
    if block_type == "list":
        style = "checklist" if block.get("style") == "checklist" else "normal"
        items = "".join(f"<li>{e(item)}</li>" for item in block["items"])
        return f"<ul class='{style}'>{items}</ul>"
    if block_type == "table":
        headers = "".join(f"<th>{e(header)}</th>" for header in block["headers"])
        rows = "".join("<tr>" + "".join(f"<td>{e(cell)}</td>" for cell in row) + "</tr>" for row in block["rows"])
        return f"<div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>"
    if block_type == "callout":
        return f"<div class='callout'><strong>{e(block.get('title', '关键判断'))}</strong><p>{e(block['text'])}</p></div>"
    if block_type == "code":
        return f"<pre><code>{e(block['text'])}</code></pre>"
    raise ValueError(f"unsupported block type: {block_type}")


def render(
    data: dict[str, Any],
    generation_duration_text: str = "未记录",
) -> str:
    palette = select_palette(data["date"], "llm-inference-foundations")
    palette_css = palette_variables(palette)
    dark_css = dark_palette_variables(palette["dark"])
    section_count = len(data["sections"])
    est_minutes = max(15, round(section_count * 4))
    toc_entries = [
        ("continuity", "课题连续性"),
        ("objectives", "学习目标"),
    ] + [
        (section["id"], f"{index} · {section['title']}")
        for index, section in enumerate(data["sections"], 1)
    ] + [
        ("practice", "练习"),
        ("podcast", "今日播客"),
        ("feed-health", "Feed 健康"),
        ("reflection", "复盘"),
        ("references", "延伸阅读"),
    ]
    nav = "".join(
        f"<li><a href='#{e(section_id)}'>{e(title)}</a></li>"
        for section_id, title in toc_entries
    )
    sections = []
    for index, section in enumerate(data["sections"], 1):
        blocks = "".join(render_block(block) for block in section["blocks"])
        sections.append(
            f"<details class='content-section' id='{e(section['id'])}' open>"
            f"<summary><span class='sec-index'>{index:02d}</span><span class='sec-titles'><h2>{e(section['title'])}</h2><span class='section-summary'>{e(section['summary'])}</span></span></summary>"
            f"<div class='section-body'>{blocks}</div></details>"
        )

    objectives = "".join(f"<li>{e(item)}</li>" for item in data["learning_objectives"])
    practice_steps = "".join(f"<li>{e(item)}</li>" for item in data["practice"]["steps"])
    deliverables = "".join(f"<li>{e(item)}</li>" for item in data["practice"]["deliverables"])
    success = "".join(f"<li>{e(item)}</li>" for item in data["practice"]["success_criteria"])
    questions = "".join(f"<li>{e(item)}</li>" for item in data["podcast"]["questions"])
    references = "".join(f"<li><a href='{e(ref['url'])}' target='_blank' rel='noopener'>{e(ref['title'])}</a><span> · {e(ref.get('why', ''))}</span></li>" for ref in data["references"])

    source_rows = []
    for source in data["data_health"].get("sources", []):
        status = source.get("status", "unknown")
        css = "ok" if status == "ok" else "bad"
        errors = "; ".join(source.get("errors") or []) or "—"
        source_rows.append(
            f"<tr><td>{e(source.get('name'))}</td><td><span class='badge {css}'>{e(status)}</span></td><td>{e(source.get('in_window', 0))} / {e(source.get('count', 0))}</td><td>{e(errors)}</td></tr>"
        )

    podcast = data["podcast"]
    generated = data.get("generated_at_utc", "")
    generation_duration = data.get("generation_duration_text") or generation_duration_text
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LLM 推理基础深读 · {e(data['date'])}</title>
<style>
:root{{--good:#16803c;--bad:#b42318;--warn:#b54708;{palette_css}}}
:root.dark-mode{{--{dark_css}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;transition:background .2s,color .2s}} main{{width:100%;max-width:none;padding:clamp(16px,2.5vw,44px) clamp(16px,3vw,56px) clamp(32px,4vw,72px)}} header{{background:linear-gradient(135deg,var(--header-start),var(--header-end));color:#fff;border-radius:12px;padding:clamp(22px,3vw,38px);margin-bottom:clamp(14px,2vw,24px)}} header h1{{margin:0 0 10px;font-size:clamp(26px,3.4vw,42px);font-weight:800;letter-spacing:0;text-shadow:0 1px 2px rgba(0,0,0,.28)}} header p{{margin:5px 0;color:var(--header-muted)}} .toc{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:clamp(14px,2vw,22px);margin-bottom:clamp(14px,2vw,22px)}} .toc h2{{margin:0 0 12px;font-size:16px}} .toc ol{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:8px 28px;margin:0;padding:0;list-style:none;counter-reset:toc}} .toc li{{counter-increment:toc;min-width:0}} .toc li::before{{content:counter(toc,decimal-leading-zero) " · ";color:var(--muted);font-variant-numeric:tabular-nums}} .toc a{{display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom;color:var(--accent);text-decoration:none;font-size:14px}} .toc a:hover{{text-decoration:underline}} details.content-section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:0;margin-bottom:clamp(14px,2vw,22px)}} details.content-section>summary{{list-style:none;display:flex;gap:16px;align-items:baseline;cursor:pointer;padding:clamp(18px,2.2vw,30px)}} details.content-section>summary::-webkit-details-marker{{display:none}} details.content-section>summary::after{{content:"+";margin-left:auto;color:var(--muted);font-size:22px;line-height:1}} details.content-section[open]>summary::after{{content:"–"}} details.content-section>summary:hover h2{{color:var(--accent)}} .sec-index{{color:var(--muted);font-variant-numeric:tabular-nums;font-size:15px;flex:0 0 auto}} .sec-titles{{min-width:0;flex:1}} .sec-titles h2{{margin:0;font-size:23px}} .section-summary{{display:block;color:var(--muted);margin:4px 0 0;font-size:14px;font-weight:400}} details.content-section .section-body{{border-top:1px solid var(--line);padding:clamp(18px,2.2vw,30px);column-width:min(100%,760px);column-gap:clamp(24px,3vw,40px)}} details.content-section .section-body>*{{break-inside:avoid}} p{{margin:10px 0}} code,pre{{font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace}} .formula{{background:var(--soft);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:16px 18px;margin:16px 0;overflow-x:auto;color:var(--ink)}} .math{{display:inline-block;min-width:100%;color:var(--ink);font-family:"Latin Modern Math","STIX Two Math","Cambria Math",Georgia,serif;font-size:1.08rem;line-height:1.45;white-space:nowrap;vertical-align:middle}} .math var{{font-style:italic;padding:0 .025em}} .mrm{{font-style:normal}} .mbb{{font-weight:600}} .mop{{padding:0 .1em}} .mlarge{{font-size:1.35em;line-height:1}} .mbin{{padding:0 .18em}} .mrel{{padding:0 .22em}} .mdelim{{padding:0 .03em}} .mfrac{{display:inline-flex;flex-direction:column;align-items:center;vertical-align:-.48em;margin:0 .18em;line-height:1.25}} .mnum{{display:flex;justify-content:center;padding:0 .18em .08em;border-bottom:1px solid currentColor}} .mden{{display:flex;justify-content:center;padding:.08em .18em 0}} .msqrt{{display:inline-flex;align-items:stretch;vertical-align:-.08em;line-height:1.25}} .msqrt-sign{{line-height:1.1}} .msqrt-body{{border-top:1px solid currentColor;padding:.08em .18em 0}} .mscript{{font-size:.68em;line-height:1;position:relative;vertical-align:baseline}} sub.mscript{{bottom:-.12em}} sup.mscript{{top:.34em}} .formula-caption{{display:block;color:var(--muted);font-size:12px;line-height:1.55;margin-top:10px;white-space:normal}} .table-wrap{{overflow-x:auto}} table{{width:100%;min-width:720px;border-collapse:collapse;margin:12px 0}} th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}} th{{color:var(--muted);font-size:13px;background:var(--soft);white-space:nowrap}} ul{{padding-left:22px;margin:10px 0}} li{{margin:6px 0}} .callout{{background:var(--soft);border-left:5px solid var(--accent);border-radius:8px;padding:14px 16px;margin:16px 0}} .badge{{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;background:var(--chip-bg,#e5e7eb);color:var(--chip-text,#374151)}} .badge.ok{{background:var(--ok-bg,#dcfce7);color:var(--good)}} .badge.bad{{background:var(--bad-bg,#fee2e2);color:var(--bad)}} .card{{border:1px solid var(--line);border-radius:8px;padding:18px;background:var(--card);column-width:min(100%,760px);column-gap:clamp(24px,3vw,40px)}} .card>*{{break-inside:avoid}} .primary{{border-left:5px solid var(--accent)}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} pre{{background:var(--code-bg);color:var(--code-text);padding:14px;border-radius:8px;overflow-x:auto}} .references{{column-width:min(100%,760px);column-gap:clamp(24px,3vw,40px)}} .references li{{break-inside:avoid}} footer{{color:var(--muted);font-size:13px;text-align:center;padding-top:4px}}
#progress-bar{{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:99;transition:width .08s linear}}
#back-top{{position:fixed;right:clamp(12px,2vw,28px);bottom:clamp(12px,2vw,28px);border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:999px;width:44px;height:44px;font-size:18px;cursor:pointer;display:none;box-shadow:0 2px 10px rgba(0,0,0,.15);z-index:98}}
#back-top:hover{{background:var(--soft)}}
#theme-toggle{{float:right;border:1px solid rgba(255,255,255,.35);background:rgba(255,255,255,.12);color:#fff;border-radius:999px;padding:5px 14px;font-size:13px;cursor:pointer}}
#theme-toggle:hover{{background:rgba(255,255,255,.22)}}
.toc-tools{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}} .toc-tools button{{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 14px;font-size:13px;cursor:pointer}} .toc-tools button:hover{{background:var(--soft)}}
.read-estimate{{color:var(--muted);font-size:13px;margin-left:auto;align-self:center}}
@media print{{.toc,#back-top,#progress-bar,#theme-toggle,.toc-tools{{display:none}}body{{background:#fff}}details.content-section{{break-inside:avoid;border:none;padding:0}}details.content-section .section-body{{column-count:1;border:none;padding:0;break-inside:avoid}}details.content-section:not([open])>.section-body{{display:block}}a{{color:inherit}}.formula{{page-break-inside:avoid}}}}
:root.dark-mode header{{background:var(--card);border:1px solid var(--line)}} :root.dark-mode #theme-toggle{{border-color:var(--line);background:var(--soft);color:var(--ink)}}
@media (prefers-color-scheme: dark){{ :root:not([data-theme="light"]):not(.dark-mode){{--{dark_css}}}}}
:root[data-theme="dark"]{{--{dark_css}}}
</style>{HEADER_CSS}</head><body><main>
<div id="progress-bar" aria-hidden="true"></div>
<header><button id="theme-toggle" type="button" aria-label="切换深浅色">深色</button><h1>LLM 推理基础深读 · {e(data['date'])}</h1><p>{e(data['title'])}</p><p>Phase {e(data['phase'])} · 从模型原理到推理工程实现 · Codex 模型解析</p><p>生成时间：{e(generated)} UTC · {e(data['data_health'].get('health_note', ''))} · 配色：{e(palette['name'])}</p><p>耗时：{e(generation_duration)}</p></header>
<nav class="toc" aria-label="目录"><h2>目录</h2><ol>{nav}</ol>
<div class="toc-tools"><button id="expand-all" type="button">全部展开</button><button id="collapse-all" type="button">速览模式（只看摘要）</button><span class="read-estimate">{section_count} 个章节 · 预计 {est_minutes} 分钟</span></div></nav>
<section id="continuity"><h2>课题连续性</h2><div class='section-body'><div class='table-wrap'><table><thead><tr><th>上一课</th><th>今日重点</th><th>下一课</th></tr></thead><tbody><tr><td>{e(data['continuity']['previous_topic'])}</td><td><strong>{e(data['continuity']['today_focus'])}</strong></td><td>{e(data['continuity']['next_topic'])}</td></tr></tbody></table></div><div class='callout'><strong>衔接逻辑</strong><p>{e(data['continuity']['connection'])}</p></div></div></section>
<section id="objectives"><h2>学习目标</h2><div class='section-body'><ul>{objectives}</ul><div class="callout"><strong>阅读方式</strong><p>先理解公式和结构，再把每一层映射到 TTFT、TPOT、吞吐、显存和稳定性。不要把本篇当新闻速读；遇到不理解的公式，先完成练习，再回看对应章节。</p></div></div></section>
{''.join(sections)}
<section id="practice"><h2>练习</h2><div class='section-body'><article class="card"><h3>{e(data['practice']['title'])}</h3><p class='meta'>时间盒：{e(data['practice']['timebox'])}</p><h4>步骤</h4><ul>{practice_steps}</ul><h4>交付物</h4><ul>{deliverables}</ul><h4>验收标准</h4><ul class='checklist'>{success}</ul></article></div></section>
<section id="podcast"><h2>今日播客</h2><div class='section-body'><article class="card primary"><div class='episode-head'><span class='badge ok'>{e(podcast['difficulty'])}</span><h3>{e(podcast['title'])}</h3></div><p class='meta'>{e(podcast['source'])} · {e(podcast['published_at'])} · {e(podcast['duration'])}</p><p><a href='{e(podcast['url'])}' target='_blank' rel='noopener'>打开原始节目页</a></p><p><strong>为什么选它：</strong>{e(podcast['reason'])}</p><h4>带着问题听</h4><ul>{questions}</ul></article></div></section>
<section id="feed-health"><h2>Feed 健康</h2><div class='section-body'><div class='table-wrap'><table><thead><tr><th>来源</th><th>状态</th><th>窗口内 / 总抓取</th><th>错误</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div></div></section>
<section id="reflection"><h2>复盘</h2><div class='section-body'><article class="card"><p><strong>{e(data['reflection']['question'])}</strong></p><p>{e(data['reflection']['instruction'])}</p></article></div></section>
<section id="references"><h2>延伸阅读</h2><div class='section-body'><ol class="references">{references}</ol></div></section>
<footer>LLM Inference Foundations 独立深读报告 · 不包含仓库 PR/issue 动态 · 原理与工程判断由 Codex 基于公开资料解析，实验结论需本地验证。生成节奏：每晚下班前由 Codex 生成，次日一早上班优先阅读。</footer>
</main>
<script>
(function () {{
  var root = document.documentElement;
  try {{
    var saved = localStorage.getItem('deep-theme');
    if (saved === 'dark') root.classList.add('dark-mode');
    if (saved === 'light') root.setAttribute('data-theme', 'light');
  }} catch (e) {{}}
  var toggle = document.getElementById('theme-toggle');
  function isDark() {{
    return root.classList.contains('dark-mode') ||
      (root.getAttribute('data-theme') !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }}
  function syncToggle() {{ toggle.textContent = isDark() ? '浅色' : '深色'; }}
  toggle.addEventListener('click', function () {{
    if (isDark()) {{
      root.classList.remove('dark-mode');
      root.setAttribute('data-theme', 'light');
      try {{ localStorage.setItem('deep-theme', 'light'); }} catch (e) {{}}
    }} else {{
      root.removeAttribute('data-theme');
      root.classList.add('dark-mode');
      try {{ localStorage.setItem('deep-theme', 'dark'); }} catch (e) {{}}
    }}
    syncToggle();
  }});
  syncToggle();

  var bar = document.getElementById('progress-bar');
  var backTop = document.getElementById('back-top');
  function onScroll() {{
    var height = document.documentElement.scrollHeight - window.innerHeight;
    bar.style.width = (height > 0 ? (window.scrollY / height) * 100 : 0) + '%';
    backTop.style.display = window.scrollY > 600 ? 'block' : 'none';
  }}
  window.addEventListener('scroll', onScroll, {{ passive: true }});
  onScroll();
  backTop.addEventListener('click', function () {{ window.scrollTo({{ top: 0, behavior: 'smooth' }}); }});

  document.getElementById('expand-all').addEventListener('click', function () {{
    document.querySelectorAll('details.content-section').forEach(function (d) {{ d.open = true; }});
  }});
  document.getElementById('collapse-all').addEventListener('click', function () {{
    document.querySelectorAll('details.content-section').forEach(function (d) {{ d.open = false; }});
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }});
  /* Deep-link: opening #section-id expands it */
  function openTarget() {{
    if (location.hash) {{
      var target = document.getElementById(location.hash.slice(1));
      if (target && target.tagName === 'DETAILS') target.open = true;
    }}
  }}
  openTarget();
  window.addEventListener('hashchange', openTarget);
}})();
</script>
<button id="back-top" type="button" aria-label="回到顶部">↑</button>
</body></html>"""


def main() -> int:
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    validate(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render(data, generation_duration_text=args.generation_duration_text),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
