#!/usr/bin/env python3
"""Mark candidates that already appeared in a previous curated report."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\[[^]]*\]", " ", text)
    for word in ("需求建议", "缺陷反馈", "文档反馈", "商分分支", "商分", "分支", "问题", "修复", "fix", "feat", "requirement", "bug-report"):
        text = text.replace(word, " ")
    return re.sub(r"[^a-z0-9一-鿿]+", "", text)[:70]


def load_seen_keys(history_dir: Path, current_date: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Collect normalized title keys and URLs from all curated reports before current_date."""
    seen_keys: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    if not history_dir.is_dir():
        return seen_keys, seen_urls
    for path in sorted(history_dir.glob("inference-radar-curated-*.json")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})\.json$", path.name)
        if not match or match.group(1) >= current_date:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get("items", []):
            if isinstance(item, dict):
                source_key = item.get("source_key") or ""
                seen_keys.add((source_key, _normalize(item.get("title") or "")))
                if item.get("url"):
                    seen_urls.add(item["url"])
    return seen_keys, seen_urls


def apply_history_markers(
    candidates: list[dict],
    seen_keys: set[tuple[str, str]],
    seen_urls: set[str],
) -> None:
    """In-place: set seen_before / seen_dates on each candidate."""
    for item in candidates:
        key = (item.get("source_key") or "", _normalize(item.get("title") or ""))
        hit = key in seen_keys or (item.get("url") in seen_urls and bool(item.get("url")))
        item["seen_before"] = hit
        if hit:
            item["curation_hint"] = (
                "This item already appeared in a previous daily report. Skip it unless there is a "
                "material new development (state change, new evidence, follow-up discussion) worth a fresh entry."
            )
