#!/usr/bin/env python3
"""Skill tags: validate curated tags against skill_map.json and aggregate coverage.

Curators tag each radar item and each deep-report section with `skill_tags`
(domain tags from skill_map.json, optionally `domain/skill` pairs). This
module is the single source of truth for what a valid tag is, and it turns
tagged history into a coverage view.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

SKILL_MAP_PATH = Path(__file__).with_name("skill_map.json")


def load_map(path: Path = SKILL_MAP_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_tags(skill_map: dict[str, Any] | None = None) -> set[str]:
    """All acceptable tag values: bare domains (`quantization`) and pairs (`quantization/mxfp`)."""
    skill_map = skill_map or load_map()
    tags: set[str] = set()
    for domain in skill_map["domains"]:
        tags.add(domain["tag"])
        for skill in domain["skills"]:
            tags.add(f"{domain['tag']}/{skill}")
    return tags


def validate_item_tags(item: dict[str, Any], skill_map: dict[str, Any] | None = None) -> list[str]:
    """Return the list of invalid tags on one curated item (empty list = OK)."""
    allowed = valid_tags(skill_map)
    return [tag for tag in (item.get("skill_tags") or []) if tag not in allowed]


def normalize_tag(tag: str) -> str:
    """Reduce `domain/skill` pairs to the domain for coverage counting."""
    return tag.split("/", 1)[0]


def coverage_from_curated_dirs(
    curated_paths: list[Path],
    skill_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate domain coverage across curated radar reports (last N days).

    Returns per-domain read counts, item examples, and zero-coverage domains,
    which the renderer turns into the heatmap section.
    """
    skill_map = skill_map or load_map()
    domains = {domain["tag"]: domain["name"] for domain in skill_map["domains"]}
    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = {tag: [] for tag in domains}
    report_days: set[str] = set()

    for path in curated_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        report_days.add(data.get("date") or path.stem)
        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            seen_domains: set[str] = set()
            for tag in item.get("skill_tags") or []:
                domain = normalize_tag(tag)
                if domain in domains and domain not in seen_domains:
                    seen_domains.add(domain)
                    counts[domain] += 1
                    if len(examples[domain]) < 3 and item.get("title"):
                        examples[domain].append({"date": data.get("date", ""), "title": item["title"], "url": item.get("url", "")})

    return {
        "report_days": sorted(report_days),
        "domains": [
            {
                "tag": tag,
                "name": domains[tag],
                "read_count": counts.get(tag, 0),
                "examples": examples[tag],
            }
            for tag in domains
        ],
        "zero_coverage_domains": [tag for tag in domains if counts.get(tag, 0) == 0],
        "total_tagged_items": sum(counts.values()),
    }
