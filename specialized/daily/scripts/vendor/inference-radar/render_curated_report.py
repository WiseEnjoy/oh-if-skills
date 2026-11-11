#!/usr/bin/env python3
"""Render the HTML report from a Codex-curated JSON file."""

from __future__ import annotations

import argparse
import html
import json
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
from zoneinfo import ZoneInfo

VENDOR_DIR = Path(__file__).resolve().parent
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

READING_SECTIONS = [
    ("industry", "外层 · 推理框架与产业实践", "vLLM、SGLang、PyTorch、论文、工程博客和通用社区中已经可借鉴的成熟优化；先看产业方向，再看 NPU 适配。"),
    ("adaptation", "中层 · 框架与 Ascend/NPU 适配", "vLLM Ascend、SGLang NPU、XLLM、torch_npu、MindSpore 等适配层，关注通用能力如何落到昇腾推理路径。"),
    ("kernel", "内层 · CANN 算子、图与通信", "CANN 算子、PyPTO、HCCL/HCOMM 等内核层，决定正确性、性能、显存和多机稳定性。"),
    ("frontier", "前沿 · 开发中与研究信号", "路线图、开发中特性和论文级机制；只保留有明确背景、验证路径或 Ascend 借鉴价值的信号。"),
]
TERMINOLOGY_NOTES = [
    ("LLM / KV cache / TTFT", "large language model、key-value cache、time to first token。"),
    ("MoE / MLA / TP / EP / PP", "Mixture-of-Experts、Multi-head Latent Attention、tensor parallelism、expert parallelism、pipeline parallelism。"),
    ("GEMM / grouped GEMM / PA / LSE", "general matrix multiplication、分组矩阵乘、paged attention、log-sum-exp。源代码中的 GMM 是 grouped matmul 的项目缩写，本文保留原文。"),
    ("MXFP4 / MXFP8", "microscaling floating-point 4-bit/8-bit format；具体编码和 scale 粒度以所引用实现及 MX 格式规范为准。"),
    ("A8W4 / W4A4 / W8A8", "activation 与 weight 的低比特数值精度写法；不同项目的字段顺序可能不同，语义以源代码定义为准。"),
    ("RoPE / SwiGLU", "rotary position embedding、SwiGLU activation。"),
    ("prefill / decode", "prefill 处理输入 prompt 并生成首个 token；decode 逐 token 生成后续输出。"),
    ("graph capture / replay / eager mode", "图捕获、图回放与逐算子立即执行模式。"),
    ("speculative decoding / draft / verify / prefix cache", "speculative decoding 先由 draft 模型或路径提出候选 token，再由 verify 步骤验证；prefix cache 复用相同前缀的 KV cache。"),
    ("cosine similarity / P99 latency", "余弦相似度用于比较 tensor 或逐层输出；P99 latency 表示 99 分位延迟。"),
    ("communication overlap / distributed serving", "通信与计算重叠调度；多卡或多节点推理 serving。"),
    ("prefill/decode disaggregation", "prefill 与 decode 阶段分离部署的 serving 架构。"),
]
NON_STANDARD_INTERPRETATION_TERMS = (
    "P/D 节点",
    "PD serving",
    "SiTU 激活",
    "Mamba 混合缓存",
)
READING_SECTION_BY_TIER = {"tier2": "industry", "tier1": "adaptation", "tier0": "kernel"}
MATURITY_ORDER = {"production": 0, "engineering": 1, "development": 2, "research": 3}
MATURITY_LABELS = {
    "production": "成熟可借鉴",
    "engineering": "工程可用待验证",
    "development": "开发中",
    "research": "研究/前瞻",
}
ALLOWED_TIERS = set(READING_SECTION_BY_TIER)
REQUIRED_ITEM_FIELDS = [
    "source_key", "source_name", "tier", "type", "event", "state", "title",
    "url", "timestamp", "why_it_matters", "verification", "priority",
]
SCHEMA_V3_FIELDS = ["background", "optimization", "maturity", "engineering_takeaway"]

PALETTES = [
    {
        "name": "ocean",
        "ink": "#111827", "muted": "#4b5563", "line": "#cbd5e1", "bg": "#f1f5f9",
        "card": "#ffffff", "accent": "#1d4ed8", "soft": "#e8eefc",
        "header_start": "#0f172a", "header_end": "#1e40af", "header_muted": "#f8fafc",
        "dark": {
            "bg": "#0a1120", "card": "#101a2e", "ink": "#e6ecf8", "muted": "#9aa8c0",
            "line": "#2a3a5e", "soft": "#18233c", "accent": "#82aaff",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(154,168,192,.16)", "chip_text": "#c3cad6",
            "ok_bg": "rgba(74,222,128,.14)", "warn_bg": "rgba(251,191,36,.14)",
            "bad_bg": "rgba(248,113,113,.14)", "info_bg": "rgba(130,170,255,.16)",
            "info_text": "#a5c2ff", "research_bg": "rgba(192,132,252,.16)", "research_text": "#d3b3ff",
        },
    },
    {
        "name": "forest",
        "ink": "#10241a", "muted": "#43554a", "line": "#cbd8d0", "bg": "#f2f7f4",
        "card": "#ffffff", "accent": "#166534", "soft": "#e6f4ec",
        "header_start": "#072416", "header_end": "#14532d", "header_muted": "#f8fafc",
        "dark": {
            "bg": "#0a140f", "card": "#0f2018", "ink": "#e4f0e8", "muted": "#93b3a2",
            "line": "#244435", "soft": "#163024", "accent": "#7cd9a8",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(147,179,162,.15)", "chip_text": "#c6d8cd",
            "ok_bg": "rgba(74,222,128,.14)", "warn_bg": "rgba(251,191,36,.14)",
            "bad_bg": "rgba(248,113,113,.14)", "info_bg": "rgba(124,217,168,.14)",
            "info_text": "#9fe6c2", "research_bg": "rgba(192,132,252,.14)", "research_text": "#d3b3ff",
        },
    },
    {
        "name": "graphite",
        "ink": "#111827", "muted": "#4b5563", "line": "#d1d5db", "bg": "#f3f4f6",
        "card": "#ffffff", "accent": "#1f2937", "soft": "#e9eaee",
        "header_start": "#0b1120", "header_end": "#374151", "header_muted": "#f8fafc",
        "dark": {
            "bg": "#0c0e11", "card": "#16191e", "ink": "#e8eaee", "muted": "#9aa2ad",
            "line": "#2c313a", "soft": "#1d222a", "accent": "#9db8dd",
            "good": "#4ade80", "bad": "#f87171", "warn": "#fbbf24",
            "chip_bg": "rgba(154,162,173,.15)", "chip_text": "#c8ccd4",
            "ok_bg": "rgba(74,222,128,.13)", "warn_bg": "rgba(251,191,36,.13)",
            "bad_bg": "rgba(248,113,113,.13)", "info_bg": "rgba(157,184,221,.14)",
            "info_text": "#b7cdf0", "research_bg": "rgba(192,132,252,.14)", "research_text": "#d3b3ff",
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
    args = parser.parse_args()
    return args


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def beijing_time(timestamp: str) -> str:
    """Render a UTC ISO timestamp as Beijing local time; fall back to the raw value."""
    if not timestamp:
        return "—"
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")


def validate(data: dict[str, Any]) -> None:
    for key in (
        "schema_version", "date", "scope", "executive_summary", "items",
        "actions", "data_health", "generated_at_utc",
    ):
        if key not in data:
            raise ValueError(f"missing top-level key: {key}")
    if data["schema_version"] not in {2, 3}:
        raise ValueError("curated report schema_version must be 2 or 3")
    datetime.strptime(data["date"], "%Y-%m-%d")
    if not 3 <= len(data["executive_summary"]) <= 5:
        raise ValueError("executive_summary must contain 3-5 bullets")
    if not 1 <= len(data["items"]) <= 40:
        raise ValueError("items must contain 1-40 curated entries")
    if not data["actions"]:
        raise ValueError("actions must not be empty")
    if len(data["actions"]) > 5:
        raise ValueError("at most five actions are allowed")

    seen_urls: set[str] = set()
    required_fields = list(REQUIRED_ITEM_FIELDS)
    if data["schema_version"] == 3:
        required_fields = [
            field for field in required_fields if field != "why_it_matters"
        ] + SCHEMA_V3_FIELDS
    for index, item in enumerate(data["items"], 1):
        for field in required_fields:
            if not item.get(field):
                raise ValueError(f"item {index}: missing {field}")
        parsed = urlparse(item["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"item {index}: invalid URL")
        if item["url"] in seen_urls:
            raise ValueError(f"item {index}: duplicate URL")
        seen_urls.add(item["url"])
        if item["tier"] not in ALLOWED_TIERS:
            raise ValueError(f"item {index}: invalid tier {item['tier']}")
        if item.get("reading_layer") and item["reading_layer"] not in {key for key, _title, _description in READING_SECTIONS}:
            raise ValueError(f"item {index}: invalid reading_layer {item['reading_layer']}")
        if data["schema_version"] == 3 and item["maturity"] not in MATURITY_ORDER:
            raise ValueError(f"item {index}: invalid maturity {item['maturity']}")
        if item["event"] not in {"new", "updated"}:
            raise ValueError(f"item {index}: invalid event")
        if item["priority"] not in {"must-read", "worth-attention", "context"}:
            raise ValueError(f"item {index}: invalid priority")
        if len(item["verification"]) < 30:
            raise ValueError(f"item {index}: verification must be at least 30 characters")
        primary_judgment = (
            item["engineering_takeaway"] if data["schema_version"] == 3 else item["why_it_matters"]
        )
        if len(primary_judgment) < 30:
            raise ValueError(f"item {index}: engineering judgment must be at least 30 characters")
        if primary_judgment.strip() == item["verification"].strip():
            raise ValueError(f"item {index}: verification must not repeat why_it_matters")
        if data["schema_version"] == 3:
            for field in ("background", "optimization", "engineering_takeaway"):
                if len(item[field]) < 30:
                    raise ValueError(f"item {index}: {field} must be at least 30 characters")
            interpretation_fields = [
                *data["executive_summary"],
                item["background"], item["optimization"],
                item["engineering_takeaway"], item["verification"],
            ]
            for text in interpretation_fields:
                for term in NON_STANDARD_INTERPRETATION_TERMS:
                    if term in text:
                        raise ValueError(f"item {index}: non-standard interpretation term: {term}")

    for index, action in enumerate(data["actions"], 1):
        for field in ("title", "detail", "evidence_urls"):
            if not action.get(field):
                raise ValueError(f"action {index}: missing {field}")
        if len(action["detail"]) < 40:
            raise ValueError(f"action {index}: detail must be at least 40 characters")
        for term in NON_STANDARD_INTERPRETATION_TERMS:
            if term in action["title"] or term in action["detail"]:
                raise ValueError(f"action {index}: non-standard interpretation term: {term}")
        for url in action["evidence_urls"]:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"action {index}: invalid evidence URL")

    # skill_tags are the curation-side hookup for the coverage heatmap. Invalid
    # values fail loudly so typos never silently zero out the heatmap; missing
    # tags are allowed for schema-2 reports and older curated files.
    import skill_tags
    try:
        skill_map = skill_tags.load_map()
    except OSError:
        return
    invalid = skill_tags.validate_item_tags
    for index, item in enumerate(data["items"], 1):
        bad = invalid(item, skill_map)
        if bad:
            raise ValueError(f"item {index}: invalid skill_tags: {', '.join(bad)}")


def render_item(item: dict[str, Any]) -> str:
    priority = item["priority"]
    state = item.get("state", "unknown")
    state_css = "ok" if state == "merged" else ("warn" if state == "open" else "")
    labels = " · ".join(item.get("labels") or []) or "—"
    maturity = item.get("maturity")
    maturity_badge = (
        f"<span class='badge maturity-{e(maturity)}'>{e(MATURITY_LABELS[maturity])}</span>"
        if maturity in MATURITY_ORDER else ""
    )
    if "background" in item:
        background = f"<p><strong>优化背景：</strong>{e(item['background'])}</p>"
        optimization = f"<p><strong>具体优化：</strong>{e(item['optimization'])}</p>"
        takeaway = f"<p><strong>工程启示：</strong>{e(item['engineering_takeaway'])}</p>"
    else:
        background = ""
        optimization = ""
        takeaway = f"<p><strong>为什么重要：</strong>{e(item['why_it_matters'])}</p>"
    anchor = item.get("source_key") or ""
    seen_badge = "<span class='badge seen-badge'>前日报道</span>" if item.get("seen_before") else ""
    skill_tag_badges = "".join(
        f"<span class='badge skill-tag'>{e(tag)}</span>"
        for tag in (item.get("skill_tags") or [])
    )
    return f"""
<article class="item priority-{e(priority)}" id="{e(anchor)}">
  <div class="item-head">
    <div><h3>{e(item['title'])}</h3><p class="meta">{e(item['source_name'])} · {e(item['type'])} · {e(item['event'])} · <span class="badge {state_css}">{e(state)}</span> · {e(beijing_time(item['timestamp']))} 北京 {maturity_badge}{seen_badge}</p></div>
    <span class="priority">{e(priority)}</span>
  </div>
  <p class="meta">labels: {e(labels)}{f" · 同题更新 ×{e(item['duplicate_count'])}" if item.get('duplicate_count', 1) > 1 else ''}{f" <span class='skill-tags'>{skill_tag_badges}</span>" if skill_tag_badges else ''}</p>
  <p><a href="{e(item['url'])}" target="_blank" rel="noopener">原始证据</a> <button class="copy-link" data-anchor="{e(anchor)}" title="复制本文锚点链接">复制链接</button></p>
  <div class="analysis">{background}{optimization}{takeaway}<p><strong>验证建议：</strong>{e(item['verification'])}</p></div>
</article>"""


def reading_layer(item: dict[str, Any]) -> str:
    layer = item.get("reading_layer")
    if layer in {key for key, _title, _description in READING_SECTIONS}:
        return layer
    if item.get("maturity") == "research":
        return "frontier"
    return READING_SECTION_BY_TIER[item["tier"]]


def reading_sort(item: dict[str, Any]) -> tuple[int, int]:
    priority_order = {"must-read": 0, "worth-attention": 1, "context": 2}
    return (
        MATURITY_ORDER.get(item.get("maturity"), 2),
        priority_order.get(item["priority"], 3),
    )


def main() -> int:
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    validate(data)
    health = data.get("data_health", {})
    source_rows = []
    for source in health.get("sources", []):
        status = source.get("status", "unknown")
        css = "ok" if status == "ok" else ("warn" if status in {"auth_required", "rate_limited", "degraded"} else "bad")
        errors = "; ".join(source.get("errors") or []) or "—"
        source_rows.append(f"<tr><td>{e(source.get('name'))}</td><td>{e(source.get('tier', ''))}</td><td><span class='badge {css}'>{e(status)}</span></td><td>{e(source.get('count', 0))}</td><td>{e(errors)}</td></tr>")

    reading_sections = []
    section_index = 4
    for layer, title, description in READING_SECTIONS:
        items = [item for item in data["items"] if reading_layer(item) == layer]
        items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        items.sort(key=reading_sort)
        content = "".join(render_item(item) for item in items) or "<p class='empty'>本期无重要动态。</p>"
        reading_sections.append(f"<section id='{layer}'><h2>{section_index} · {e(title)}</h2><p class='meta'>{e(description)} · 入选 {len(items)} 条</p><div class='tier-grid'>{content}</div></section>")
        section_index += 1

    summary_html = "".join(f"<li>{e(text)}</li>" for text in data["executive_summary"])
    action_html = []
    for action in data["actions"]:
        links = " · ".join(f"<a href='{e(url)}' target='_blank' rel='noopener'>证据</a>" for url in action["evidence_urls"])
        action_html.append(f"<article><h3>{e(action['title'])}</h3><p>{e(action['detail'])}</p><p>{links}</p></article>")

    # Coverage heatmap: tag counts across the last 30 days of curated reports.
    import skill_tags
    heatmap_html = ""
    try:
        curated_dir = args.input.resolve().parent
        history_paths = sorted(curated_dir.glob("inference-radar-curated-*.json"))
        cutoff_day = (datetime.strptime(data["date"], "%Y-%m-%d") - timedelta(days=30)).date()
        recent_paths = [
            path for path in history_paths
            if path.name >= f"inference-radar-curated-{cutoff_day.isoformat()}.json"
        ]
        if recent_paths:
            coverage = skill_tags.coverage_from_curated_dirs(recent_paths)
            if coverage["total_tagged_items"]:
                max_count = max((domain["read_count"] for domain in coverage["domains"]), default=1) or 1
                heat_rows = []
                for domain in coverage["domains"]:
                    intensity = domain["read_count"] / max_count
                    examples_html = "".join(
                        f"<li><a href='{e(ex['url'])}' target='_blank' rel='noopener'>{e(ex['title'])}</a></li>"
                        for ex in domain["examples"][:2]
                    ) or "<li class='meta'>—</li>"
                    heat_rows.append(
                        f"<tr><td>{e(domain['name'])} <code>{e(domain['tag'])}</code></td>"
                        f"<td><span class='heat-cell' style='opacity:{0.15 + intensity * 0.85:.2f}'>{domain['read_count']}</span></td>"
                        f"<td><ul class='heat-examples'>{examples_html}</ul></td></tr>"
                    )
                zero_note = ""
                if coverage["zero_coverage_domains"]:
                    names = "、".join(
                        next(d["name"] for d in coverage["domains"] if d["tag"] == tag)
                        for tag in coverage["zero_coverage_domains"]
                    )
                    zero_note = f"<p class='meta'>近 30 天零覆盖：{e(names)} —— 适合排入深读计划。</p>"
                heatmap_html = (
                    f"<section id='skill-coverage'><h2>能力覆盖热力图（近 30 天阅读）</h2>"
                    f"<div class='table-wrap'><table><thead><tr><th>能力域</th><th>条目数</th><th>近期示例</th></tr></thead>"
                    f"<tbody>{''.join(heat_rows)}</tbody></table></div>{zero_note}"
                    f"<p class='meta'>共 {e(str(coverage['total_tagged_items']))} 条打了能力标签 · 覆盖 {e(str(len(coverage['report_days'])))} 天报告。阅读数低的能力域说明该方向动态少或关注不足，结合深读排期判断。</p></section>"
                )
    except (OSError, ValueError):
        heatmap_html = ""

    # Carried-over verification actions from the ledger, with their age.
    carried_html = ""
    carried = data.get("carried_actions") or []
    if carried:
        rows = []
        for action in carried:
            added = action.get("added_at", "")
            age = ""
            if added:
                try:
                    age_days = (datetime.strptime(data["date"], "%Y-%m-%d") - datetime.strptime(added, "%Y-%m-%d")).days
                    age = f"<span class='badge seen-badge'>已挂 {age_days} 天</span>"
                except ValueError:
                    pass
            links = " · ".join(f"<a href='{e(url)}' target='_blank' rel='noopener'>证据</a>" for url in (action.get("evidence_urls") or []))
            rows.append(f"<article><h3>{e(action.get('title', ''))} {age}</h3><p>{e(action.get('detail', ''))}</p><p>{links}</p></article>")
        ledger_stats = data.get("ledger_stats") or {}
        done_count = ledger_stats.get("done", 0)
        oldest = ledger_stats.get("oldest_open_days", 0)
        carried_html = (
            f"<section id='carried-actions'><h2>未闭环的验证行动</h2>"
            f"<p class='meta'>以下行动来自此前报告且尚未完成（共 {len(carried)} 项，历史已完成 {done_count} 项，最久未动 {oldest} 天）。完成后让 Codex 在台账中关闭对应条目。</p>"
            f"<div class='actions'>{''.join(rows)}</div></section>"
        )

    toc_entries = [
        "<li><a href=\"#terminology\">术语约定</a></li>",
        "<li><a href=\"#data-health\">数据健康</a></li>",
        "<li><a href=\"#executive-summary\">Executive Summary</a></li>",
    ]
    toc_entries.extend(
        f"<li><a href=\"#{layer}\">{title}</a></li>"
        for layer, title, _description in READING_SECTIONS
    )
    if heatmap_html:
        toc_entries.append("<li><a href=\"#skill-coverage\">能力覆盖热力图</a></li>")
    if carried_html:
        toc_entries.append("<li><a href=\"#carried-actions\">未闭环行动</a></li>")
    toc_entries.append("<li><a href=\"#actions\">今日行动</a></li>")

    generated = data.get("generated_at_utc", "")
    generation_duration = data.get("generation_duration_text") or args.generation_duration_text
    palette = select_palette(data["date"], "inference-radar")
    palette_css = palette_variables(palette)
    dark_css = dark_palette_variables(palette["dark"])
    item_count = len(data["items"])
    must_read_count = sum(1 for item in data["items"] if item["priority"] == "must-read")
    est_minutes = max(5, round(item_count * 1.8 + len(data["executive_summary"]) * 0.5))
    unhealthy_statuses = {"failed", "rate_limited", "degraded", "auth_required"}
    unhealthy_sources = [source for source in health.get("sources", []) if source.get("status") in unhealthy_statuses]
    health_badge = "降级" if unhealthy_sources or health.get("errors") else "完整"
    health_note = health.get("health_note") or (
        f"GitHub token：{'是' if health.get('github_token_present') else '否'} · "
        f"GitCode token：{'是' if health.get('gitcode_token_present') else '否'}"
    )
    rendered = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LLM 推理优化雷达 · {e(data['date'])}</title>
<style>
:root{{--good:#16803c;--bad:#b42318;--warn:#b54708;{palette_css}}}
:root.dark-mode{{--{dark_css}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;transition:background .2s,color .2s}} main{{width:100%;max-width:none;padding:clamp(16px,2.5vw,44px) clamp(16px,3vw,56px) clamp(32px,4vw,64px)}} header{{background:linear-gradient(135deg,var(--header-start),var(--header-end));color:#fff;border-radius:12px;padding:clamp(20px,3vw,36px);margin-bottom:clamp(14px,2vw,24px)}} header h1{{margin:0 0 8px;font-size:clamp(24px,3.2vw,38px);font-weight:800;letter-spacing:0;text-shadow:0 1px 2px rgba(0,0,0,.28)}} header p{{margin:4px 0;color:var(--header-muted)}} .toc{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:clamp(14px,2vw,22px);margin-bottom:clamp(14px,2vw,22px)}} .toc h2{{margin:0 0 12px;font-size:16px}} .toc ol{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:8px 24px;margin:0;padding:0;list-style:none;counter-reset:toc}} .toc li{{counter-increment:toc;min-width:0}} .toc li::before{{content:counter(toc,decimal-leading-zero) " · ";color:var(--muted);font-variant-numeric:tabular-nums}} .toc a{{display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom}} section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:clamp(16px,2.2vw,28px);margin-bottom:clamp(14px,2vw,22px)}} h2{{margin:0 0 14px;font-size:20px}} h3{{margin:0;font-size:17px}} .meta{{color:var(--muted);font-size:13px}} .table-wrap{{overflow-x:auto}} table{{width:100%;min-width:760px;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}} th{{color:var(--muted);font-size:13px;white-space:nowrap}} .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:10px 28px;margin:0;padding-left:22px}} .tier-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,620px),1fr));gap:14px;align-items:start}} .item{{border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:8px;padding:16px;margin:0;background:var(--card)}} .item-head{{display:flex;justify-content:space-between;gap:14px}} .priority{{flex:0 0 auto;border-radius:999px;padding:3px 10px;background:var(--chip-bg,var(--soft));color:var(--chip-text,var(--ink));font-size:12px;height:fit-content}} .priority-must-read{{background:var(--bad-bg,#fee2e2);color:var(--bad)}} .priority-worth-attention{{background:var(--warn-bg,#fef0c7);color:var(--warn)}} .priority-context{{background:var(--info-bg,var(--soft));color:var(--accent)}} .analysis{{background:var(--soft);border-radius:8px;padding:12px}} .badge{{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;background:var(--chip-bg,#e5e7eb);color:var(--chip-text,#374151)}} .badge.ok{{background:var(--ok-bg,#dcfce7);color:var(--good)}} .badge.warn{{background:var(--warn-bg,#fef0c7);color:var(--warn)}} .badge.bad{{background:var(--bad-bg,#fee2e2);color:var(--bad)}} .badge.seen-badge{{background:var(--warn-bg,#fef0c7);color:var(--warn)}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} .actions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px}} .actions article{{border:1px solid var(--line);border-radius:8px;padding:16px;margin:0;background:var(--card)}} .empty{{color:var(--muted)}} footer{{color:var(--muted);font-size:13px;text-align:center;padding-top:4px}}
.maturity-production{{background:var(--ok-bg,#dcfce7);color:var(--good)}} .maturity-engineering{{background:var(--info-bg,#dbeafe);color:var(--info-text,var(--accent))}} .maturity-development{{background:var(--warn-bg,#fef0c7);color:var(--warn)}} .maturity-research{{background:var(--research-bg,#f3e8ff);color:var(--research-text,#7c3aed)}}
.glossary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:14px}} .glossary article{{border:1px solid var(--line);border-radius:8px;padding:16px;margin:0;background:var(--card)}}
.copy-link{{border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:6px;padding:1px 8px;font-size:12px;cursor:pointer;margin-left:6px}} .copy-link:hover{{background:var(--soft)}}
#progress-bar{{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:99;transition:width .08s linear}}
#back-top{{position:fixed;right:clamp(12px,2vw,28px);bottom:clamp(12px,2vw,28px);border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:999px;width:44px;height:44px;font-size:18px;cursor:pointer;display:none;box-shadow:0 2px 10px rgba(0,0,0,.15);z-index:98}}
#back-top:hover{{background:var(--soft)}}
#theme-toggle{{float:right;border:1px solid rgba(255,255,255,.35);background:rgba(255,255,255,.12);color:#fff;border-radius:999px;padding:5px 14px;font-size:13px;cursor:pointer}}
#theme-toggle:hover{{background:rgba(255,255,255,.22)}}
.filter-bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}} .filter-bar button{{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:4px 14px;font-size:13px;cursor:pointer}} .filter-bar button.active{{background:var(--accent);color:var(--bg);border-color:var(--accent)}}
.filter-bar .read-estimate{{margin-left:auto;color:var(--muted);font-size:13px}}
.heat-cell{{display:inline-block;min-width:44px;text-align:center;border-radius:6px;padding:2px 10px;background:var(--accent);color:var(--bg);font-weight:700;font-variant-numeric:tabular-nums}} .heat-examples{{margin:0;padding-left:18px;font-size:13px}} .skill-tags{{margin-left:6px}} .badge.skill-tag{{background:var(--info-bg,var(--soft));color:var(--info-text,var(--accent));margin-right:4px}}
@media(max-width:800px){{.item-head{{display:block}}.priority{{display:inline-block;margin-top:8px}}table{{min-width:680px}}.filter-bar .read-estimate{{width:100%;margin:4px 0 0}}}}
@media print{{.toc,.filter-bar,#back-top,#progress-bar,#theme-toggle,.copy-link{{display:none}}body{{background:#fff}}section{{break-inside:avoid;box-shadow:none}}.item{{page-break-inside:avoid}}a{{color:inherit}}.item a[href]::after,.analysis a[href]::after{{content:""}}
}}
:root.dark-mode header{{background:var(--card);border:1px solid var(--line)}} :root.dark-mode #theme-toggle{{border-color:var(--line);background:var(--soft);color:var(--ink)}}
@media (prefers-color-scheme: dark){{ :root:not([data-theme="light"]):not(.dark-mode){{--{dark_css}}}}}
:root[data-theme="dark"]{{--{dark_css}}}
</style>{HEADER_CSS}</head><body><main>
<div id="progress-bar" aria-hidden="true"></div>
<header><button id="theme-toggle" type="button" aria-label="切换深浅色">深色</button><h1>LLM 推理优化雷达 · {e(data['date'])}</h1><p>{e(data['scope'])}</p><p>生成时间：{e(generated)} UTC · 数据健康：{e(health_badge)} · Codex 模型解析 + API 证据链 · 配色：{e(palette['name'])}</p><p>耗时：{e(generation_duration)}</p></header>
<nav class="toc" aria-label="目录"><h2>目录</h2><ol>{''.join(toc_entries)}</ol></nav>
<div class="filter-bar" role="toolbar" aria-label="优先级过滤"><span class="meta">过滤：</span>
<button data-filter="all" class="active">全部</button>
<button data-filter="must-read">必读（{must_read_count}）</button>
<button data-filter="worth-attention">值得关注</button>
<button data-filter="context">背景</button>
<span class="read-estimate">{item_count} 条 · 预计 {est_minutes} 分钟</span>
</div>
<section id="terminology"><h2>1 · 术语约定</h2><div class="glossary">{''.join(f"<article><h3>{e(term)}</h3><p>{e(meaning)}</p></article>" for term, meaning in TERMINOLOGY_NOTES)}</div><p class="meta">QFA、C8、SiTU、ScatterPa、KVPP、GDN、FD、BSND、BNSD、FRACTAL_NZ 等为上游实现名、精度/布局标识或模型结构名；本文保留原文，未在证据中定义的缩写不强行展开。原始标题中的非规范简称也按证据原文保留。</p></section>
<section id="data-health"><h2>2 · 数据健康</h2><div class="table-wrap"><table><thead><tr><th>来源</th><th>层级</th><th>状态</th><th>数量</th><th>错误</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div><p class="meta">{e(health_note)}</p></section>
<section id="executive-summary"><h2>3 · Executive Summary</h2><ul class="summary">{summary_html}</ul></section>
{''.join(reading_sections)}
{heatmap_html}
{carried_html}
<section id="actions"><h2>{len(READING_SECTIONS) + 4} · 今日行动</h2><div class="actions">{''.join(action_html)}</div></section>
<footer>数据来自公开代码托管平台、论文、工程博客、华为社区与国内外专业社区 API；“优化背景/具体优化/工程启示/验证建议/优先级”由 Codex 基于证据解析生成，性能与根因仍需实验验证。术语遵循行业共识，上游专有名称保持原文；成熟度按稳定发布、工程验证、开发中、研究四级保守标注。生成节奏：每晚下班前由 Codex 生成，次日一早上班优先阅读。</footer>
</main>
<script>
(function () {{
  /* Theme: persist choice, default to system preference */
  var root = document.documentElement;
  try {{
    var saved = localStorage.getItem('radar-theme');
    if (saved === 'dark') root.classList.add('dark-mode');
    if (saved === 'light') root.setAttribute('data-theme', 'light');
  }} catch (e) {{}}
  var toggle = document.getElementById('theme-toggle');
  function syncToggle() {{
    var dark = root.classList.contains('dark-mode') ||
      (root.getAttribute('data-theme') !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    toggle.textContent = dark ? '浅色' : '深色';
  }}
  toggle.addEventListener('click', function () {{
    var dark = root.classList.contains('dark-mode') ||
      (root.getAttribute('data-theme') !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) {{
      root.classList.remove('dark-mode');
      root.setAttribute('data-theme', 'light');
      try {{ localStorage.setItem('radar-theme', 'light'); }} catch (e) {{}}
    }} else {{
      root.removeAttribute('data-theme');
      root.classList.add('dark-mode');
      try {{ localStorage.setItem('radar-theme', 'dark'); }} catch (e) {{}}
    }}
    syncToggle();
  }});
  syncToggle();

  /* Reading progress + back-to-top */
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

  /* Copy item anchor link */
  document.querySelectorAll('.copy-link').forEach(function (button) {{
    button.addEventListener('click', function () {{
      var url = location.origin + location.pathname + '#' + button.getAttribute('data-anchor');
      var done = function () {{
        var original = button.textContent;
        button.textContent = '已复制';
        setTimeout(function () {{ button.textContent = original; }}, 1200);
      }};
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(url).then(done);
      }} else {{
        var input = document.createElement('textarea');
        input.value = url;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        done();
      }}
    }});
  }});

  /* Priority filter */
  var buttons = document.querySelectorAll('.filter-bar button');
  buttons.forEach(function (button) {{
    button.addEventListener('click', function () {{
      var filter = button.getAttribute('data-filter');
      buttons.forEach(function (other) {{ other.classList.toggle('active', other === button); }});
      document.querySelectorAll('article.item').forEach(function (item) {{
        var show = filter === 'all' || item.classList.contains('priority-' + filter);
        item.style.display = show ? '' : 'none';
      }});
      document.querySelectorAll('section[id]').forEach(function (section) {{
        if (section.id === 'actions') return;
        var items = section.querySelectorAll('article.item');
        var visible = Array.prototype.some.call(items, function (item) {{ return item.style.display !== 'none'; }});
        if (items.length) section.style.display = visible ? '' : 'none';
      }});
    }});
  }});
}})();
</script>
<button id="back-top" type="button" aria-label="回到顶部">↑</button>
</body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
