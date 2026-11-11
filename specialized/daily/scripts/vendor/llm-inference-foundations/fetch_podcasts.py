#!/usr/bin/env python3
"""Fetch validated AI podcast feeds for the daily foundations brief."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any

USER_AGENT = "codex-ai-foundations/1.0"
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")
SOURCES = [
    {
        "key": "practical-ai",
        "name": "Practical AI",
        "feed": "https://changelog.com/practicalai/feed",
        "difficulty": "入门",
        "phase": [1, 2],
        "track": "accessible AI concepts and applied context",
    },
    {
        "key": "mlst",
        "name": "Machine Learning Street Talk",
        "feed": "https://www.mlst.ai/feed",
        "difficulty": "高阶",
        "phase": [4],
        "track": "technical AI debates and research context",
    },
]


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not context.get_ca_certs() and SYSTEM_CA_BUNDLE.exists():
        context.load_verify_locations(cafile=SYSTEM_CA_BUNDLE)
    return context


SSL_CONTEXT = ssl_context()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")
    return args


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", unescape(value))
    return re.sub(r"\s+", " ", text).strip()


def child_link(element: ET.Element) -> str | None:
    for child in element:
        if child.tag.endswith("link") and (child.get("href") or (child.text or "").strip()):
            return child.get("href") or child.text.strip()
    return None


def first_text(element: ET.Element, names: list[str]) -> str | None:
    for name in names:
        for match in element.iter():
            if match.tag == name or match.tag.endswith("}" + name):
                if match.text and match.text.strip():
                    return match.text.strip()
    return None


def fetch(source: dict[str, Any], cutoff: datetime, timeout: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    request = urllib.request.Request(
        source["feed"], headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
            raw = response.read()
    except Exception as urllib_error:
        # Some Substack/CDN endpoints reset urllib TLS sessions while curl succeeds.
        curl = subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", str(timeout), source["feed"]],
            capture_output=True,
            text=False,
            check=False,
        )
        if curl.returncode != 0:
            message = curl.stderr.decode("utf-8", errors="replace").strip() or str(urllib_error)
            return [], {"status": "failed", "errors": [message]}
        raw = curl.stdout
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        return [], {"status": "failed", "errors": [f"invalid XML: {exc}"]}

    entries = root.findall(".//item") or root.findall(".//entry")
    episodes: list[dict[str, Any]] = []
    for entry in entries[:20]:
        title = strip_html(first_text(entry, ["title"]))
        link = child_link(entry) or first_text(entry, ["link"])
        published = parse_datetime(first_text(entry, ["pubDate", "published", "updated", "date"]))
        summary = strip_html(first_text(entry, ["summary", "description", "content", "encoded"]))
        duration = first_text(entry, ["duration"])
        if not title or not link or not published:
            continue
        episodes.append(
            {
                "source_key": source["key"],
                "source_name": source["name"],
                "title": title,
                "url": link,
                "published_at": published.isoformat(),
                "in_window": published >= cutoff,
                "duration_raw": duration,
                "summary": summary[:1000],
                "difficulty": source["difficulty"],
                "phase": source["phase"],
                "track": source["track"],
            }
        )
    return episodes, {"status": "ok", "count": len(episodes), "in_window": sum(e["in_window"] for e in episodes)}


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    episodes: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    # Feeds are independent. Sequential fetching multiplied the timeout by the
    # number of feeds; fan out so one dead feed costs one timeout, not five.
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        fetched = list(pool.map(lambda source: fetch(source, cutoff, args.timeout), SOURCES))

    for source, (found, status) in zip(SOURCES, fetched):
        episodes.extend(found)
        sources.append({**source, "status": status.get("status"), "count": status.get("count"), "in_window": status.get("in_window"), "errors": status.get("errors", [])})
        if status.get("status") != "ok":
            errors.append({"source_key": source["key"], "message": "; ".join(status.get("errors", []))})
    episodes.sort(key=lambda episode: episode["published_at"], reverse=True)
    output = {
        "schema_version": 1,
        "generated_at_utc": now.isoformat(),
        "window_days": args.days,
        "cutoff_utc": cutoff.isoformat(),
        "sources": sources,
        "episodes": episodes,
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
