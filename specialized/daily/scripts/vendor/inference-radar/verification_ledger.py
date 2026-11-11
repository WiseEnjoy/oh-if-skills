#!/usr/bin/env python3
"""Verification ledger: carry curated actions across days until closed.

The radar's 今日行动 are only useful if they survive the day that generated
them. This module loads the ledger, marks actions as still open, appends
today's actions as new entries, and writes the updated ledger back. The
renderer uses the open entries to show carried-over actions with their age.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

LEDGER_SCHEMA_VERSION = 1
ACTION_STATUSES = {"open", "done", "dropped"}


def _today() -> str:
    return date.today().isoformat()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": LEDGER_SCHEMA_VERSION, "actions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": LEDGER_SCHEMA_VERSION, "actions": []}
    if not isinstance(data, dict) or not isinstance(data.get("actions"), list):
        return {"schema_version": LEDGER_SCHEMA_VERSION, "actions": []}
    return data


def _action_fingerprint(action: dict[str, Any]) -> str:
    title = (action.get("title") or "").strip()
    detail = " ".join((action.get("detail") or "").strip().split())[:120]
    return f"{title}|{detail}"


def update(
    ledger: dict[str, Any],
    today_actions: list[dict[str, Any]],
    today: str,
    max_age_days: int = 21,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Merge today's actions into the ledger.

    Returns (updated_ledger, carried_open_actions). Carried actions are open
    ledger entries older than today that are not superseded by an action with
    the same fingerprint in today's list.
    """
    actions: list[dict[str, Any]] = ledger.get("actions", [])
    today_fingerprints = {_action_fingerprint(action) for action in today_actions}

    for action in actions:
        if action.get("status") == "open" and action.get("added_at") != today:
            age_days = _age_days(action.get("added_at"), today)
            if age_days is not None and age_days > max_age_days:
                action["status"] = "dropped"
                action["closed_at"] = today
                action["close_reason"] = f"auto-dropped after {age_days} days open"
            elif _action_fingerprint(action) in today_fingerprints:
                # Codex re-raised the same action today; keep the original date
                # so the age keeps growing and the reminder stays honest.
                action["last_seen_at"] = today

    known = {_action_fingerprint(action) for action in actions if action.get("status") == "open"}
    for action in today_actions:
        if _action_fingerprint(action) in known:
            continue
        actions.append(
            {
                "title": action.get("title") or "",
                "detail": action.get("detail") or "",
                "evidence_urls": action.get("evidence_urls") or [],
                "added_at": today,
                "last_seen_at": today,
                "status": "open",
            }
        )
        known.add(_action_fingerprint(action))

    ledger["actions"] = actions
    ledger["schema_version"] = LEDGER_SCHEMA_VERSION
    ledger["updated_at"] = today

    carried = [
        action for action in actions
        if action.get("status") == "open" and action.get("added_at") != today
    ]
    return ledger, carried


def close(ledger: dict[str, Any], title_substring: str, today: str, status: str = "done") -> bool:
    """Close matching open actions (called manually or by Codex on user request)."""
    closed = False
    for action in ledger.get("actions", []):
        if action.get("status") == "open" and title_substring.lower() in (action.get("title") or "").lower():
            action["status"] = status
            action["closed_at"] = today
            closed = True
    return closed


def stats(ledger: dict[str, Any], today: str) -> dict[str, int]:
    counts = {"open": 0, "done": 0, "dropped": 0}
    oldest_open_days = 0
    for action in ledger.get("actions", []):
        status = action.get("status", "open")
        counts[status] = counts.get(status, 0) + 1
        if status == "open":
            age = _age_days(action.get("added_at"), today)
            if age is not None:
                oldest_open_days = max(oldest_open_days, age)
    counts["oldest_open_days"] = oldest_open_days
    return counts


def _age_days(added_at: str | None, today: str) -> int | None:
    if not added_at:
        return None
    try:
        return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(added_at, "%Y-%m-%d")).days
    except ValueError:
        return None
