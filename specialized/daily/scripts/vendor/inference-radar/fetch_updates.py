#!/usr/bin/env python3
"""Fetch recent GitHub/GitCode repository updates and AI podcast candidates.

The script is intentionally dependency-free. It emits JSON so Codex can rank,
summarize, and clearly distinguish data from analysis.
"""

from __future__ import annotations

import argparse
import email.utils
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
GITCODE_API = "https://api.gitcode.com/api/v5"
USER_AGENT = "codex-inference-radar/1.0"
DEFAULT_PER_PAGE = 100
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")


def build_ssl_context() -> ssl.SSLContext:
    """Use the Python default trust store, with a macOS system bundle fallback."""
    context = ssl.create_default_context()
    if not context.get_ca_certs() and SYSTEM_CA_BUNDLE.exists():
        context.load_verify_locations(cafile=str(SYSTEM_CA_BUNDLE))
    return context


SSL_CONTEXT = build_ssl_context()

RELEVANT_KEYWORDS = [
    "ascend", "npu", "cann", "aclnn", "torch_npu", "privateuse1",
    "quant", "fp8", "w8a8", "int4", "int8", "graph", "compile",
    "flash attention", "flashattention", "paged attention", "kv cache",
    "moe", "speculative decoding", "distributed inference", "tensor parallel",
    "pipeline parallel", "expert parallel", "communication", "profil",
    "operator", "matmul", "attention", "memory", "scheduler", "lora",
]


SOURCES: list[dict[str, Any]] = [
    {
        "key": "vllm",
        "category": "engines",
        "name": "vLLM",
        "kind": "repository",
        "host": "github",
        "owner": "vllm-project",
        "repo": "vllm",
    },
    {
        "key": "vllm-ascend",
        "category": "engines",
        "name": "vLLM Ascend",
        "kind": "repository",
        "host": "github",
        "owner": "vllm-project",
        "repo": "vllm-ascend",
    },
    {
        "key": "sglang",
        "category": "engines",
        "name": "SGLang",
        "kind": "repository",
        "host": "github",
        "owner": "sgl-project",
        "repo": "sglang",
    },
    {
        "key": "sgl-kernel-npu",
        "category": "engines",
        "name": "SGLang Kernel NPU",
        "kind": "repository",
        "host": "github",
        "owner": "sgl-project",
        "repo": "sgl-kernel-npu",
    },
    {
        "key": "sglang-ascend-roadmap",
        "category": "engines",
        "name": "SGLang Ascend roadmap and support matrix",
        "kind": "issue_details",
        "host": "github",
        "owner": "sgl-project",
        "repo": "sglang",
        "issue_numbers": [13664, 18967],
    },
    {
        "key": "tensorrt-llm",
        "category": "engines",
        "name": "TensorRT-LLM",
        "kind": "repository",
        "host": "github",
        "owner": "NVIDIA",
        "repo": "TensorRT-LLM",
        "keyword_filter": True,
    },
    {
        "key": "mooncake",
        "category": "engines",
        "name": "Mooncake",
        "kind": "repository",
        "host": "github",
        "owner": "kvcache-ai",
        "repo": "mooncake",
    },
    {
        "key": "lmdeploy",
        "category": "engines",
        "name": "LMDeploy",
        "kind": "repository",
        "host": "github",
        "owner": "InternLM",
        "repo": "lmdeploy",
    },
    {
        "key": "llama-cpp",
        "category": "engines",
        "name": "llama.cpp",
        "kind": "repository",
        "host": "github",
        "owner": "ggml-org",
        "repo": "llama.cpp",
        "keyword_filter": True,
    },
    {
        "key": "xllm",
        "category": "engines",
        "name": "XLLM",
        "kind": "repository",
        "host": "github",
        "owner": "xLLM-AI",
        "repo": "xllm",
        "github_html_fallback": True,
        "skip_endpoints": ["releases"],
    },
    {
        "key": "pytorch",
        "category": "frameworks",
        "name": "PyTorch",
        "kind": "repository",
        "host": "github",
        "owner": "pytorch",
        "repo": "pytorch",
        "keyword_filter": True,
    },
    {
        "key": "torch_npu",
        "category": "frameworks",
        "name": "torch_npu",
        "kind": "repository",
        "host": "gitcode",
        "owner": "Ascend",
        "repo": "op-plugin",
    },
    {
        "key": "cann-ops-math",
        "category": "operators",
        "name": "CANN ops-math",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "ops-math",
    },
    {
        "key": "cann-ops-transformer",
        "category": "operators",
        "name": "CANN ops-transformer",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "ops-transformer",
    },
    {
        "key": "cann-ops-nn",
        "category": "operators",
        "name": "CANN ops-nn",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "ops-nn",
    },
    {
        "key": "cann-ops-cv",
        "category": "operators",
        "name": "CANN ops-cv",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "ops-cv",
    },
    {
        "key": "cann-pypto",
        "category": "operators",
        "name": "CANN PyPTO",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "PyPTO",
    },
    {
        "key": "hccl",
        "category": "communications",
        "name": "HCCL",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "HCCL",
    },
    {
        "key": "hcomm",
        "category": "communications",
        "name": "HCOMM",
        "kind": "repository",
        "host": "gitcode",
        "owner": "cann",
        "repo": "HCOMM",
    },
    {
        "key": "practical-ai",
        "category": "podcasts",
        "name": "Practical AI",
        "kind": "podcast",
        "feed": "https://changelog.com/practicalai/feed",
        "site": "https://changelog.com/practicalai",
        "difficulty": "入门",
        "track": "applied AI context",
    },
    {
        "key": "latent-space",
        "category": "podcasts",
        "name": "Latent Space",
        "kind": "podcast",
        "feed": "https://www.latent.space/feed",
        "site": "https://www.latent.space",
        "difficulty": "进阶",
        "track": "AI engineering and systems",
    },
    {
        "key": "mlst",
        "category": "podcasts",
        "name": "Machine Learning Street Talk",
        "kind": "podcast",
        "site": "https://www.mlst.ai",
        "difficulty": "高阶",
        "track": "deep technical discussion",
    },
    {
        "key": "dwarkesh",
        "category": "podcasts",
        "name": "Dwarkesh Podcast",
        "kind": "podcast",
        "site": "https://www.dwarkesh.com/podcast",
        "difficulty": "高阶",
        "track": "research and frontier thinking",
    },
    {
        "key": "twiml",
        "category": "podcasts",
        "name": "TWIML AI Podcast",
        "kind": "podcast",
        "site": "https://twimlai.com",
        "difficulty": "进阶",
        "track": "applied ML and interviews",
    },
]

SOURCE_BY_KEY = {source["key"]: source for source in SOURCES}

# LLM-inference scope: exclude generic CV/training/application churn. ops-cv is
# intentionally absent; include an LLM-relevant ops-cv item only by explicit
# --repo cann-ops-cv and with a clear justification in the report.
LLM_INFERENCE_SOURCES = {
    "vllm", "vllm-ascend", "sglang", "sgl-kernel-npu", "sglang-ascend-roadmap",
    "tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp",
    "xllm", "pytorch", "torch_npu", "cann-ops-math",
    "cann-ops-transformer", "cann-ops-nn", "cann-pypto", "hccl", "hcomm",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch recent inference ecosystem updates and podcast candidates."
    )
    parser.add_argument("--hours", type=int, default=24, help="Repository update window in hours (default: 24).")
    parser.add_argument(
        "--focus",
        choices=["llm-inference"],
        help="Fetch only repositories needed for large-language-model inference. Excludes podcasts and cann-ops-cv.",
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=["engines", "frameworks", "operators", "communications", "podcasts"],
        help="Category to fetch. May be repeated. Defaults to all categories.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        help="Repository/source key to fetch, e.g. vllm or torch_npu. May be repeated.",
    )
    parser.add_argument("--podcast-days", type=int, default=30, help="Podcast freshness window in days (default: 30).")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent source fetches (default: 6; 1 disables parallelism).")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds per request.")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    args = parser.parse_args()

    if args.hours <= 0:
        parser.error("--hours must be positive")
    if args.podcast_days <= 0:
        parser.error("--podcast-days must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")
    if args.repo:
        unknown = [key for key in args.repo if key not in SOURCE_BY_KEY]
        if unknown:
            valid = ", ".join(SOURCE_BY_KEY)
            parser.error(f"unknown source key(s): {', '.join(unknown)}. Valid keys: {valid}")
    return args


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    # RSS pubDate
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    # ISO 8601, including Z suffix
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def request(
    url: str,
    *,
    token: str | None = None,
    github: bool = False,
    timeout: float = 20.0,
    json_response: bool = True,
    retries_left: int = 1,
) -> tuple[Any, dict[str, str]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json" if github else "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request_obj = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout, context=SSL_CONTEXT) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers_out = {key.lower(): value for key, value in response.headers.items()}
            content_type = headers_out.get("content-type", "")
            if not json_response:
                return body, headers_out
            data = json.loads(body)
            return data, headers_out
    except urllib.error.HTTPError as exc:
        remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        detail = f"HTTP {exc.code}"
        try:
            body = exc.read().decode("utf-8", errors="replace")
            if body:
                detail += f": {body[:500]}"
        except Exception:
            pass
        if exc.code == 429 or (exc.code in (403, 404) and remaining == "0"):
            raise RateLimitedError(detail, retry_after=retry_after) from exc
        if retries_left > 0 and exc.code in {500, 502, 503, 504}:
            time.sleep(1.5)
            return request(url, token=token, github=github, timeout=timeout, json_response=json_response, retries_left=retries_left - 1)
        raise FetchError(detail, status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if retries_left > 0 and any(needle in reason.lower() for needle in ("timed out", "timeout", "reset", "temporarily unavailable")):
            time.sleep(1.5)
            return request(url, token=token, github=github, timeout=timeout, json_response=json_response, retries_left=retries_left - 1)
        raise FetchError(f"network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FetchError("request timed out") from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid JSON response: {exc}") from exc


class FetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitedError(FetchError):
    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


def api_base(host: str) -> str:
    return GITHUB_API if host == "github" else GITCODE_API


def token_for(host: str) -> str | None:
    if host == "github":
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            return token
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-a", "codex", "-s", "github-token", "-w"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None
    return os.environ.get("GITCODE_TOKEN")


def append_query(url: str, params: dict[str, Any]) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query.extend((str(key), str(value)) for key, value in params.items())
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def strip_code_blocks(value: Any) -> str:
    """Markdown body text with code fences removed, whitespace collapsed."""
    if not value or not isinstance(value, str):
        return ""
    text = re.sub(r"```.*?(?:```|\Z)", " ", value, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def matched_keywords(item: dict[str, Any]) -> list[str]:
    searchable = " ".join(
        text_of(item.get(field)) for field in ("title", "body", "summary", "description", "name", "tag_name")
    ).lower()
    return [keyword for keyword in RELEVANT_KEYWORDS if keyword in searchable]


def normalized_author(raw: dict[str, Any]) -> str | None:
    for field in ("user", "owner", "author"):
        candidate = raw.get(field)
        if isinstance(candidate, dict):
            login = candidate.get("login") or candidate.get("username") or candidate.get("name")
            if login:
                return str(login)
    return None


def normalize_common_item(
    raw: dict[str, Any],
    *,
    item_type: str,
    source: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any] | None:
    created = parse_datetime(raw.get("created_at"))
    updated = parse_datetime(raw.get("updated_at"))
    published = parse_datetime(raw.get("published_at"))
    timestamp = updated or published or created
    if timestamp is None:
        return None
    if timestamp < cutoff and (created is None or created < cutoff):
        return None

    url = raw.get("html_url") or raw.get("url")
    title = raw.get("title") or raw.get("name") or raw.get("tag_name")
    if not url or not title:
        return None

    labels = []
    for label in raw.get("labels") or []:
        if isinstance(label, str):
            labels.append(label)
        elif isinstance(label, dict):
            name = label.get("name") or label.get("title")
            if name:
                labels.append(str(name))

    reactions = raw.get("reactions") or {}
    result: dict[str, Any] = {
        "source_key": source["key"],
        "source_name": source["name"],
        "category": source["category"],
        "type": item_type,
        "event": "new" if (created and created >= cutoff) or (published and published >= cutoff) else "updated",
        "id": raw.get("id") or raw.get("number"),
        "number": raw.get("number"),
        "title": str(title),
        "url": str(url),
        "state": raw.get("state"),
        "created_at": isoformat(created),
        "updated_at": isoformat(updated),
        "published_at": isoformat(published),
        "timestamp": isoformat(timestamp),
        "author": normalized_author(raw),
        "labels": labels,
        "comments": raw.get("comments"),
        "reactions_total": reactions.get("total_count") if isinstance(reactions, dict) else None,
        "matched_keywords": [],
        "draft": raw.get("draft"),
        "prerelease": raw.get("prerelease"),
        "merged_at": isoformat(parse_datetime(raw.get("merged_at"))),
        "closed_at": isoformat(parse_datetime(raw.get("closed_at"))),
    }
    body = strip_code_blocks(raw.get("body"))
    result["body_excerpt"] = body[:800] if body else None
    result["matched_keywords"] = matched_keywords({**raw, "title": title, "body": body})
    return result


def fetch_github_html_search(
    source: dict[str, Any],
    endpoint: str,
    *,
    cutoff: datetime,
    timeout: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fallback for API-limited GitHub repositories using GitHub search HTML.

    The query filters by `updated:>=cutoff`; therefore an observed item is an
    updated item in the requested window even when the exact update timestamp is
    not exposed by the search page. The item timestamp is the observation time,
    not a fabricated GitHub timestamp.
    """
    if endpoint not in {"pulls", "issues"}:
        raise ValueError(f"HTML fallback does not support endpoint: {endpoint}")
    kind = "pr" if endpoint == "pulls" else "issue"
    query = (
        f"repo:{source['owner']}/{source['repo']} is:{kind} "
        f"updated:>={cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')} sort:updated-desc"
    )
    url = "https://github.com/search?" + urllib.parse.urlencode({"q": query, "type": "issues"})
    try:
        proc = subprocess.run(
            ["curl", "-L", "--max-time", str(int(max(1, timeout))), "-A", "Mozilla/5.0", "-sS", url],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError(f"GitHub HTML fallback failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:300]
        raise FetchError(f"GitHub HTML fallback failed with curl exit {proc.returncode}: {detail}")

    body = proc.stdout
    repo_path = f"/{source['owner']}/{source['repo']}/issues/"
    pattern = re.compile(
        r'href="' + re.escape(repo_path) + r'(\d+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    observed = now_utc()
    by_number: dict[int, dict[str, Any]] = {}
    for match in pattern.finditer(body):
        number = int(match.group(1))
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        title = re.sub(r"\s+", " ", unescape(title)).strip()
        if not title or title.startswith("#") or number in by_number:
            continue
        item_type = "pull_request" if endpoint == "pulls" else "issue"
        path = "pull" if endpoint == "pulls" else "issues"
        item = {
            "source_key": source["key"],
            "source_name": source["name"],
            "category": source["category"],
            "type": item_type,
            "event": "updated",
            "id": number,
            "number": number,
            "title": title,
            "url": f"https://github.com/{source['owner']}/{source['repo']}/{path}/{number}",
            "state": "unknown",
            "created_at": None,
            "updated_at": isoformat(observed),
            "published_at": None,
            "timestamp": isoformat(observed),
            "author": None,
            "labels": [],
            "comments": None,
            "reactions_total": None,
            "matched_keywords": matched_keywords({"title": title}),
            "draft": None,
            "prerelease": None,
            "merged_at": None,
            "closed_at": None,
            "evidence_method": "github_html_search_updated_filter",
            "evidence_query": query,
        }
        by_number[number] = item
    items = list(by_number.values())
    return items, {
        "endpoint": endpoint,
        "status": "degraded",
        "count": len(items),
        "filtered_out": 0,
        "evidence_url": url,
        "fallback": "github_html_search",
        "note": "GitHub API rate limit was bypassed with an HTML search filtered by updated:>=cutoff; exact update timestamps are not exposed.",
    }


def fetch_endpoint(
    source: dict[str, Any],
    endpoint: str,
    *,
    cutoff: datetime,
    timeout: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = api_base(source["host"])
    owner = source["owner"]
    repo = source["repo"]
    token = token_for(source["host"])

    if endpoint == "pulls":
        url = f"{base}/repos/{owner}/{repo}/pulls"
        params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": DEFAULT_PER_PAGE}
        item_type = "pull_request"
    elif endpoint == "issues":
        url = f"{base}/repos/{owner}/{repo}/issues"
        params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": DEFAULT_PER_PAGE}
        item_type = "issue"
    elif endpoint == "releases":
        url = f"{base}/repos/{owner}/{repo}/releases"
        params = {"per_page": DEFAULT_PER_PAGE}
        item_type = "release"
    else:
        raise ValueError(f"unsupported endpoint: {endpoint}")

    try:
        raw_items, headers = request(
            append_query(url, params),
            token=token,
            github=source["host"] == "github",
            timeout=timeout,
        )
    except RateLimitedError as exc:
        if source["host"] == "github" and endpoint in {"pulls", "issues"}:
            fallback_items, fallback_status = fetch_github_html_search(
                source, endpoint, cutoff=cutoff, timeout=timeout
            )
            fallback_status["errors"] = [
                f"GitHub API rate limited; HTML search fallback used: {exc}"
            ]
            return fallback_items, fallback_status
        raise
    if not isinstance(raw_items, list):
        raise FetchError("expected a JSON array response")

    items: list[dict[str, Any]] = []
    filtered_out = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        # GitHub's /issues endpoint also returns pull requests; keep issue data unique.
        if endpoint == "issues" and raw.get("pull_request"):
            continue
        item = normalize_common_item(raw, item_type=item_type, source=source, cutoff=cutoff)
        if item is None:
            continue
        if source.get("keyword_filter") and not item["matched_keywords"]:
            filtered_out += 1
            continue
        items.append(item)

    rate_remaining = headers.get("x-ratelimit-remaining")
    return items, {
        "endpoint": endpoint,
        "status": "ok",
        "count": len(items),
        "filtered_out": filtered_out,
        "rate_limit_remaining": rate_remaining,
    }


def fetch_github_issue_html(
    source: dict[str, Any],
    number: int,
    *,
    timeout: float,
) -> dict[str, Any] | None:
    """Fetch a GitHub issue page when the REST API is rate-limited.

    The public HTML page embeds the issue title, state, createdAt, and updatedAt.
    This fallback keeps evidence traceable without inventing API metadata.
    """
    url = f"https://github.com/{source['owner']}/{source['repo']}/issues/{number}"
    try:
        proc = subprocess.run(
            ["curl", "-L", "--max-time", str(int(max(1, timeout))), "-A", "Mozilla/5.0", "-sS", url],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError(f"GitHub issue HTML fallback failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:300]
        raise FetchError(f"GitHub issue HTML fallback failed with curl exit {proc.returncode}: {detail}")

    body = proc.stdout
    title_match = re.search(r"<title>(.*?)</title>", body, re.DOTALL | re.IGNORECASE)
    state_match = re.search(r'"state"\s*:\s*"([^"]+)"', body)
    created_match = re.search(r'"createdAt"\s*:\s*"([^"]+)"', body)
    updated_match = re.search(r'"updatedAt"\s*:\s*"([^"]+)"', body)
    if not title_match:
        raise FetchError("GitHub issue HTML fallback could not find title")

    title = title_match.group(1)
    title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", title))).strip()
    # GitHub titles include repository suffix; keep it because it is still exact evidence.
    state = state_match.group(1).lower() if state_match else "unknown"
    created = parse_datetime(created_match.group(1)) if created_match else None
    updated = parse_datetime(updated_match.group(1)) if updated_match else None
    timestamp = updated or created or now_utc()
    return {
        "source_key": source["key"],
        "source_name": source["name"],
        "category": source["category"],
        "type": "roadmap_issue",
        "event": "new" if created and created >= (now_utc() - timedelta(days=1)) else "updated",
        "id": number,
        "number": number,
        "title": title,
        "url": url,
        "state": state,
        "created_at": isoformat(created),
        "updated_at": isoformat(updated),
        "published_at": None,
        "timestamp": isoformat(timestamp),
        "author": None,
        "labels": [],
        "comments": None,
        "reactions_total": None,
        "matched_keywords": matched_keywords({"title": title}),
        "draft": None,
        "prerelease": None,
        "merged_at": None,
        "closed_at": None,
        "evidence_method": "github_issue_html",
    }


def fetch_issue_details(source: dict[str, Any], *, cutoff: datetime, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token = token_for(source["host"])
    base = api_base(source["host"])
    items: list[dict[str, Any]] = []
    errors: list[str] = []

    for number in source["issue_numbers"]:
        url = f"{base}/repos/{source['owner']}/{source['repo']}/issues/{number}"
        try:
            raw, _ = request(url, token=token, github=source["host"] == "github", timeout=timeout)
            if not isinstance(raw, dict):
                raise FetchError("expected a JSON object response")
            item = normalize_common_item(raw, item_type="roadmap_issue", source=source, cutoff=cutoff)
            if item:
                items.append(item)
        except RateLimitedError as exc:
            try:
                raw = fetch_github_issue_html(source, number, timeout=timeout)
                item = normalize_common_item(raw, item_type="roadmap_issue", source=source, cutoff=cutoff) if raw else None
                if item:
                    item["evidence_method"] = "github_issue_html"
                    items.append(item)
                else:
                    errors.append(f"issue #{number}: HTML fallback found no usable item")
            except FetchError as fallback_exc:
                errors.append(f"issue #{number}: {exc}; HTML fallback failed: {fallback_exc}")
        except FetchError as exc:
            errors.append(f"issue #{number}: {exc}")

    used_html_fallback = any("HTML fallback" in error for error in errors)
    if not errors:
        status = "ok"
    elif items or used_html_fallback:
        status = "degraded"
    else:
        status = "failed"
    return items, {
        "endpoint": "issue_details",
        "status": status,
        "count": len(items),
        "errors": errors,
    }


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_duration(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    parts = value.split(":")
    if not all(part.strip().isdigit() for part in parts):
        return None
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


def discover_feed(site_url: str, timeout: float) -> str:
    html, _ = request(site_url, timeout=timeout, json_response=False)
    pattern = re.compile(
        r"<link\b[^>]+(?:type=[\"'](?:application/rss\+xml|application/atom\+xml)[\"'][^>]*|"
        r"rel=[\"']alternate[\"'][^>]*)>",
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        tag = match.group(0)
        href_match = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        type_match = re.search(r"type=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        if href_match and type_match and "rss" in type_match.group(1).lower():
            return urllib.parse.urljoin(site_url, href_match.group(1))
    raise FetchError("RSS/Atom feed link not found on podcast site")


def first_text(element: ET.Element, names: list[str], *, namespaces: dict[str, str] | None = None) -> str | None:
    for name in names:
        if ":" in name:
            prefix, local = name.split(":", 1)
            uri = (namespaces or {}).get(prefix)
            if not uri:
                continue
            value = element.findtext(f"{{{uri}}}{local}")
        else:
            value = element.findtext(name)
        if value:
            return value
    return None


def child_link(element: ET.Element) -> str | None:
    for child in element:
        if child.tag.endswith("}link") or child.tag == "link":
            href = child.attrib.get("href")
            if href:
                return href
            if child.text and child.text.strip():
                return child.text.strip()
    return None


def fetch_podcast(source: dict[str, Any], *, podcast_cutoff: datetime, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    feed_url = source.get("feed")
    discovery_used = False
    try:
        if not feed_url:
            feed_url = discover_feed(source["site"], timeout)
            discovery_used = True
        raw, _ = request(feed_url, timeout=timeout, json_response=False)
        if not isinstance(raw, str):
            raise FetchError("expected RSS/Atom text response")
        root = ET.fromstring(raw)
    except FetchError as exc:
        return [], {
            "endpoint": "podcast_feed",
            "status": "failed",
            "errors": [str(exc)],
            "feed_url": feed_url,
        }
    except ET.ParseError as exc:
        return [], {
            "endpoint": "podcast_feed",
            "status": "failed",
            "errors": [f"invalid RSS/Atom XML: {exc}"],
            "feed_url": feed_url,
        }

    namespaces = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    entries = root.findall(".//item") or root.findall(".//entry")
    episodes: list[dict[str, Any]] = []

    for entry in entries[:20]:
        title = first_text(entry, ["title"], namespaces=namespaces)
        link = child_link(entry) or first_text(entry, ["link"], namespaces=namespaces)
        published_raw = first_text(entry, ["pubDate", "published", "updated", "date"], namespaces=namespaces)
        published = parse_datetime(published_raw)
        summary = strip_html(
            first_text(
                entry,
                ["summary", "description", "content:encoded", "content"],
                namespaces={**namespaces, "content": "http://purl.org/rss/1.0/modules/content/"},
            )
            or ""
        )
        duration_raw = first_text(entry, ["itunes:duration"], namespaces=namespaces)
        if not title or not link:
            continue
        episodes.append(
            {
                "source_key": source["key"],
                "source_name": source["name"],
                "category": "podcasts",
                "type": "podcast_episode",
                "title": title.strip(),
                "url": link.strip(),
                "published_at": isoformat(published),
                "duration_seconds": parse_duration(duration_raw),
                "summary": summary[:1000],
                "difficulty": source.get("difficulty"),
                "track": source.get("track"),
                "in_window": bool(published and published >= podcast_cutoff),
                "matched_keywords": matched_keywords({"title": title, "summary": summary}),
            }
        )

    episodes.sort(key=lambda episode: episode.get("published_at") or "", reverse=True)
    in_window = sum(1 for episode in episodes if episode["in_window"])
    return episodes[:10], {
        "endpoint": "podcast_feed",
        "status": "ok",
        "count": len(episodes[:10]),
        "in_window": in_window,
        "feed_url": feed_url,
        "feed_discovered_from_site": discovery_used,
    }


def select_sources(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.repo:
        selected = [SOURCE_BY_KEY[key] for key in args.repo]
    elif args.category:
        categories = set(args.category)
        selected = [source for source in SOURCES if source["category"] in categories]
    elif args.focus == "llm-inference":
        selected = [SOURCE_BY_KEY[key] for key in LLM_INFERENCE_SOURCES]
    else:
        selected = SOURCES
    if args.focus == "llm-inference":
        selected = [source for source in selected if source["key"] in LLM_INFERENCE_SOURCES]
    return selected


def merge_status(endpoints: list[dict[str, Any]]) -> tuple[str, list[str]]:
    statuses = {endpoint.get("status") for endpoint in endpoints}
    all_errors: list[str] = []
    for endpoint in endpoints:
        all_errors.extend(endpoint.get("errors") or [])
    if "auth_required" in statuses:
        return "auth_required", all_errors
    # If at least one endpoint produced fallback data, report the source as
    # degraded rather than rate-limited; the endpoint table still discloses the
    # exact rate-limited endpoint.
    if "rate_limited" in statuses and ("ok" in statuses or "degraded" in statuses):
        return "degraded", all_errors
    if "rate_limited" in statuses:
        return "rate_limited", all_errors
    if statuses and statuses.issubset({"ok"}):
        return "ok", all_errors
    if "ok" in statuses or "degraded" in statuses:
        return "degraded", all_errors
    return "failed", all_errors


def fetch_source_result(source: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch one source; returns (result, endpoints-items, episodes, endpoints-status)."""
    base_result: dict[str, Any] = {
        "key": source["key"],
        "name": source["name"],
        "category": source["category"],
        "kind": source["kind"],
        "host": source.get("host"),
        "repository": f"{source.get('owner')}/{source.get('repo')}" if source.get("owner") else None,
    }
    endpoints: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []

    try:
        if source["kind"] == "repository":
            skipped_endpoints = set(source.get("skip_endpoints") or [])
            for endpoint in ("pulls", "issues", "releases"):
                if endpoint in skipped_endpoints:
                    continue
                try:
                    endpoint_items, endpoint_status = fetch_endpoint(
                        source, endpoint, cutoff=now_utc() - timedelta(hours=args.hours), timeout=args.timeout
                    )
                    endpoints.append(endpoint_status)
                    items.extend(endpoint_items)
                except RateLimitedError as exc:
                    endpoints.append(
                        {
                            "endpoint": endpoint,
                            "status": "rate_limited",
                            "errors": [str(exc)],
                            "retry_after": exc.retry_after,
                        }
                    )
                except FetchError as exc:
                    endpoints.append({"endpoint": endpoint, "status": "failed", "errors": [str(exc)]})
        elif source["kind"] == "issue_details":
            endpoint_items, endpoint_status = fetch_issue_details(
                source, cutoff=now_utc() - timedelta(hours=args.hours), timeout=args.timeout
            )
            endpoints.append(endpoint_status)
            items.extend(endpoint_items)
        elif source["kind"] == "podcast":
            podcast_episodes, endpoint_status = fetch_podcast(
                source, podcast_cutoff=now_utc() - timedelta(days=args.podcast_days), timeout=args.timeout
            )
            endpoints.append(endpoint_status)
            episodes.extend(podcast_episodes)
    except Exception as exc:  # Defensive: a source failure must not suppress other sources.
        endpoints.append({"endpoint": "source", "status": "failed", "errors": [f"unexpected error: {exc}"]})

    return base_result, items, episodes, endpoints


def main() -> int:
    args = parse_args()
    generated_at = now_utc()
    repository_cutoff = generated_at - timedelta(hours=args.hours)
    podcast_cutoff = generated_at - timedelta(days=args.podcast_days)
    github_token = token_for("github")
    gitcode_token = token_for("gitcode")

    items: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    global_errors: list[dict[str, Any]] = []

    sources = select_sources(args)
    workers = min(args.workers, len(sources)) or 1
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(lambda source: fetch_source_result(source, args), sources))
    else:
        fetched = [fetch_source_result(source, args) for source in sources]

    for base_result, source_items, source_episodes, endpoints in fetched:
        overall_status, errors = merge_status(endpoints)
        base_result.update(
            {
                "status": overall_status,
                "endpoints": endpoints,
                "errors": errors,
                "item_count": sum(int(endpoint.get("count") or 0) for endpoint in endpoints),
            }
        )
        source_results.append(base_result)
        items.extend(source_items)
        episodes.extend(source_episodes)
        for error in errors:
            global_errors.append({"source_key": base_result["key"], "message": error})

    items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    episodes.sort(key=lambda episode: episode.get("published_at") or "", reverse=True)

    output: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": isoformat(generated_at),
        "repository_window_hours": args.hours,
        "repository_cutoff_utc": isoformat(repository_cutoff),
        "podcast_window_days": args.podcast_days,
        "podcast_cutoff_utc": isoformat(podcast_cutoff),
        "selected_focus": args.focus or "all",
        "selected_categories": args.category or ["all"],
        "selected_sources": args.repo or ["all"],
        "github_token_present": bool(github_token),
        "gitcode_token_present": bool(gitcode_token),
        "source_policy": {
            "cann_primary_host": "gitcode",
            "gitee_used": False,
            "note": "GitCode is the primary and preferred host for CANN repositories. XLLM is tracked on GitHub only.",
        },
        "sources": source_results,
        "items": items,
        "podcast_episodes": episodes,
        "errors": global_errors,
    }

    rendered = json.dumps(
        output,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=False,
    ) + ("\n" if not args.compact else "")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
