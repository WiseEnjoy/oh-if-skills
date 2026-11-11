#!/usr/bin/env python3
"""Fetch broad community, paper, and engineering-blog candidates for curation."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any

USER_AGENT = "codex-inference-radar/1.0"
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")

SOURCES: list[dict[str, Any]] = [
    {
        "key": "hackernews-llm-inference",
        "name": "Hacker News",
        "kind": "hackernews",
        "category": "communities",
        "host": "news.ycombinator.com",
        "queries": ["LLM inference", "vLLM", "SGLang", "KV cache", "Ascend NPU"],
        "tier": "tier2",
    },
    {
        "key": "arxiv-llm-inference",
        "name": "arXiv LLM inference",
        "kind": "arxiv",
        "category": "papers",
        "host": "export.arxiv.org",
        "query": (
            '(all:"LLM inference" OR all:"language model inference" OR all:"LLM serving" '
            'OR all:"KV cache" OR all:"speculative decoding" OR cat:cs.DC AND all:"inference")'
        ),
        "tier": "tier2",
    },
    {
        "key": "vllm-blog",
        "name": "vLLM blog",
        "kind": "rss",
        "category": "engineering_blogs",
        "feed": "https://vllm.ai/blog/rss.xml",
        "tier": "tier2",
    },
    {
        "key": "pytorch-blog",
        "name": "PyTorch blog",
        "kind": "rss",
        "category": "engineering_blogs",
        "feed": "https://pytorch.org/blog/feed.xml",
        "tier": "tier2",
    },
    {
        "key": "semianalysis",
        "name": "SemiAnalysis",
        "kind": "rss",
        "category": "engineering_blogs",
        "feed": "https://semianalysis.com/feed",
        "tier": "tier2",
    },
    {
        "key": "interconnects",
        "name": "Interconnects (Nathan Lambert)",
        "kind": "rss",
        "category": "engineering_blogs",
        "feed": "https://www.interconnects.ai/feed",
        "tier": "tier2",
    },
    {
        "key": "qbitai",
        "name": "量子位",
        "kind": "rss",
        "category": "chinese_tech_media",
        "feed": "https://www.qbitai.com/feed",
        "tier": "tier2",
    },
    {
        "key": "hiascend-forum",
        "name": "昇腾社区论坛",
        "kind": "hiascend_forum",
        "category": "huawei_communities",
        "host": "www.hiascend.com",
        "tier": "tier1",
    },
    {
        "key": "mindspore-discuss",
        "name": "MindSpore 论坛",
        "kind": "discourse",
        "category": "huawei_communities",
        "host": "discuss.mindspore.cn",
        "queries": ["推理 order:latest", "vLLM order:latest", "MindSpore Lite Ascend order:latest"],
        "tier": "tier1",
    },
    {
        "key": "mindspore-blog",
        "name": "MindSpore 技术博客",
        "kind": "mindspore_blog",
        "category": "huawei_communities",
        "host": "www.mindspore.cn",
        "feed": "https://www.mindspore.cn/technology-blogs/_payload.json",
        "tier": "tier1",
    },
    {
        "key": "gitcode-huawei-issues",
        "name": "GitCode 华为生态 Issues",
        "kind": "gitcode_search",
        "category": "huawei_communities",
        "host": "gitcode.com",
        "queries": ["org:Ascend llm inference", "org:mindspore vllm inference", "org:cann 推理 量化"],
        "tier": "tier1",
    },
    {
        "key": "bytedance-github-issues",
        "name": "ByteDance GitHub Issues",
        "kind": "github_search",
        "category": "domestic_companies",
        "host": "github.com",
        "query": "org:bytedance vllm",
        "tier": "tier2",
    },
    {
        "key": "alibaba-github-issues",
        "name": "Alibaba/Qwen GitHub Issues",
        "kind": "github_search",
        "category": "domestic_companies",
        "host": "github.com",
        "query": "org:QwenLM vllm",
        "repository_excludes": ["qwen-code", "Qwen3-ASR", "Qwen3.8"],
        "tier": "tier2",
    },
    {
        "key": "tencent-github-issues",
        "name": "Tencent Hunyuan GitHub Issues",
        "kind": "github_search",
        "category": "domestic_companies",
        "host": "github.com",
        "query": "org:Tencent-Hunyuan vllm",
        "repository_excludes": ["UniRL"],
        "tier": "tier2",
    },
    {
        "key": "deepseek-github-issues",
        "name": "DeepSeek GitHub Issues",
        "kind": "github_search",
        "category": "domestic_companies",
        "host": "github.com",
        "query": "org:deepseek-ai inference",
        "tier": "tier2",
    },
    {
        "key": "zhipu-github-issues",
        "name": "Zhipu/THUDM GitHub Issues",
        "kind": "github_search",
        "category": "domestic_companies",
        "host": "github.com",
        "query": "org:THUDM vllm",
        "tier": "tier2",
    },
    {
        "key": "qwen-blog",
        "name": "Qwen Blog",
        "kind": "rss",
        "category": "domestic_companies",
        "feed": "https://qwenlm.github.io/blog/index.xml",
        "tier": "tier2",
    },
]

SOURCE_BY_KEY = {source["key"]: source for source in SOURCES}
RELEVANT_RE = re.compile(
    r"(?i)(?:llm inference|large language model inference|vllm|sglang|"
    r"kv cache|paged attention|flash attention|continuous batching|"
    r"speculative decoding|prefill|decode|tensor parallel|pipeline parallel|"
    r"expert parallel|quantization|fp8|fp4|w4a8|inference (?:latency|throughput|serving)|"
    r"llm serving|npu inference|ttft|tpot|tokens/s"
    r"|大模型推理|推理引擎|推理服务|推理优化|推理显存|推理吞吐|推理延迟|推理量化"
    r"|昇腾|ascend|cann|mindie|mindspeed|mindspore|torch_npu|hccl"
    r"|NPU推理|算子|量化|推理部署|vllm-ascend)"
)
STRICT_INFERENCE_RE = re.compile(
    r"(?i)(?:llm inference|large language model inference|llm serving|"
    r"vllm|sglang|flash attention|flashattention|kv cache|paged attention|"
    r"continuous batching|speculative decoding|prefill|decode|"
    r"tensor parallel|pipeline parallel|expert parallel|"
    r"msmodelslim|mindie|torch_npu|hccl|"
    r"大模型推理|LLM推理|大模型服务|推理引擎|推理服务|推理优化|"
    r"推理量化|推理显存|推理吞吐|推理延迟|伪量化)"
)
STRICT_EXCLUDED_RE = re.compile(
    r"(?i)(?:直播|预告|招聘|开发板|WiFi|HDMI|显示器|ResNet|训练实战|"
    r"混合精度训练|第一课|分工|技术架构全景|算力平台设计|大会|生态|"
    r"checkpoint resume|optimizer|adamw|rollout|training)"
)


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not context.get_ca_certs() and SYSTEM_CA_BUNDLE.exists():
        context.load_verify_locations(cafile=str(SYSTEM_CA_BUNDLE))
    return context


SSL_CONTEXT = ssl_context()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-per-source", type=int, default=40)
    parser.add_argument("--workers", type=int, default=6, help="Concurrent source fetches (default: 6; 1 disables parallelism).")
    parser.add_argument("--source", action="append", help="Source key; may be repeated.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error("--hours must be positive")
    if args.max_per_source <= 0:
        parser.error("--max-per-source must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")
    if args.source:
        unknown = [key for key in args.source if key not in SOURCE_BY_KEY]
        if unknown:
            parser.error("unknown source(s): " + ", ".join(unknown))
    return args


def fetch_bytes(
    url: str,
    timeout: float,
    accept: str = "application/json",
    headers: dict[str, str] | None = None,
) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
            return response.read()
    except Exception:
        curl = subprocess.run(
            [
                "curl", "--fail", "--silent", "--show-error", "--location",
                "--max-time", str(timeout),
                *sum(
                    (["--header", f"{key}: {value}"] for key, value in request_headers.items()),
                    [],
                ),
                url,
            ],
            capture_output=True,
            check=False,
        )
        if curl.returncode != 0:
            raise RuntimeError(curl.stderr.decode("utf-8", errors="replace").strip() or "request failed")
        return curl.stdout


def fetch_json(url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    return json.loads(fetch_bytes(url, timeout, headers=headers).decode("utf-8", errors="replace"))


def parse_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def clean_text(value: str | None, limit: int = 1200) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", unescape(value))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def parse_compact_utc(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return parsed.isoformat()


def make_item(
    source: dict[str, Any],
    *,
    item_id: str,
    title: str,
    url: str,
    timestamp: str,
    summary: str = "",
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "source_key": source["key"],
        "source_name": source["name"],
        "category": source["category"],
        "type": source["kind"],
        "event": "new",
        "id": item_id,
        "title": clean_text(title, 400),
        "url": url,
        "state": "open",
        "timestamp": timestamp,
        "labels": [],
        "summary": clean_text(summary),
        "tier": source.get("tier", "tier2"),
        **metadata,
    }


def source_health(source: dict[str, Any], status: str, count: int, errors: list[str]) -> dict[str, Any]:
    return {
        "key": source["key"],
        "name": source["name"],
        "host": source.get("host", ""),
        "tier": source.get("tier", "tier2"),
        "status": status,
        "count": count,
        "errors": errors,
    }


def relevant(item: dict[str, Any]) -> bool:
    title = item.get("title", "")
    text = title + "\n" + item.get("summary", "")
    if STRICT_EXCLUDED_RE.search(text):
        return False
    if item.get("source_key") == "hiascend-forum":
        return bool(STRICT_INFERENCE_RE.search(title))
    return bool(STRICT_INFERENCE_RE.search(text))


def fetch_hackernews(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in source["queries"]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{int(cutoff.timestamp())}",
                "hitsPerPage": limit,
            }
        )
        try:
            payload = fetch_json(f"https://hn.algolia.com/api/v1/search_by_date?{params}", timeout)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue
        for hit in payload.get("hits", []):
            object_id = str(hit.get("object_id") or hit.get("story_id") or "")
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
            if not object_id or object_id in items:
                continue
            timestamp = datetime.fromtimestamp(hit.get("created_at_i", 0), timezone.utc).isoformat()
            items[object_id] = make_item(
                source,
                item_id=object_id,
                title=hit.get("title") or "",
                url=url,
                timestamp=timestamp,
                summary=hit.get("story_text") or "",
                points=hit.get("points", 0),
                comments=hit.get("num_comments", 0),
            )
    if errors and not items:
        raise RuntimeError("; ".join(errors))
    return [item for item in items.values() if relevant(item)][:limit]


def fetch_lobsters(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    payload = fetch_json("https://lobste.rs/newest.json", timeout)
    for story in payload if isinstance(payload, list) else []:
        timestamp = parse_time(story.get("created_at"))
        if timestamp and datetime.fromisoformat(timestamp) < cutoff:
            continue
        items.append(
            make_item(
                source,
                item_id=str(story.get("short_id") or story.get("id") or story.get("comments_url", "")),
                title=story.get("title") or "",
                url=story.get("comments_url") or story.get("url") or "",
                timestamp=timestamp,
                summary=story.get("description") or " ".join(story.get("tags") or []),
                score=story.get("score", 0),
                comments=story.get("comment_count", 0),
            )
        )
    return [item for item in items if relevant(item)][:limit]


def fetch_reddit(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"limit": min(limit, 100)})
    payload = fetch_json(
        f"https://www.reddit.com/r/{source['subreddit']}/new.json?{params}",
        timeout,
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept": "application/json"},
    )
    items: list[dict[str, Any]] = []
    for child in payload.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        timestamp = datetime.fromtimestamp(post.get("created_utc", 0), timezone.utc).isoformat()
        if datetime.fromisoformat(timestamp) < cutoff:
            continue
        permalink = post.get("url") or post.get("permalink") or ""
        if permalink and permalink.startswith("/"):
            permalink = "https://www.reddit.com" + permalink
        items.append(
            make_item(
                source,
                item_id=str(post.get("id") or permalink),
                title=post.get("title") or "",
                url=permalink,
                timestamp=timestamp,
                summary=post.get("selftext") or "",
                score=post.get("score", 0),
                comments=post.get("num_comments", 0),
                flair=post.get("link_flair_text") or "",
            )
        )
    return [item for item in items if relevant(item)][:limit]


def fetch_arxiv(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search_query": source["query"],
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": min(limit * 2, 80),
        }
    )
    raw = fetch_bytes(
        f"https://export.arxiv.org/api/query?{params}", timeout, accept="application/atom+xml"
    )
    root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    items: list[dict[str, Any]] = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        title = clean_text(entry.findtext("{http://www.w3.org/2005/Atom}title", ""))
        summary = clean_text(entry.findtext("{http://www.w3.org/2005/Atom}summary", ""))
        url = ""
        for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
            if link.get("type") == "application/pdf" or link.get("rel") == "alternate":
                url = link.get("href") or ""
                break
        published = parse_time(entry.findtext("{http://www.w3.org/2005/Atom}published"))
        if not title or not url or not published:
            continue
        if datetime.fromisoformat(published) < cutoff:
            continue
        authors = [
            author.findtext("{http://www.w3.org/2005/Atom}name", "")
            for author in entry.findall("{http://www.w3.org/2005/Atom}author")
        ]
        items.append(
            make_item(
                source,
                item_id=url.rsplit("/", 1)[-1],
                title=title,
                url=url,
                timestamp=published,
                summary=summary,
                authors=[author for author in authors if author],
            )
        )
    return [item for item in items if relevant(item)][:limit]


def child_link(element: ET.Element) -> str:
    for child in element:
        if child.tag.endswith("link") and (child.get("href") or (child.text or "").strip()):
            return child.get("href") or child.text.strip()
    return ""


def first_text(element: ET.Element, names: list[str]) -> str | None:
    for name in names:
        for match in element.iter():
            if match.tag == name or match.tag.endswith("}" + name):
                if match.text and match.text.strip():
                    return match.text.strip()
    return None


def fetch_rss(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    raw = fetch_bytes(source["feed"], timeout, accept="application/rss+xml, application/atom+xml, application/xml")
    xml_text = raw.decode("utf-8", errors="replace")
    if not re.match(r"\s*(?:<\?xml|<rss\b|<feed\b)", xml_text):
        raise RuntimeError("endpoint returned non-feed content, likely blocked or moved")
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for entry in (root.findall(".//item") or root.findall(".//entry"))[: max(limit * 3, 40)]:
        title = clean_text(first_text(entry, ["title"]), 400)
        url = child_link(entry) or first_text(entry, ["link"]) or ""
        timestamp = parse_time(first_text(entry, ["pubDate", "published", "updated", "date"]))
        summary = clean_text(first_text(entry, ["summary", "description", "content", "encoded"]))
        if not title or not url or not timestamp:
            continue
        if datetime.fromisoformat(timestamp) < cutoff:
            continue
        items.append(make_item(source, item_id=url, title=title, url=url, timestamp=timestamp, summary=summary))
    return [item for item in items if relevant(item)][:limit]


def fetch_hiascend_forum(
    source: dict[str, Any], cutoff: datetime, timeout: float, limit: int
) -> list[dict[str, Any]]:
    payload = fetch_json(
        "https://www.hiascend.com/ascendgateway/ascendservice/devCenter/bbs/servlet/get-topic-list",
        timeout,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://www.hiascend.com/forum/",
            "Origin": "https://www.hiascend.com",
        },
    )
    topics = payload.get("data", {}).get("resultList", [])
    if not isinstance(topics, list):
        raise RuntimeError("unexpected Ascend forum payload")
    items: list[dict[str, Any]] = []
    for topic in topics:
        topic_id = str(topic.get("topicId") or "")
        title = topic.get("title") or ""
        if not topic_id or not title:
            continue
        created = parse_compact_utc(topic.get("createTime"))
        last_post = parse_compact_utc(topic.get("lastPostTime"))
        timestamp = last_post or created
        if not timestamp or datetime.fromisoformat(timestamp) < cutoff:
            continue
        items.append(
            make_item(
                source,
                item_id=topic_id,
                title=title,
                url=f"https://www.hiascend.com/forum/thread-{topic_id}-1-1.html",
                timestamp=timestamp,
                summary=topic.get("contentSummary") or "",
                event="new" if created and datetime.fromisoformat(created) >= cutoff else "updated",
                section=topic.get("sectionName") or "",
                views=topic.get("views", 0),
                replies=topic.get("replies", 0),
                likes=topic.get("likes", 0),
            )
        )
    return [item for item in items if relevant(item)][:limit]


def fetch_discourse(
    source: dict[str, Any], cutoff: datetime, timeout: float, limit: int
) -> tuple[list[dict[str, Any]], list[str]]:
    items: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    base_url = f"https://{source['host']}"
    for query in source["queries"]:
        params = urllib.parse.urlencode({"q": query})
        try:
            payload = fetch_json(f"{base_url}/search.json?{params}", timeout)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue
        posts_by_topic = {
            str(post.get("topic_id")): post.get("blurb") or ""
            for post in payload.get("posts", [])
            if isinstance(post, dict)
        }
        for topic in payload.get("topics", []):
            topic_id = str(topic.get("id") or "")
            title = topic.get("title") or topic.get("fancy_title") or ""
            if not topic_id or not title or topic_id in items:
                continue
            created = parse_time(topic.get("created_at"))
            last_post = parse_time(topic.get("last_posted_at") or topic.get("bumped_at"))
            timestamp = last_post or created
            if not timestamp or datetime.fromisoformat(timestamp) < cutoff:
                continue
            slug = topic.get("slug") or "topic"
            tags = [
                tag.get("name") or ""
                for tag in topic.get("tags", [])
                if isinstance(tag, dict) and tag.get("name")
            ]
            items[topic_id] = make_item(
                source,
                item_id=topic_id,
                title=title,
                url=f"{base_url}/t/{slug}/{topic_id}",
                timestamp=timestamp,
                summary=posts_by_topic.get(topic_id, ""),
                event="new" if created and datetime.fromisoformat(created) >= cutoff else "updated",
                state="closed" if topic.get("closed") or topic.get("archived") else "open",
                section="MindSpore 社区",
                replies=topic.get("reply_count", 0),
                posts=topic.get("posts_count", 0),
                tags=tags,
            )
    relevant_items = [item for item in items.values() if relevant(item)]
    relevant_items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return relevant_items[:limit], errors


def dereference_payload(value: dict[str, Any], root: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item < len(root):
            result[key] = root[item]
        else:
            result[key] = item
    return result


def fetch_mindspore_blog(
    source: dict[str, Any], cutoff: datetime, timeout: float, limit: int
) -> list[dict[str, Any]]:
    root = fetch_json(source["feed"], timeout)
    if not isinstance(root, list):
        raise RuntimeError("unexpected MindSpore blog payload")
    items: list[dict[str, Any]] = []
    for value in root:
        if not isinstance(value, dict) or "_path" not in value or "title" not in value:
            continue
        blog = dereference_payload(value, root)
        title = blog.get("title") or ""
        path = blog.get("_path") or ""
        published = blog.get("date") or ""
        if not title or not path or not published:
            continue
        try:
            timestamp = datetime.strptime(published, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
        if datetime.fromisoformat(timestamp) < cutoff:
            continue
        url = urllib.parse.urljoin("https://www.mindspore.cn", path)
        items.append(
            make_item(
                source,
                item_id=path,
                title=title,
                url=url,
                timestamp=timestamp,
                summary=blog.get("description") or "",
                state="published",
                section=blog.get("category") or "",
                blog_type=blog.get("type") or "",
            )
        )
    return [item for item in items if relevant(item)][:limit]


def fetch_gitcode_search(
    source: dict[str, Any], cutoff: datetime, timeout: float, limit: int
) -> tuple[list[dict[str, Any]], list[str]]:
    items: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    allowed_orgs = {"ascend", "mindspore", "cann"}
    for query in source["queries"]:
        params = urllib.parse.urlencode({"q": query})
        headers = {}
        token = os.environ.get("GITCODE_TOKEN")
        if not token:
            try:
                proc = subprocess.run(
                    ["security", "find-generic-password", "-a", "codex", "-s", "gitcode-token", "-w"],
                    check=False, capture_output=True, text=True, timeout=2,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    token = proc.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            payload = fetch_json(f"https://gitcode.com/api/v5/search/issues?{params}", timeout, headers=headers or None)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{query}: expected issue list")
            continue
        for issue in payload:
            issue_id = str(issue.get("id") or "")
            repository = (issue.get("repository") or {}).get("full_name") or ""
            owner = repository.split("/", 1)[0].lower()
            title = issue.get("title") or ""
            url = issue.get("html_url") or ""
            if not issue_id or not title or not url or owner not in allowed_orgs or issue_id in items:
                continue
            created = parse_time(issue.get("created_at"))
            updated = parse_time(issue.get("updated_at"))
            timestamp = updated or created
            if not timestamp or datetime.fromisoformat(timestamp) < cutoff:
                continue
            items[issue_id] = make_item(
                source,
                item_id=issue_id,
                title=title,
                url=url,
                timestamp=timestamp,
                summary=issue.get("body") or "",
                event="updated" if updated and created and updated > created else "new",
                state=issue.get("state") or "open",
                number=issue.get("number") or "",
                repository=repository,
                comments=issue.get("comments", 0),
                labels=issue.get("labels") or [],
            )
    relevant_items = [item for item in items.values() if relevant(item)]
    relevant_items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return relevant_items[:limit], errors


def fetch_github_search(
    source: dict[str, Any], cutoff: datetime, timeout: float, limit: int
) -> list[dict[str, Any]]:
    query = f'{source["query"]} updated:>={cutoff.date().isoformat()}'
    params = urllib.parse.urlencode(
        {"q": query, "per_page": min(limit, 100), "sort": "updated", "order": "desc"}
    )
    payload = fetch_json(f"https://api.github.com/search/issues?{params}", timeout)
    items: dict[str, dict[str, Any]] = {}
    for issue in payload.get("items", []):
        issue_id = str(issue.get("id") or "")
        repository = ((issue.get("repository_url") or "").rsplit("/", 2)[-2:] or [])
        repository = "/".join(repository)
        title = issue.get("title") or ""
        url = issue.get("html_url") or ""
        excluded_repositories = source.get("repository_excludes", [])
        if any(pattern.lower() in repository.lower() for pattern in excluded_repositories):
            continue
        if not issue_id or not title or not url or issue_id in items:
            continue
        created = parse_time(issue.get("created_at"))
        updated = parse_time(issue.get("updated_at"))
        timestamp = updated or created
        if not timestamp or datetime.fromisoformat(timestamp) < cutoff:
            continue
        labels = [label.get("name") or "" for label in issue.get("labels", [])]
        items[issue_id] = make_item(
            source,
            item_id=issue_id,
            title=title,
            url=url,
            timestamp=timestamp,
            summary=issue.get("body") or "",
            event="new" if created and datetime.fromisoformat(created) >= cutoff else "updated",
            state=issue.get("state") or "open",
            number=issue.get("number") or "",
            repository=repository,
            type="pull_request" if issue.get("pull_request") else "issue",
            comments=issue.get("comments", 0),
            labels=[label for label in labels if label],
        )
    relevant_items = [item for item in items.values() if relevant(item)]
    relevant_items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return relevant_items[:limit]


def fetch_huggingface_papers(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> list[dict[str, Any]]:
    """Daily papers from the Hugging Face API, ranked by community upvotes."""
    payload = fetch_json("https://huggingface.co/api/daily_papers", timeout)
    items: list[dict[str, Any]] = []
    for entry in payload if isinstance(payload, list) else []:
        paper = entry.get("paper") or {}
        paper_id = str(paper.get("id") or "")
        title = paper.get("title") or ""
        published = parse_time(paper.get("publishedAt"))
        if not paper_id or not title or not published:
            continue
        if datetime.fromisoformat(published) < cutoff:
            continue
        url = f"https://huggingface.co/papers/{paper_id}"
        summary = clean_text(paper.get("summary"))
        upvotes = paper.get("upvotes", 0)
        if upvotes < 10:
            continue
        authors = [
            (author.get("name") or author.get("user") or "")
            for author in (paper.get("authors") or [])[:6]
            if isinstance(author, dict)
        ]
        items.append(
            make_item(
                source,
                item_id=paper_id,
                title=title,
                url=url,
                timestamp=published,
                summary=summary,
                points=upvotes,
                authors=[author for author in authors if author],
            )
        )
    items.sort(key=lambda item: item.get("points", 0), reverse=True)
    return items[:limit]


def fetch_source(source: dict[str, Any], cutoff: datetime, timeout: float, limit: int) -> tuple[list[dict[str, Any]], str, list[str]]:
    try:
        if source["kind"] == "hackernews":
            return fetch_hackernews(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "lobsters":
            return fetch_lobsters(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "reddit":
            return fetch_reddit(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "arxiv":
            return fetch_arxiv(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "huggingface_papers":
            return fetch_huggingface_papers(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "rss":
            return fetch_rss(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "hiascend_forum":
            return fetch_hiascend_forum(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "discourse":
            items, errors = fetch_discourse(source, cutoff, timeout, limit)
            if errors and items:
                return items, "degraded", errors
            if errors and any("429" in error or "rate limit" in error.lower() for error in errors):
                return items, "rate_limited", errors
            return items, ("ok" if not errors else "failed"), errors
        if source["kind"] == "mindspore_blog":
            return fetch_mindspore_blog(source, cutoff, timeout, limit), "ok", []
        if source["kind"] == "gitcode_search":
            items, errors = fetch_gitcode_search(source, cutoff, timeout, limit)
            if errors and items:
                return items, "degraded", errors
            if errors and any("429" in error or "rate limit" in error.lower() for error in errors):
                return items, "rate_limited", errors
            return items, ("ok" if not errors else "failed"), errors
        if source["kind"] == "github_search":
            return fetch_github_search(source, cutoff, timeout, limit), "ok", []
    except Exception as exc:
        message = str(exc)
        status = "rate_limited" if "rate limit" in message.lower() or "429" in message else "failed"
        return [], status, [message]
    return [], "failed", [f"unsupported source kind: {source['kind']}"]


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(timezone.utc)
    cutoff = generated_at - timedelta(hours=args.hours)
    selected_sources = (
        [SOURCE_BY_KEY[key] for key in args.source]
        if args.source
        else SOURCES
    )
    workers = min(args.workers, len(selected_sources)) or 1
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(
                lambda source: fetch_source(source, cutoff, args.timeout, args.max_per_source),
                selected_sources,
            ))
    else:
        fetched = [fetch_source(source, cutoff, args.timeout, args.max_per_source) for source in selected_sources]
    items: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source, (source_items, status, source_errors) in zip(selected_sources, fetched):
        items.extend(source_items)
        sources.append({
            **source_health(source, status, len(source_items), source_errors),
            "category": source["category"],
            "kind": source["kind"],
            "endpoints": [{"endpoint": source["kind"], "status": status, "count": len(source_items), "errors": source_errors}],
            "item_count": len(source_items),
        })
        for message in source_errors:
            errors.append({"source_key": source["key"], "message": message})
    items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    output = {
        "schema_version": 1,
        "generated_at_utc": generated_at.isoformat(),
        "repository_window_hours": args.hours,
        "repository_cutoff_utc": cutoff.isoformat(),
        "selected_sources": args.source or ["all"],
        "selected_categories": [
            "communities", "papers", "engineering_blogs", "chinese_tech_media",
            "huawei_communities", "domestic_companies"
        ],
        "source_policy": {
            "cann_primary_host": "gitcode",
            "gitee_used": False,
            "broad_intake": True,
            "note": "Broad domestic and international community, paper, and blog candidates are priors for Codex curation; they are not automatically published in the daily report.",
        },
        "sources": sources,
        "items": items,
        "podcast_episodes": [],
        "errors": errors,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=None if args.compact else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not args.compact else ""), encoding="utf-8")
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
