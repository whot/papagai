#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Invocation tracking for papagai using SQLite."""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("papagai")


def get_tracking_db_path() -> Path:
    """Return the path to the invocation tracking SQLite database.

    The database is stored at ``$XDG_CACHE_HOME/papagai/invocations.db``,
    defaulting to ``~/.cache/papagai/invocations.db``.
    """
    return (
        Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "papagai"
        / "invocations.db"
    )


def record_invocation(
    command: str,
    branch: str,
    directory: str,
    task_name: str | None = None,
) -> None:
    """Record a papagai invocation to the tracking database.

    Opens (or creates) the SQLite database, ensures the schema exists,
    and inserts a row.  WAL journal mode is used so that concurrent
    papagai processes can write without blocking each other.

    Args:
        command: The subcommand that was invoked (e.g. "code", "do",
                 "review", "task").
        branch: The papagai branch containing the result.
        directory: The working directory papagai was invoked from.
        task_name: Optional task identifier.  For the ``task`` command
                   this is the task name; for ``review --mr`` this is
                   ``"mr<number>"``.
    """
    db_path = get_tracking_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                task_name TEXT,
                timestamp TEXT NOT NULL,
                branch TEXT NOT NULL,
                directory TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO invocations"
            " (command, task_name, timestamp, branch, directory)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                command,
                task_name,
                datetime.now(timezone.utc).isoformat(),
                branch,
                directory,
            ),
        )


@dataclass
class Invocation:
    """A single tracked invocation."""

    id: int
    command: str
    task_name: str | None
    timestamp: str
    branch: str
    directory: str


def load_invocations() -> list[Invocation]:
    """Load all invocations from the tracking database.

    Returns an empty list if the database does not exist or has no
    ``invocations`` table yet.
    """
    db_path = get_tracking_db_path()
    if not db_path.exists():
        return []

    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='invocations'"
        )
        if cursor.fetchone() is None:
            return []

        rows = conn.execute(
            "SELECT id, command, task_name, timestamp, branch, directory"
            " FROM invocations ORDER BY id"
        ).fetchall()
        return [
            Invocation(
                id=row[0],
                command=row[1],
                task_name=row[2],
                timestamp=row[3],
                branch=row[4],
                directory=row[5],
            )
            for row in rows
        ]


def delete_invocations(ids: list[int]) -> None:
    """Delete invocations by their IDs.

    Does nothing if the database does not exist or *ids* is empty.
    """
    if not ids:
        return

    db_path = get_tracking_db_path()
    if not db_path.exists():
        return

    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"DELETE FROM invocations WHERE id IN ({placeholders})",
            ids,
        )
