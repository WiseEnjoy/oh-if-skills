#!/usr/bin/env python3
"""Single-command wrapper for the two nightly inference reports."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
RADAR_SCRIPTS = SCRIPTS_ROOT / "vendor" / "inference-radar"
FOUNDATIONS_SCRIPTS = SCRIPTS_ROOT / "vendor" / "llm-inference-foundations"
BEIJING = ZoneInfo("Asia/Shanghai")
TIMING_SCHEMA_VERSION = 1
SLOW_THRESHOLD_SECONDS = 600.0
GENERATION_DURATION_PLACEHOLDER = "__DAILY_GENERATION_DURATION__"


def update_verification_ledger(args: argparse.Namespace, paths: dict[str, Path]) -> None:
    """Carry curated actions across days: append today's, age out stale ones."""
    radar_json = args.radar_json or paths["radar_curated"]
    if not radar_json.exists():
        return
    sys.path.insert(0, str(RADAR_SCRIPTS))
    try:
        import verification_ledger as ledger_mod
    finally:
        sys.path.pop(0)
    data = json.loads(radar_json.read_text(encoding="utf-8"))
    ledger_path = args.work_dir / "verification-ledger.json"
    ledger = ledger_mod.load(ledger_path)
    ledger, carried = ledger_mod.update(ledger, data.get("actions", []), args.date)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data["carried_actions"] = carried
    data["ledger_stats"] = ledger_mod.stats(ledger, args.date)
    radar_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def today_beijing() -> str:
    return datetime.now(BEIJING).date().isoformat()


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", default=today_beijing(), help="Beijing report date, YYYY-MM-DD")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("work"),
        help="Directory for acquisition and curated JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for final HTML reports",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Fetch and audit all report inputs")
    add_common_arguments(prepare)
    prepare.add_argument("--repository-hours", type=int, default=24)
    prepare.add_argument("--web-hours", type=int, default=72)
    prepare.add_argument("--podcast-days", type=int, default=30)
    prepare.add_argument("--timeout", type=float, default=10.0)
    prepare.add_argument("--max-per-source", type=int, default=40)
    prepare.add_argument("--max-per-tier", type=int, default=60)
    prepare.add_argument("--reuse", action="store_true", help="Reuse existing radar acquisition files")
    prepare.add_argument(
        "--fast",
        action="store_true",
        help="10-minute budget preset: 6s timeouts, smaller pools, 14-day podcast window",
    )
    prepare.add_argument(
        "--history-dir",
        type=Path,
        help="Directory with prior curated reports for seen-before marking (defaults to --work-dir)",
    )
    prepare.add_argument(
        "--print-inputs",
        action="store_true",
        help="Print radar candidates and podcast episodes as one JSON object",
    )

    render = subparsers.add_parser("render", help="Render both final HTML reports")
    add_common_arguments(render)
    render.add_argument("--radar-json", type=Path)
    render.add_argument("--deep-json", type=Path)

    inspect = subparsers.add_parser("inspect", help="Print concise report input summaries")
    add_common_arguments(inspect)
    inspect.add_argument("--radar-limit", type=int, default=80)
    inspect.add_argument("--podcast-limit", type=int, default=100)
    inspect.add_argument("--full", action="store_true", help="Print complete JSON inputs")

    paths = subparsers.add_parser("paths", help="Print conventional paths for a report date")
    add_common_arguments(paths)

    return parser.parse_args()


def validate_common(args: argparse.Namespace) -> None:
    try:
        datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit("--date must use YYYY-MM-DD") from exc
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)


def conventional_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "radar_candidates": args.work_dir / f"inference-radar-codex-candidates-{args.date}.json",
        "radar_curated": args.work_dir / f"inference-radar-curated-{args.date}.json",
        "podcasts": args.work_dir / f"llm-inference-foundations-podcasts-{args.date}.json",
        "deep_curated": args.work_dir / f"llm-inference-foundations-deep-{args.date}.json",
        "radar_html": args.output_dir / f"inference-radar-{args.date}.html",
        "deep_html": args.output_dir / f"llm-inference-foundations-{args.date}.html",
        "metrics": args.work_dir / f"daily-run-metrics-{args.date}.json",
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_timing_metrics(date: str) -> dict[str, Any]:
    return {
        "schema_version": TIMING_SCHEMA_VERSION,
        "date": date,
        "slow_threshold_seconds": SLOW_THRESHOLD_SECONDS,
        "events": [],
    }


def load_timing_metrics(path: Path, date: str) -> dict[str, Any]:
    if not path.exists():
        return new_timing_metrics(date)
    metrics = new_timing_metrics(date)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("date") != date:
            raise ValueError("metrics date mismatch")
        events = loaded.get("events", [])
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        metrics["events"] = [
            event
            for event in events
            if isinstance(event, dict) and event.get("phase") in {"prepare", "render"}
        ]
        if isinstance(loaded.get("slow_threshold_seconds"), (int, float)):
            metrics["slow_threshold_seconds"] = loaded["slow_threshold_seconds"]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        metrics["metrics_load_error"] = f"{type(exc).__name__}: {exc}"
    return derive_timing_summary(metrics)


def write_timing_metrics(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def latest_event(metrics: dict[str, Any], phase: str) -> dict[str, Any] | None:
    events = [
        event
        for event in metrics.get("events", [])
        if event.get("phase") == phase
    ]
    return events[-1] if events else None


def latest_success(metrics: dict[str, Any], phase: str) -> dict[str, Any] | None:
    events = [
        event
        for event in metrics.get("events", [])
        if event.get("phase") == phase and event.get("status") == "success"
    ]
    return events[-1] if events else None


def derive_timing_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    prepare = latest_success(metrics, "prepare")
    render = latest_success(metrics, "render")
    prepare_duration = prepare.get("duration_seconds") if prepare else None
    render_duration = render.get("duration_seconds") if render else None
    summary: dict[str, Any] = {
        "prepare_duration_seconds": prepare_duration,
        "render_duration_seconds": render_duration,
        "total_generation_seconds": None,
        "curation_gap_seconds": None,
        "performance_status": "unavailable",
        "timing_unavailable_reason": None,
    }

    if prepare is None:
        summary["timing_unavailable_reason"] = "prepare timing unavailable"
    elif render is None:
        summary["timing_unavailable_reason"] = "render timing unavailable"
    else:
        try:
            started = datetime.fromisoformat(prepare["started_at_utc"].replace("Z", "+00:00"))
            ended = datetime.fromisoformat(render["ended_at_utc"].replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            summary["timing_unavailable_reason"] = f"invalid timing event: {exc}"
        else:
            total = round((ended - started).total_seconds(), 3)
            if total < 0:
                summary["timing_unavailable_reason"] = "render ended before prepare started"
            else:
                summary["total_generation_seconds"] = total
                phase_total = (prepare_duration or 0) + (render_duration or 0)
                if total + 0.01 < phase_total:
                    summary["timing_unavailable_reason"] = "timing intervals are inconsistent"
                else:
                    summary["curation_gap_seconds"] = round(total - phase_total, 3)
                summary["performance_status"] = (
                    "slow" if total >= metrics.get("slow_threshold_seconds", SLOW_THRESHOLD_SECONDS) else "ok"
                )

    metrics["last_prepare"] = latest_event(metrics, "prepare")
    metrics["last_render"] = latest_event(metrics, "render")
    metrics.update(summary)
    return metrics


def record_timing_event(
    args: argparse.Namespace,
    phase: str,
    started_at: datetime,
    ended_at: datetime,
    duration_seconds: float,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    paths = conventional_paths(args)
    metrics = load_timing_metrics(paths["metrics"], args.date)
    event = {
        "phase": phase,
        "status": status,
        "started_at_utc": iso_utc(started_at),
        "ended_at_utc": iso_utc(ended_at),
        "duration_seconds": round(duration_seconds, 3),
        "error": error,
    }
    metrics["events"].append(event)
    metrics = derive_timing_summary(metrics)
    metrics["updated_at_utc"] = iso_utc(utc_now())
    write_timing_metrics(paths["metrics"], metrics)
    return metrics


def run_timed_phase(
    args: argparse.Namespace,
    phase: str,
    operation: Callable[[argparse.Namespace], int],
    finalize: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    started_perf = time.perf_counter()
    started_at = utc_now()
    try:
        result = operation(args)
        metrics = record_timing_event(
            args,
            phase,
            started_at,
            utc_now(),
            time.perf_counter() - started_perf,
            "success",
        )
        if finalize is not None:
            finalize(metrics)
        return result
    except BaseException as exc:
        message = str(exc) or type(exc).__name__
        record_timing_event(
            args,
            phase,
            started_at,
            utc_now(),
            time.perf_counter() - started_perf,
            "failed",
            f"{type(exc).__name__}: {message}",
        )
        raise


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未记录"
    if seconds < 0:
        return "无效"
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    minutes, seconds_part = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} 分 {seconds_part:.1f} 秒"
    hours, minutes_part = divmod(minutes, 60)
    return f"{int(hours)} 时 {int(minutes_part)} 分 {seconds_part:.1f} 秒"


def timing_display_text(metrics: dict[str, Any]) -> str:
    total = metrics.get("total_generation_seconds")
    reason = metrics.get("timing_unavailable_reason")
    total_text = format_duration(total) if total is not None else f"未记录（{reason}）"
    status = metrics.get("performance_status", "unavailable")
    status_text = {"ok": "正常", "slow": "偏慢"}.get(status, "未评估")
    return (
        f"渲染 {format_duration(metrics.get('render_duration_seconds'))} · "
        f"端到端 {total_text} · 性能：{status_text}"
    )


def public_timing(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "prepare_duration_seconds": metrics.get("prepare_duration_seconds"),
        "render_duration_seconds": metrics.get("render_duration_seconds"),
        "total_generation_seconds": metrics.get("total_generation_seconds"),
        "curation_gap_seconds": metrics.get("curation_gap_seconds"),
        "performance_status": metrics.get("performance_status"),
        "timing_unavailable_reason": metrics.get("timing_unavailable_reason"),
        "display_text": timing_display_text(metrics),
    }


def replace_generation_duration(path: Path, display_text: str, required: bool = True) -> None:
    content = path.read_text(encoding="utf-8")
    if GENERATION_DURATION_PLACEHOLDER not in content:
        if required:
            raise RuntimeError(f"generation duration placeholder missing from {path}")
        return
    path.write_text(
        content.replace(GENERATION_DURATION_PLACEHOLDER, html.escape(display_text, quote=True)),
        encoding="utf-8",
    )


def run_process(command: list[str], timeout: float | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {timeout}s: {' '.join(command)}"
        ) from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{message}")
    return {
        "command": command,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(args: argparse.Namespace) -> int:
    paths = conventional_paths(args)
    if args.fast:
        args.timeout = min(args.timeout, 6.0)
        args.max_per_source = min(args.max_per_source, 20)
        args.max_per_tier = min(args.max_per_tier, 30)
        args.podcast_days = min(args.podcast_days, 14)
    if args.repository_hours <= 0 or args.web_hours <= 0 or args.podcast_days <= 0:
        raise SystemExit("time windows must be positive")
    if args.timeout <= 0 or args.max_per_source <= 0 or args.max_per_tier <= 0:
        raise SystemExit("limits and timeout must be positive")

    radar_command = [
        sys.executable,
        str(RADAR_SCRIPTS / "acquire.py"),
        "--date", args.date,
        "--repository-hours", str(args.repository_hours),
        "--web-hours", str(args.web_hours),
        "--timeout", str(args.timeout),
        "--max-per-source", str(args.max_per_source),
        "--max-per-tier", str(args.max_per_tier),
        "--output-dir", str(args.work_dir),
    ]
    if args.reuse:
        radar_command.append("--reuse")
    radar_command.extend(["--history-dir", str(args.history_dir or args.work_dir)])
    podcast_command = [
        sys.executable,
        str(FOUNDATIONS_SCRIPTS / "fetch_podcasts.py"),
        "--days", str(args.podcast_days),
        "--timeout", str(args.timeout),
        "--compact",
        "--output", str(paths["podcasts"]),
    ]
    reuse_podcasts = args.reuse and paths["podcasts"].exists()
    if reuse_podcasts:
        radar = run_process(radar_command, timeout=150)
        podcasts = None
    else:
        # Radar and podcasts hit unrelated hosts; overlapping them removes the
        # podcast phase from the critical path.
        with ThreadPoolExecutor(max_workers=2) as pool:
            radar_future = pool.submit(run_process, radar_command, 150)
            podcast_future = pool.submit(run_process, podcast_command, 90)
            radar = radar_future.result()
            podcasts = podcast_future.result()

    if args.print_inputs:
        payload = {
            "date": args.date,
            "paths": {key: str(value) for key, value in paths.items()},
            "radar_candidates": load_json(paths["radar_candidates"]),
            "podcasts": load_json(paths["podcasts"]),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps({
        "date": args.date,
        "radar": json.loads(radar["stdout"] or "{}"),
        "podcasts_path": str(paths["podcasts"]),
        "radar_candidates_path": str(paths["radar_candidates"]),
        "podcasts_stdout": (
            {"reused": True}
            if reuse_podcasts
            else json.loads(podcasts["stdout"] or "{}") if podcasts["stdout"] else None
        ),
    }, ensure_ascii=False, indent=2))
    return 0


def render_reports(args: argparse.Namespace) -> int:
    paths = conventional_paths(args)
    radar_json = args.radar_json or paths["radar_curated"]
    deep_json = args.deep_json or paths["deep_curated"]
    if not radar_json.exists():
        raise SystemExit(f"radar JSON does not exist: {radar_json}")
    if not deep_json.exists():
        raise SystemExit(f"foundations JSON does not exist: {deep_json}")

    update_verification_ledger(args, paths)

    try:
        run_process([
            sys.executable,
            str(RADAR_SCRIPTS / "render_curated_report.py"),
            str(radar_json),
            "--output", str(paths["radar_html"]),
            "--generation-duration-text", GENERATION_DURATION_PLACEHOLDER,
        ], timeout=60)
        run_process([
            sys.executable,
            str(FOUNDATIONS_SCRIPTS / "render_deep_report.py"),
            str(deep_json),
            "--output", str(paths["deep_html"]),
            "--generation-duration-text", GENERATION_DURATION_PLACEHOLDER,
        ], timeout=60)
    except BaseException:
        failure_text = "渲染失败 · 端到端未记录 · 性能：未评估"
        for html_path in (paths["radar_html"], paths["deep_html"]):
            if html_path.exists():
                replace_generation_duration(html_path, failure_text, required=False)
        raise

    return 0


def finish_render(args: argparse.Namespace, metrics: dict[str, Any]) -> None:
    paths = conventional_paths(args)
    radar_json = args.radar_json or paths["radar_curated"]
    deep_json = args.deep_json or paths["deep_curated"]
    display_text = timing_display_text(metrics)
    replace_generation_duration(paths["radar_html"], display_text)
    replace_generation_duration(paths["deep_html"], display_text)

    print(json.dumps({
        "date": args.date,
        "radar_input": str(radar_json),
        "deep_input": str(deep_json),
        "radar_html": str(paths["radar_html"]),
        "deep_html": str(paths["deep_html"]),
        "timing": public_timing(metrics),
        "metrics_path": str(paths["metrics"]),
    }, ensure_ascii=False, indent=2))


def render(args: argparse.Namespace) -> int:
    return run_timed_phase(
        args,
        "render",
        render_reports,
        lambda metrics: finish_render(args, metrics),
    )



def truncate(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    return value if len(value) <= limit else value[: limit - 3] + "..."


def inspect_inputs(args: argparse.Namespace) -> int:
    paths = conventional_paths(args)
    if not paths["radar_candidates"].exists():
        raise SystemExit(f"radar candidates do not exist: {paths['radar_candidates']}")
    if not paths["podcasts"].exists():
        raise SystemExit(f"podcast input does not exist: {paths['podcasts']}")
    if args.radar_limit <= 0 or args.podcast_limit <= 0:
        raise SystemExit("inspect limits must be positive")

    radar = load_json(paths["radar_candidates"])
    podcasts = load_json(paths["podcasts"])
    if args.full:
        print(json.dumps({
            "radar_candidates": radar,
            "podcasts": podcasts,
        }, ensure_ascii=False, indent=2))
        return 0

    radar_items = []
    health = radar.get("data_health", {})
    health_sources = health.get("sources", [])
    for item in radar.get("candidates", [])[: args.radar_limit]:
        radar_items.append({
            "tier": item.get("tier"),
            "source": item.get("source_name"),
            "title": item.get("title"),
            "url": item.get("url"),
            "type": item.get("type"),
            "event": item.get("event"),
            "state": item.get("state"),
            "timestamp": item.get("timestamp"),
            "machine_theme": item.get("machine_theme"),
            "seen_before": item.get("seen_before", False),
            "labels": item.get("labels", []),
            "summary": truncate(item.get("summary") or item.get("body_excerpt"), 260),
        })

    podcast_items = []
    for item in podcasts.get("episodes", [])[: args.podcast_limit]:
        podcast_items.append({
            "source": item.get("source_name"),
            "title": item.get("title"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "duration_raw": item.get("duration_raw"),
            "difficulty": item.get("difficulty"),
            "phase": item.get("phase"),
            "summary": truncate(item.get("summary"), 220),
        })

    print(json.dumps({
        "date": args.date,
        "radar": {
            "candidate_pool_count": radar.get("candidate_pool_count"),
            "presented_candidate_count": radar.get("presented_candidate_count"),
            "candidate_tier_counts": radar.get("candidate_tier_counts"),
            "data_health": {
                "source_count": len(health_sources),
                "ok_source_count": sum(1 for source in health_sources if source.get("status") == "ok"),
                "degraded_sources": [
                    {
                        "key": source.get("key"),
                        "name": source.get("name"),
                        "status": source.get("status"),
                        "errors": source.get("errors", []),
                    }
                    for source in health_sources
                    if source.get("status") != "ok"
                ],
                "errors": health.get("errors", []),
                "github_token_present": health.get("github_token_present"),
                "gitcode_token_present": health.get("gitcode_token_present"),
            },
            "items": radar_items,
        },
        "podcasts": {
            "window_days": podcasts.get("window_days"),
            "source_count": len(podcasts.get("sources", [])),
            "episode_count": len(podcasts.get("episodes", [])),
            "errors": podcasts.get("errors", []),
            "items": podcast_items,
        },
        "history_check": radar.get("history_check"),
    }, ensure_ascii=False, indent=2))
    return 0


def print_paths(args: argparse.Namespace) -> int:
    paths = conventional_paths(args)
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    validate_common(args)
    if args.command == "prepare":
        return run_timed_phase(args, "prepare", prepare)
    if args.command == "render":
        return render(args)
    if args.command == "inspect":
        return inspect_inputs(args)
    return print_paths(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
