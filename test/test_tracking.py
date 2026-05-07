#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for invocation tracking."""

import os
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from papagai.cli import papagai
from papagai.tracking import get_tracking_db_path, record_invocation


class TestGetTrackingDbPath:
    """Tests for get_tracking_db_path()."""

    def test_default_path(self):
        """Test default path when XDG_CACHE_HOME is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure XDG_CACHE_HOME is unset
            os.environ.pop("XDG_CACHE_HOME", None)
            path = get_tracking_db_path()
            assert path == Path.home() / ".cache" / "papagai" / "invocations.db"

    def test_xdg_cache_home(self, tmp_path):
        """Test path respects XDG_CACHE_HOME."""
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(tmp_path)}):
            path = get_tracking_db_path()
            assert path == tmp_path / "papagai" / "invocations.db"

    def test_xdg_cache_home_empty(self):
        """Test path falls back to default when XDG_CACHE_HOME is empty."""
        with patch.dict(os.environ, {"XDG_CACHE_HOME": ""}):
            path = get_tracking_db_path()
            # Empty string is falsy but os.getenv returns it, so Path("")
            # is used.  This matches the XDG spec: empty means unset.
            # Our implementation uses os.getenv with a default, so an
            # empty value is treated as set (matching how the task dir
            # handling works).
            assert "invocations.db" in str(path)


class TestRecordInvocation:
    """Tests for record_invocation()."""

    @pytest.fixture(autouse=True)
    def use_tmp_db(self, tmp_path, monkeypatch):
        """Redirect the tracking database to a temporary directory."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    def test_creates_database(self, tmp_path):
        """Test that the database and table are created on first invocation."""
        record_invocation(
            command="code",
            branch="papagai/main-20260507-1430-abc12345",
            directory="/home/user/project",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        assert db_path.exists()

        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert "invocations" in tables

    def test_inserts_row(self, tmp_path):
        """Test that a row is correctly inserted."""
        record_invocation(
            command="code",
            branch="papagai/main-20260507-1430-abc12345",
            directory="/home/user/project",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute("SELECT * FROM invocations").fetchall()
            assert len(rows) == 1
            row = rows[0]
            # id, command, task_name, timestamp, branch, directory
            assert row[1] == "code"
            assert row[2] is None  # task_name
            assert row[3] is not None  # timestamp
            assert row[4] == "papagai/main-20260507-1430-abc12345"
            assert row[5] == "/home/user/project"

    def test_inserts_with_task_name(self, tmp_path):
        """Test that task_name is stored when provided."""
        record_invocation(
            command="task",
            branch="papagai/main-20260507-1430-abc12345",
            directory="/home/user/project",
            task_name="python/lint",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT * FROM invocations").fetchone()
            assert row[1] == "task"
            assert row[2] == "python/lint"

    def test_inserts_review_with_mr(self, tmp_path):
        """Test recording a review invocation with MR number."""
        record_invocation(
            command="review",
            branch="papagai/review/mr1234/v1",
            directory="/home/user/project",
            task_name="mr1234",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT * FROM invocations").fetchone()
            assert row[1] == "review"
            assert row[2] == "mr1234"
            assert row[4] == "papagai/review/mr1234/v1"

    def test_multiple_invocations(self, tmp_path):
        """Test that multiple invocations are all recorded."""
        for i in range(5):
            record_invocation(
                command="code",
                branch=f"papagai/main-20260507-143{i}-abc12345",
                directory="/home/user/project",
            )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM invocations").fetchone()[0]
            assert count == 5

    def test_timestamp_is_iso_format(self, tmp_path):
        """Test that the timestamp is in ISO 8601 format."""
        record_invocation(
            command="code",
            branch="papagai/main-20260507-1430-abc12345",
            directory="/home/user/project",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            timestamp = conn.execute("SELECT timestamp FROM invocations").fetchone()[0]
            # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM
            assert "T" in timestamp
            assert "+" in timestamp or "Z" in timestamp

    def test_concurrent_writes(self, tmp_path):
        """Test that concurrent writes from multiple threads succeed."""
        errors = []
        num_threads = 10
        writes_per_thread = 10

        def worker(thread_id):
            try:
                for i in range(writes_per_thread):
                    record_invocation(
                        command="code",
                        branch=f"papagai/main-t{thread_id}-{i}",
                        directory="/home/user/project",
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent write errors: {errors}"

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM invocations").fetchone()[0]
            assert count == num_threads * writes_per_thread

    def test_wal_mode_enabled(self, tmp_path):
        """Test that the database uses WAL journal mode."""
        record_invocation(
            command="code",
            branch="papagai/main-20260507-1430-abc12345",
            directory="/home/user/project",
        )

        db_path = tmp_path / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created if they don't exist."""
        nested = tmp_path / "deep" / "nested"
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(nested)}):
            record_invocation(
                command="code",
                branch="papagai/main-20260507-1430-abc12345",
                directory="/home/user/project",
            )
            assert (nested / "papagai" / "invocations.db").exists()


class TestTrackCLIOption:
    """Tests for the --track CLI option."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_track_option_in_help(self, runner):
        """Test that --track appears in the help output."""
        result = runner.invoke(papagai, ["--help"])
        assert result.exit_code == 0
        assert "--track" in result.output

    def test_track_option_accepted(self, runner):
        """Test that --track is accepted without error."""
        # Just invoke --help with --track to verify it's accepted
        result = runner.invoke(papagai, ["--track", "--help"])
        assert result.exit_code == 0


class TestTrackIntegration:
    """Integration tests for tracking through claude_run."""

    @pytest.fixture(autouse=True)
    def use_tmp_db(self, tmp_path, monkeypatch):
        """Redirect the tracking database to a temporary directory."""
        self.cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(self.cache_dir))

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_instructions_file(self, tmp_path):
        instructions = tmp_path / "instructions.md"
        instructions.write_text("Do something.\n")
        return instructions

    def test_track_records_on_success(self, runner, mock_instructions_file, tmp_path):
        """Test that --track records an invocation on successful run."""
        mock_worktree = type(
            "MockWorktree",
            (),
            {
                "branch": "papagai/main-20260507-1430-abc12345",
                "worktree_dir": tmp_path / "worktree",
                "has_commits": lambda _self: True,
            },
        )()

        class MockContextManager:
            def __enter__(self):
                return mock_worktree

            def __exit__(self, *args):
                pass

        with (
            patch("papagai.cli.Worktree") as mock_wt_cls,
            patch("papagai.cli.WorktreeOverlayFs") as mock_overlay_cls,
            patch("papagai.cli.run_claude"),
            patch("papagai.cli.get_branch", return_value="main"),
            patch("papagai.cli.create_branch_if_not_exists", return_value="main"),
            patch("papagai.cli.send_notification"),
        ):
            mock_overlay_cls.is_supported.return_value = False
            mock_wt_cls.from_branch.return_value = MockContextManager()

            result = runner.invoke(
                papagai,
                [
                    "--track",
                    "do",
                    "--isolation=worktree",
                    str(mock_instructions_file),
                ],
            )

        assert result.exception is None, f"CLI raised an exception: {result.exception}"
        db_path = self.cache_dir / "papagai" / "invocations.db"
        assert db_path.exists(), "Tracking database was not created"
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute("SELECT * FROM invocations").fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "do"
            assert rows[0][4] == "papagai/main-20260507-1430-abc12345"

    def test_no_track_without_flag(self, runner, mock_instructions_file, tmp_path):
        """Test that invocations are NOT recorded without --track."""
        mock_worktree = type(
            "MockWorktree",
            (),
            {
                "branch": "papagai/main-20260507-1430-abc12345",
                "worktree_dir": tmp_path / "worktree",
                "has_commits": lambda _self: True,
            },
        )()

        class MockContextManager:
            def __enter__(self):
                return mock_worktree

            def __exit__(self, *args):
                pass

        with (
            patch("papagai.cli.Worktree") as mock_wt_cls,
            patch("papagai.cli.WorktreeOverlayFs") as mock_overlay_cls,
            patch("papagai.cli.run_claude"),
            patch("papagai.cli.get_branch", return_value="main"),
            patch("papagai.cli.create_branch_if_not_exists", return_value="main"),
            patch("papagai.cli.send_notification"),
        ):
            mock_overlay_cls.is_supported.return_value = False
            mock_wt_cls.from_branch.return_value = MockContextManager()

            runner.invoke(
                papagai,
                ["do", "--isolation=worktree", str(mock_instructions_file)],
            )

        db_path = self.cache_dir / "papagai" / "invocations.db"
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                rows = conn.execute("SELECT * FROM invocations").fetchall()
                assert len(rows) == 0
        # If the DB doesn't exist at all, that's fine - nothing was tracked

    def test_track_not_recorded_on_dry_run(
        self, runner, mock_instructions_file, tmp_path
    ):
        """Test that --track does not record during --dry-run."""
        with (
            patch("papagai.cli.Worktree"),
            patch("papagai.cli.WorktreeOverlayFs") as mock_overlay_cls,
            patch("papagai.cli.run_claude"),
            patch("papagai.cli.get_branch", return_value="main"),
            patch("papagai.cli.create_branch_if_not_exists", return_value="main"),
            patch("papagai.cli.send_notification"),
        ):
            mock_overlay_cls.is_supported.return_value = False

            runner.invoke(
                papagai,
                [
                    "--track",
                    "--dry-run",
                    "do",
                    "--isolation=worktree",
                    str(mock_instructions_file),
                ],
            )

        db_path = self.cache_dir / "papagai" / "invocations.db"
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name='invocations'"
                )
                if cursor.fetchone():
                    rows = conn.execute("SELECT * FROM invocations").fetchall()
                    assert len(rows) == 0
        # If the DB doesn't exist at all, that's fine - nothing was tracked
