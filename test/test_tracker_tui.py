#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the tracker TUI."""

import os
import sqlite3
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from papagai.cli import papagai
from papagai.tracking import Invocation, record_invocation

try:
    from papagai.tracker_tui import (
        COLUMNS,
        TrackerApp,
        _compute_directory_labels,
        _detect_terminal_theme,
        _format_timestamp,
    )

    has_textual = True
except ImportError:
    has_textual = False

pytestmark = pytest.mark.skipif(not has_textual, reason="textual is not installed")


class TestFormatTimestamp:
    """Tests for _format_timestamp()."""

    def test_iso_utc_timestamp(self):
        result = _format_timestamp("2026-05-07T14:30:00+00:00")
        assert "2026" in result
        assert "05" in result or "5" in result

    def test_invalid_timestamp_returns_truncated(self):
        result = _format_timestamp("not-a-timestamp-at-all")
        assert result == "not-a-timestamp-"

    def test_short_invalid_timestamp(self):
        result = _format_timestamp("short")
        assert result == "short"


class TestDetectTerminalTheme:
    """Tests for _detect_terminal_theme()."""

    def test_dark_background_from_colorfgbg(self):
        """COLORFGBG with dark bg (0-6) returns textual-dark."""
        with patch.dict(os.environ, {"COLORFGBG": "15;0"}):
            assert _detect_terminal_theme() == "textual-dark"

    def test_light_background_from_colorfgbg(self):
        """COLORFGBG with light bg (>=7) returns textual-light."""
        with patch.dict(os.environ, {"COLORFGBG": "0;15"}):
            assert _detect_terminal_theme() == "textual-light"

    def test_colorfgbg_with_middle_value(self):
        """COLORFGBG with bg=7 (white) returns textual-light."""
        with patch.dict(os.environ, {"COLORFGBG": "0;7"}):
            assert _detect_terminal_theme() == "textual-light"

    def test_colorfgbg_with_three_values(self):
        """Some terminals emit three semicolon-separated values."""
        with patch.dict(os.environ, {"COLORFGBG": "0;default;15"}):
            assert _detect_terminal_theme() == "textual-light"

    def test_colorfgbg_not_set(self):
        """Falls back to textual-dark when COLORFGBG is not set."""
        env = os.environ.copy()
        env.pop("COLORFGBG", None)
        with patch.dict(os.environ, env, clear=True):
            assert _detect_terminal_theme() == "textual-dark"

    def test_colorfgbg_invalid(self):
        """Falls back to textual-dark when COLORFGBG is garbage."""
        with patch.dict(os.environ, {"COLORFGBG": "not-a-number"}):
            assert _detect_terminal_theme() == "textual-dark"


class TestComputeDirectoryLabels:
    """Tests for _compute_directory_labels()."""

    def _make_inv(self, directory: str) -> Invocation:
        return Invocation(
            id=1,
            command="code",
            task_name=None,
            timestamp="2026-05-07T14:30:00+00:00",
            branch="papagai/main-20260507-1430-abc12345",
            directory=directory,
        )

    def test_unique_basenames_use_basename(self):
        invocations = [
            self._make_inv("/home/user/project-a"),
            self._make_inv("/home/user/project-b"),
        ]
        labels = _compute_directory_labels(invocations)
        assert labels["/home/user/project-a"] == "project-a"
        assert labels["/home/user/project-b"] == "project-b"

    def test_duplicate_basenames_use_full_path(self):
        invocations = [
            self._make_inv("/home/alice/myproject"),
            self._make_inv("/home/bob/myproject"),
        ]
        labels = _compute_directory_labels(invocations)
        assert labels["/home/alice/myproject"] == "/home/alice/myproject"
        assert labels["/home/bob/myproject"] == "/home/bob/myproject"

    def test_same_path_repeated_uses_basename(self):
        invocations = [
            self._make_inv("/home/user/project"),
            self._make_inv("/home/user/project"),
        ]
        labels = _compute_directory_labels(invocations)
        assert labels["/home/user/project"] == "project"

    def test_mixed_unique_and_duplicate(self):
        invocations = [
            self._make_inv("/home/alice/myproject"),
            self._make_inv("/home/bob/myproject"),
            self._make_inv("/home/user/unique-project"),
        ]
        labels = _compute_directory_labels(invocations)
        assert labels["/home/alice/myproject"] == "/home/alice/myproject"
        assert labels["/home/bob/myproject"] == "/home/bob/myproject"
        assert labels["/home/user/unique-project"] == "unique-project"

    def test_empty_list(self):
        labels = _compute_directory_labels([])
        assert labels == {}


class TestTrackerAppUnit:
    """Unit tests for TrackerApp internals (no async)."""

    @pytest.fixture(autouse=True)
    def use_tmp_db(self, tmp_path, monkeypatch):
        self.cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(self.cache_dir))

    def _populate_db(self, entries: list[tuple[str, str, str | None]]):
        """Insert entries as (command, directory, task_name)."""
        for command, directory, task_name in entries:
            record_invocation(
                command=command,
                branch=f"papagai/main-branch-{command}",
                directory=directory,
                task_name=task_name,
            )

    def test_app_loads_empty_db(self):
        """App should handle empty/missing database gracefully."""
        app = TrackerApp()
        assert app._invocations == []

    def test_app_instantiates(self):
        """Basic smoke test for app creation."""
        app = TrackerApp()
        assert app._marked_for_deletion == set()
        assert app._selected_column == 0
        assert app._filter_text == ""


class TestTrackerAppAsync:
    """Async tests using textual's test framework."""

    @pytest.fixture(autouse=True)
    def use_tmp_db(self, tmp_path, monkeypatch):
        self.cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(self.cache_dir))

    def _populate_db(self, entries: list[tuple[str, str, str | None]]):
        for command, directory, task_name in entries:
            record_invocation(
                command=command,
                branch=f"papagai/{command}-branch",
                directory=directory,
                task_name=task_name,
            )

    @pytest.mark.asyncio
    async def test_app_mounts_with_data(self):
        """Test the app mounts and displays data."""
        self._populate_db(
            [
                ("code", "/home/user/project-a", None),
                ("review", "/home/user/project-b", "mr42"),
            ]
        )

        app = TrackerApp()
        async with app.run_test():
            table = app.query_one("DataTable")
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_app_mounts_empty(self):
        """Test the app mounts with no data."""
        app = TrackerApp()
        async with app.run_test():
            table = app.query_one("DataTable")
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_j_k_navigation(self):
        """Test j/k move cursor down/up."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
                ("task", "/home/user/p3", "lint"),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()
            assert table.cursor_coordinate.row == 0

            await pilot.press("j")
            assert table.cursor_coordinate.row == 1

            await pilot.press("j")
            assert table.cursor_coordinate.row == 2

            await pilot.press("k")
            assert table.cursor_coordinate.row == 1

    @pytest.mark.asyncio
    async def test_arrow_key_navigation(self):
        """Test arrow keys move cursor and columns."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
                ("task", "/home/user/p3", "lint"),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()
            assert table.cursor_coordinate.row == 0

            await pilot.press("down")
            assert table.cursor_coordinate.row == 1

            await pilot.press("down")
            assert table.cursor_coordinate.row == 2

            await pilot.press("up")
            assert table.cursor_coordinate.row == 1

            # Column navigation with arrow keys
            assert app._selected_column == 0

            await pilot.press("right")
            assert app._selected_column == 1

            await pilot.press("left")
            assert app._selected_column == 0

    @pytest.mark.asyncio
    async def test_h_l_column_navigation(self):
        """Test h/l change the selected column."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            assert app._selected_column == 0

            await pilot.press("l")
            assert app._selected_column == 1

            await pilot.press("l")
            assert app._selected_column == 2

            await pilot.press("h")
            assert app._selected_column == 1

            await pilot.press("h")
            assert app._selected_column == 0

            # Should not go below 0
            await pilot.press("h")
            assert app._selected_column == 0

    @pytest.mark.asyncio
    async def test_h_l_column_bounds(self):
        """Test h/l don't go out of bounds."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            # Move to rightmost column
            for _ in range(len(COLUMNS) + 2):
                await pilot.press("l")
            assert app._selected_column == len(COLUMNS) - 1

            # Move to leftmost column
            for _ in range(len(COLUMNS) + 2):
                await pilot.press("h")
            assert app._selected_column == 0

    @pytest.mark.asyncio
    async def test_d_marks_for_deletion(self):
        """Test d marks an entry for deletion."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            await pilot.press("d")
            assert len(app._marked_for_deletion) == 1

    @pytest.mark.asyncio
    async def test_u_unmarks_deletion(self):
        """Test u unmarks an entry."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            await pilot.press("d")
            assert len(app._marked_for_deletion) == 1

            # Move back up (d advances cursor)
            await pilot.press("k")
            await pilot.press("u")
            assert len(app._marked_for_deletion) == 0

    @pytest.mark.asyncio
    async def test_sort_ascending(self):
        """Test s sorts by selected column ascending."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
                ("task", "/home/user/p3", "lint"),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            # Select the "Command" column (index 1)
            await pilot.press("l")
            assert app._selected_column == 1

            await pilot.press("s")
            assert app._sort_column == 1
            assert app._sort_reverse is False

    @pytest.mark.asyncio
    async def test_sort_descending(self):
        """Test S sorts by selected column descending."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            await pilot.press("l")
            await pilot.press("S")
            assert app._sort_column == 1
            assert app._sort_reverse is True

    @pytest.mark.asyncio
    async def test_filter_and_clear(self):
        """Test / opens filter, typing filters, Esc clears."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("review", "/home/user/p2", "mr42"),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            assert table.row_count == 2

            # Open filter
            await pilot.press("slash")
            filter_input = app.query_one("#filter-input")
            assert filter_input.has_class("visible")

            # Type filter text and submit
            await pilot.press("r", "e", "v", "i", "e", "w")
            await pilot.press("enter")

            assert app._filter_text == "review"
            assert table.row_count == 1

            # Clear filter
            await pilot.press("escape")
            assert app._filter_text == ""
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_quit_applies_deletions(self):
        """Test q applies pending deletions to the database."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            # Mark first entry for deletion
            await pilot.press("d")
            assert len(app._marked_for_deletion) == 1

            await pilot.press("q")

        # Verify deletion was applied to DB
        db_path = self.cache_dir / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM invocations").fetchone()[0]
            assert count == 1

    @pytest.mark.asyncio
    async def test_quit_deletes_git_branches(self):
        """Test that quitting with deletions also deletes git branches."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            await pilot.press("d")

            with patch("papagai.tracker_tui.subprocess.run") as mock_run:
                await pilot.press("q")

                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][0][:3] == ["git", "branch", "-D"]
                assert call_args[1]["check"] is False

    @pytest.mark.asyncio
    async def test_mark_partial(self):
        """Test P marks entry as partial."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()
            await pilot.press("P")

            inv = app._current_invocation()
            assert inv is not None
            assert inv.review_state == "partial"

        # Verify persisted to DB
        db_path = self.cache_dir / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            state = conn.execute("SELECT review_state FROM invocations").fetchone()[0]
            assert state == "partial"

    @pytest.mark.asyncio
    async def test_mark_reviewed(self):
        """Test R marks entry as reviewed."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()
            await pilot.press("R")

            inv = app._current_invocation()
            assert inv is not None
            assert inv.review_state == "reviewed"

    @pytest.mark.asyncio
    async def test_mark_obsolete(self):
        """Test O marks entry as obsolete."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()
            await pilot.press("O")

            inv = app._current_invocation()
            assert inv is not None
            assert inv.review_state == "obsolete"

    @pytest.mark.asyncio
    async def test_review_state_toggle(self):
        """Test pressing the same state key again clears it."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            await pilot.press("P")
            assert app._current_invocation().review_state == "partial"

            await pilot.press("P")
            assert app._current_invocation().review_state is None

    @pytest.mark.asyncio
    async def test_review_state_change(self):
        """Test changing from one state to another."""
        self._populate_db([("code", "/home/user/p1", None)])

        app = TrackerApp()
        async with app.run_test() as pilot:
            table = app.query_one("DataTable")
            table.focus()

            await pilot.press("P")
            assert app._current_invocation().review_state == "partial"

            await pilot.press("R")
            assert app._current_invocation().review_state == "reviewed"

    @pytest.mark.asyncio
    async def test_quit_without_deletions(self):
        """Test q without deletions doesn't alter DB."""
        self._populate_db(
            [
                ("code", "/home/user/p1", None),
                ("do", "/home/user/p2", None),
            ]
        )

        app = TrackerApp()
        async with app.run_test() as pilot:
            await pilot.press("q")

        db_path = self.cache_dir / "papagai" / "invocations.db"
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM invocations").fetchone()[0]
            assert count == 2


class TestTrackerCLICommand:
    """Tests for the tracker CLI subcommand."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_tracker_in_help(self, runner):
        """Test that tracker appears in the help output."""
        with patch("papagai.cli.send_notification"):
            result = runner.invoke(papagai, ["--help"])
        assert result.exit_code == 0
        assert "tracker" in result.output

    def test_tracker_help(self, runner):
        """Test tracker --help."""
        with patch("papagai.cli.send_notification"):
            result = runner.invoke(papagai, ["tracker", "--help"])
        assert result.exit_code == 0
        assert "Browse invocation history" in result.output
