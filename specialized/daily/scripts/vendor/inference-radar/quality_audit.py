#!/usr/bin/env python3
"""Audit fetched Inference Radar JSON against the skill's quality gates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CATEGORY_SOURCES = {
    "engines": {"vllm", "vllm-ascend", "sglang", "sgl-kernel-npu", "sglang-ascend-roadmap",
                 "tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp", "xllm"},
    "frameworks": {"pytorch", "torch_npu"},
    "operators": {"cann-ops-math", "cann-ops-transformer", "cann-ops-nn", "cann-ops-cv", "cann-pypto"},
    "communications": {"hccl", "hcomm"},
    "podcasts": {"practical-ai", "mlst"},
    "communities": {"hackernews-llm-inference"},
    "papers": {"arxiv-llm-inference"},
    "engineering_blogs": {"vllm-blog", "pytorch-blog",
                           "semianalysis", "interconnects"},
    "chinese_tech_media": {"qbitai"},
    "huawei_communities": {
        "hiascend-forum", "mindspore-discuss", "mindspore-blog", "gitcode-huawei-issues"
    },
    "domestic_companies": {
        "bytedance-github-issues", "alibaba-github-issues", "tencent-github-issues",
        "deepseek-github-issues", "zhipu-github-issues", "qwen-blog"
    },
}
EXPECTED_SOURCES = set().union(*CATEGORY_SOURCES.values())
GITCODE_REQUIRED = {
    "torch_npu", "cann-ops-math", "cann-ops-transformer", "cann-ops-nn",
    "cann-ops-cv", "cann-pypto", "hccl", "hcomm",
}
LLM_INFERENCE_SOURCES = {
    "vllm", "vllm-ascend", "sglang", "sgl-kernel-npu", "sglang-ascend-roadmap",
    "tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp",
    "xllm", "pytorch", "torch_npu", "cann-ops-math",
    "cann-ops-transformer", "cann-ops-nn", "cann-pypto", "hccl", "hcomm",
    "hiascend-forum", "mindspore-discuss", "mindspore-blog", "gitcode-huawei-issues",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def expected_keys(data: dict) -> set[str]:
    selected_sources = data.get("selected_sources") or ["all"]
    selected_categories = data.get("selected_categories") or ["all"]
    if selected_sources != ["all"]:
        expected = set(selected_sources)
    elif selected_categories != ["all"]:
        expected = set()
        for category in selected_categories:
            expected.update(CATEGORY_SOURCES.get(category, set()))
    else:
        expected = EXPECTED_SOURCES
    if data.get("selected_focus") == "llm-inference":
        expected &= LLM_INFERENCE_SOURCES
    return expected


def main() -> int:
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []
    sources = {source.get("key"): source for source in data.get("sources", [])}
    expected = expected_keys(data)
    missing = sorted(expected - set(sources))
    extra = sorted(set(sources) - expected)
    if missing:
        failures.append(f"missing sources: {', '.join(missing)}")
    if extra:
        warnings.append(f"unexpected sources: {', '.join(extra)}")

    for key in sorted(GITCODE_REQUIRED & set(sources)):
        source = sources[key]
        repository = source.get("repository") or ""
        if source.get("host") != "gitcode":
            failures.append(f"{key}: expected GitCode host")
        elif not repository or repository.count("/") != 1:
            failures.append(f"{key}: expected owner/repository format, got {repository!r}")

    if data.get("source_policy", {}).get("gitee_used") is not False:
        failures.append("source_policy must state that Gitee is not used")

    cutoff_raw = data.get("repository_cutoff_utc")
    if not cutoff_raw:
        failures.append("repository_cutoff_utc is missing")
    else:
        cutoff = iso(cutoff_raw)
        for item in data.get("items", []):
            key = item.get("source_key", "?")
            title = (item.get("title") or "").strip()
            url = item.get("url") or ""
            timestamp = item.get("timestamp")
            event = item.get("event")
            if not title:
                failures.append(f"{key}: item has empty title")
            if not url or not url.startswith(("http://", "https://")):
                failures.append(f"{key}: item has invalid URL: {title!r}")
            else:
                if host(url) == "gitee.com":
                    failures.append(f"{key}: Gitee link found: {url}")
                expected_host = (sources.get(key) or {}).get("host")
                if expected_host == "gitcode" and host(url) != "gitcode.com":
                    failures.append(f"{key}: GitCode source has non-GitCode URL: {url}")
                if expected_host == "github" and host(url) != "github.com":
                    failures.append(f"{key}: GitHub source has non-GitHub URL: {url}")
            if not timestamp:
                failures.append(f"{key}: item has no timestamp: {title!r}")
            elif iso(timestamp) < cutoff:
                failures.append(f"{key}: item outside time window: {title!r}")
            if event not in ("new", "updated"):
                failures.append(f"{key}: invalid event {event!r}: {title!r}")

    endpoint_states = {"ok", "failed", "degraded", "rate_limited", "auth_required"}
    for source in data.get("sources", []):
        key = source.get("key", "?")
        if source.get("status") not in endpoint_states:
            failures.append(f"{key}: invalid source status {source.get('status')!r}")
        for endpoint in source.get("endpoints", []):
            if endpoint.get("status") not in endpoint_states:
                failures.append(f"{key}/{endpoint.get('endpoint')}: invalid endpoint status")

    for episode in data.get("podcast_episodes", []):
        title = episode.get("title")
        url = episode.get("url") or ""
        if not title or not url.startswith(("http://", "https://")):
            failures.append(f"podcast: invalid episode {title!r}")
        if episode.get("difficulty") not in ("入门", "进阶", "高阶"):
            warnings.append(f"podcast: difficulty missing for {title!r}")

    auth_required = [key for key, source in sources.items() if source.get("status") == "auth_required"]
    rate_limited = [key for key, source in sources.items() if source.get("status") == "rate_limited"]
    failed = [key for key, source in sources.items() if source.get("status") == "failed"]
    degraded_sources = [key for key, source in sources.items() if source.get("status") == "degraded"]
    global_errors = data.get("errors") or []
    data_complete = not auth_required and not rate_limited and not failed and not degraded_sources and not global_errors
    result = {
        # `passed` means schema and source-policy checks passed. Data completeness
        # is reported separately so a structurally valid partial fetch is never
        # mistaken for a complete daily scan.
        "passed": not failures,
        "schema_passed": not failures,
        "data_complete": data_complete,
        "degraded": not data_complete,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "scope_sources": sorted(expected),
        "failures": failures,
        "warnings": warnings,
        "source_count": len(sources),
        "item_count": len(data.get("items", [])),
        "podcast_count": len(data.get("podcast_episodes", [])),
        "failed_source_count": len(failed),
        "rate_limited_source_count": len(rate_limited),
        "degraded_source_count": len(degraded_sources),
        "auth_required_source_count": len(auth_required),
        "rate_limited_sources": rate_limited,
        "auth_required_sources": auth_required,
        "failed_sources": failed,
        "degraded_sources": degraded_sources,
        "global_errors": global_errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
