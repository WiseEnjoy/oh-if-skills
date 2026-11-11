#!/usr/bin/env python3
"""Acquire and audit all Inference Radar inputs, then build the Codex candidate pool."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--repository-hours", type=int, default=24)
    parser.add_argument("--web-hours", type=int, default=72)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-per-source", type=int, default=40)
    parser.add_argument("--max-per-tier", type=int, default=60)
    parser.add_argument("--history-dir", type=Path, help="Directory with prior curated reports for seen-before marking.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--reuse", action="store_true", help="Reuse existing acquisition JSON files.")
    args = parser.parse_args()
    if args.repository_hours <= 0 or args.web_hours <= 0:
        parser.error("hours must be positive")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    if args.max_per_source <= 0 or args.max_per_tier <= 0:
        parser.error("max counts must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args


def run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def acquire_if_needed(
    path: Path,
    command: list[str],
    reuse: bool,
) -> dict[str, Any]:
    if reuse and path.exists():
        return {"path": str(path), "reused": True, "fetch": None}
    result = run(command)
    if result["returncode"] != 0:
        raise RuntimeError(
            "acquisition failed: " + (result["stderr"] or result["stdout"] or "unknown error")
        )
    return {"path": str(path), "reused": False, "fetch": result}


def audit(path: Path) -> dict[str, Any]:
    result = run([sys.executable, str(Path(__file__).with_name("quality_audit.py")), str(path)])
    if result["returncode"] != 0:
        raise RuntimeError("audit failed: " + (result["stderr"] or result["stdout"]))
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid audit output for {path}: {exc}") from exc
    return {"path": str(path), **payload}


def main() -> int:
    args = parse_args()
    cann_path = args.output_dir / f"inference-radar-llm-cann-{args.date}.json"
    framework_path = args.output_dir / f"inference-radar-llm-frameworks-{args.date}.json"
    web_path = args.output_dir / f"inference-radar-web-sources-{args.date}.json"
    candidate_path = args.output_dir / f"inference-radar-codex-candidates-{args.date}.json"
    summary_path = args.output_dir / f"inference-radar-acquisition-summary-{args.date}.json"
    script_dir = Path(__file__).resolve().parent

    acquisition_jobs = [
        (
            cann_path,
            [
                sys.executable, str(script_dir / "fetch_updates.py"),
                "--focus", "llm-inference", "--category", "operators",
                "--category", "communications", "--hours", str(args.repository_hours),
                "--timeout", str(args.timeout), "--compact", "--output", str(cann_path),
            ],
        ),
        (
            framework_path,
            [
                sys.executable, str(script_dir / "fetch_updates.py"),
                "--focus", "llm-inference", "--category", "frameworks",
                "--category", "engines", "--hours", str(args.repository_hours),
                "--timeout", str(args.timeout), "--compact", "--output", str(framework_path),
            ],
        ),
        (
            web_path,
            [
                sys.executable, str(script_dir / "fetch_web_sources.py"),
                "--hours", str(args.web_hours), "--timeout", str(args.timeout),
                "--max-per-source", str(args.max_per_source),
                "--compact", "--output", str(web_path),
            ],
        ),
    ]
    # The three acquisition stages are independent; run them concurrently so a
    # slow web source cannot delay repository or operator collection.
    with ThreadPoolExecutor(max_workers=len(acquisition_jobs)) as pool:
        acquisitions = list(pool.map(
            lambda job: acquire_if_needed(job[0], job[1], args.reuse),
            acquisition_jobs,
        ))
    audits = [audit(path) for path in (cann_path, framework_path, web_path)]

    prepare = [
        sys.executable, str(script_dir / "prepare_candidates.py"),
        str(cann_path), str(framework_path), str(web_path),
        "--date", args.date, "--max-per-tier", str(args.max_per_tier),
        "--compact", "--output", str(candidate_path),
    ]
    if args.history_dir:
        prepare.extend(["--history-dir", str(args.history_dir)])
    prepare = run(prepare)
    if prepare["returncode"] != 0:
        raise RuntimeError("candidate preparation failed: " + (prepare["stderr"] or prepare["stdout"]))

    summary = {
        "schema_version": 1,
        "date": args.date,
        "repository_window_hours": args.repository_hours,
        "web_window_hours": args.web_hours,
        "acquisitions": acquisitions,
        "audits": audits,
        "candidate_path": str(candidate_path),
        "prepare": prepare,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "candidate_path": str(candidate_path),
        "summary_path": str(summary_path),
        "data_complete": all(item["data_complete"] for item in audits),
        "degraded_sources": [
            {"path": item["path"], "sources": item["degraded_sources"] + item["rate_limited_sources"] + item["failed_sources"]}
            for item in audits
            if item["degraded_sources"] or item["rate_limited_sources"] or item["failed_sources"]
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
