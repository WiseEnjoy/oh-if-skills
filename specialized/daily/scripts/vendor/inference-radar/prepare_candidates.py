#!/usr/bin/env python3
"""Prepare a compact, evidence-preserving candidate pool for Codex model curation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import build_report as engine
import history_markers


BROAD_SOURCE_KEYS = {
    "hackernews-llm-inference", "lobsters-llm-inference", "reddit-localllama",
    "reddit-machinelearning", "arxiv-llm-inference", "huggingface-papers",
    "vllm-blog", "huggingface-blog", "pytorch-blog", "nvidia-developer-blog",
    "semianalysis", "interconnects",
    "jiqizhixin", "qbitai", "infoq-cn", "hiascend-forum",
    "mindspore-discuss", "mindspore-blog", "gitcode-huawei-issues",
    "bytedance-github-issues", "alibaba-github-issues", "tencent-github-issues",
    "deepseek-github-issues", "zhipu-github-issues", "qwen-blog",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--history-dir", type=Path, help="Directory holding prior curated reports for seen-before marking.")
    parser.add_argument("--max-per-tier", type=int, default=60)
    parser.add_argument("--min-score", type=int, default=engine.MIN_SELECTION_SCORE)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error("--date must use YYYY-MM-DD")
    if args.max_per_tier <= 0:
        parser.error("--max-per-tier must be positive")
    return args


def public_fields(item: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "source_key", "source_name", "category", "type", "event", "id", "number",
        "title", "url", "state", "timestamp", "author", "labels", "comments",
        "reactions_total", "matched_keywords", "draft", "prerelease", "merged_at",
        "closed_at", "created_at", "updated_at", "published_at", "body_excerpt",
        "summary", "points", "comments", "flair", "authors",
        "repository", "section", "views", "replies", "likes",
    ]
    result = {key: item.get(key) for key in fields}
    result.update(
        {
            "machine_score": item["score"],
            "machine_theme": item["theme"],
            "tier": item["tier"],
            "duplicate_count": item["duplicate_count"],
        }
    )
    return result


def main() -> int:
    args = parse_args()
    data = engine.merge_inputs(args.inputs)
    relevant = [item for item in data.get("items", []) if engine.llm_relevant(item)]

    ranked = sorted(relevant, key=lambda item: (engine.score(item), item.get("timestamp", "")), reverse=True)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in ranked:
        key = engine.title_key(item)
        if key in grouped:
            grouped[key]["duplicate_count"] += 1
            continue
        grouped[key] = {
            **item,
            "score": engine.score(item),
            "theme": engine.theme(item),
            "tier": engine.tier_for(item),
            "duplicate_count": 1,
        }

    candidates = [
        item for item in grouped.values()
        if item["score"] >= args.min_score or item.get("source_key") in BROAD_SOURCE_KEYS
    ]
    if args.history_dir:
        seen_keys, seen_urls = history_markers.load_seen_keys(args.history_dir, args.date)
        history_markers.apply_history_markers(candidates, seen_keys, seen_urls)
    candidates.sort(key=lambda item: (item["score"], item.get("timestamp", "")), reverse=True)
    by_tier: dict[str, list[dict[str, Any]]] = {tier: [] for tier, _title, _desc in engine.TIER_DEFINITIONS}
    for item in candidates:
        by_tier.setdefault(item["tier"], []).append(item)

    trimmed: list[dict[str, Any]] = []
    for tier, _title, _desc in engine.TIER_DEFINITIONS:
        tier_items = by_tier.get(tier, [])[: args.max_per_tier]
        broad_items = [
            item for item in by_tier.get(tier, [])
            if item.get("source_key") in BROAD_SOURCE_KEYS
        ][:12]
        broad_ids = {id(item) for item in broad_items}
        for broad_item in broad_items:
            if any(id(item) == id(broad_item) for item in tier_items):
                continue
            replacement_index = next(
                (index for index in range(len(tier_items) - 1, -1, -1)
                 if id(tier_items[index]) not in broad_ids),
                None,
            )
            if replacement_index is not None:
                tier_items[replacement_index] = broad_item
        trimmed.extend(tier_items)
    trimmed.sort(
        key=lambda item: (
            next(index for index, (tier, _t, _d) in enumerate(engine.TIER_DEFINITIONS) if tier == item["tier"]),
            -item["score"],
            item.get("timestamp", ""),
        )
    )

    source_health = []
    for source in data.get("sources", []):
        source_health.append(
            {
                "key": source.get("key"),
                "name": source.get("name"),
                "host": source.get("host"),
                "tier": source.get("tier") or engine.TIER_LABELS.get(source.get("key", ""), ""),
                "status": source.get("status"),
                "count": source.get("count", source.get("item_count")),
                "errors": source.get("errors", []),
            }
        )

    output = {
        "schema_version": 2,
        "date": args.date,
        "purpose": "Codex model curation input; machine scores are priors, not final judgments",
        "data_health": {
            "sources": source_health,
            "errors": data.get("errors", []),
            "github_token_present": data.get("github_token_present", False),
            "gitcode_token_present": data.get("gitcode_token_present", False),
            "repository_cutoff_utc": data.get("repository_cutoff_utc"),
            "repository_window_hours": data.get("repository_window_hours"),
            "source_policy": data.get("source_policy", {}),
        },
        "raw_update_count": len(data.get("items", [])),
        "llm_filter_passed_count": len(relevant),
        "candidate_pool_count": len(candidates),
        "presented_candidate_count": len(trimmed),
        "broad_candidate_count": sum(item.get("source_key") in BROAD_SOURCE_KEYS for item in trimmed),
        "candidate_tier_counts": dict(Counter(item["tier"] for item in candidates)),
        "presented_tier_counts": dict(Counter(item["tier"] for item in trimmed)),
        "minimum_machine_score": args.min_score,
        "history_check": {
            "history_dir": str(args.history_dir) if args.history_dir else None,
            "seen_before_count": sum(1 for item in candidates if item.get("seen_before")),
        },
        "model_curation_target": {
            "evidence_tiers": {"tier0": 20, "tier1": 7, "tier2": 5},
            "reading_layers": {"industry": 7, "runtime": 8, "kernel": 13, "frontier": 4},
        },
        "candidates": [public_fields(item) for item in trimmed],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=None if args.compact else 2) + "\n", encoding="utf-8")
    if not args.compact:
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
