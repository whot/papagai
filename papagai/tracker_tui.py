#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Interactive TUI for browsing papagai invocation history."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.widgets import DataTable, Footer, Input, Label

from .tracking import Invocation, delete_invocations, load_invocations


def _detect_terminal_theme() -> str:
    """Detect whether the terminal uses a light or dark background.

    Checks ``COLORFGBG`` (set by rxvt, xterm, and others) where the
    format is ``fg;bg`` and a bg value < 7 means a dark background.
    Falls back to ``textual-dark`` when detection is inconclusive.
    """
    colorfgbg = os.environ.get("COLORFGBG")
    if colorfgbg:
        try:
            bg = int(colorfgbg.rsplit(";", 1)[-1])
            # ANSI colors 0-6 are dark, 7+ are light (7 = white/light gray)
            return "textual-light" if bg >= 7 else "textual-dark"
        except (ValueError, IndexError):
            pass

    return "textual-dark"


# Column definitions: (key, label)
COLUMNS: list[tuple[str, str]] = [
    ("timestamp", "Date"),
    ("command", "Command"),
    ("task_name", "Task"),
    ("num_commits", "Commits"),
    ("directory", "Directory"),
    ("branch", "Branch"),
]


def _format_timestamp(iso: str) -> str:
    """Format an ISO 8601 timestamp to a compact local-time string."""
    try:
        dt = datetime.fromisoformat(iso)
        # Convert to local time
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return iso[:16]


def _compute_directory_labels(invocations: list[Invocation]) -> dict[str, str]:
    """Compute display labels for directories.

    Uses the basename of the directory by default.  If two different
    full paths share the same basename, the full path is used for both
    to avoid ambiguity.
    """
    # Count how many distinct full paths map to each basename
    basename_to_paths: dict[str, set[str]] = {}
    for inv in invocations:
        base = Path(inv.directory).name
        basename_to_paths.setdefault(base, set()).add(inv.directory)

    # Basenames that map to more than one distinct path are ambiguous
    ambiguous: set[str] = set()
    for base, paths in basename_to_paths.items():
        if len(paths) > 1:
            ambiguous.add(base)

    result: dict[str, str] = {}
    for inv in invocations:
        d = inv.directory
        if d in result:
            continue
        base = Path(d).name
        result[d] = d if base in ambiguous else base

    return result


class TrackerApp(App):
    """Mutt-like TUI for browsing papagai invocations."""

    TITLE = "papagai tracker"

    CSS = """
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    #status-label {
        width: 1fr;
    }
    #filter-input {
        display: none;
        width: 1fr;
    }
    #filter-input.visible {
        display: block;
    }
    DataTable {
        height: 1fr;
    }
    DataTable > .datatable--cursor {
        background: $accent;
    }
    """

    # Most key handling is done in on_key() to ensure our actions
    # take priority over the DataTable's built-in bindings.
    BINDINGS = [
        Binding("q", "quit_app", "Quit", show=True),
        Binding("escape", "clear_filter", "Clear filter", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.theme = _detect_terminal_theme()
        self._invocations: list[Invocation] = []
        self._dir_labels: dict[str, str] = {}
        self._marked_for_deletion: set[int] = set()
        self._selected_column: int = 0
        self._filter_text: str = ""
        self._sort_column: int | None = None
        self._sort_reverse: bool = False
        # Filtered + sorted view indices into _invocations
        self._view: list[int] = []

    def compose(self) -> ComposeResult:
        yield DataTable()
        with Horizontal(id="status-bar"):
            yield Label("", id="status-label")
            yield Input(placeholder="filter...", id="filter-input")
        yield Footer()

    def on_mount(self) -> None:
        self._invocations = load_invocations()
        self._dir_labels = _compute_directory_labels(self._invocations)
        self._rebuild_table()

    def _get_field(self, inv: Invocation, col_idx: int) -> str:
        """Return the display string for a given column index."""
        key = COLUMNS[col_idx][0]
        if key == "timestamp":
            return _format_timestamp(inv.timestamp)
        if key == "command":
            return inv.command
        if key == "task_name":
            return inv.task_name or ""
        if key == "num_commits":
            return str(inv.num_commits) if inv.num_commits is not None else ""
        if key == "directory":
            return self._dir_labels.get(inv.directory, inv.directory)
        if key == "branch":
            return inv.branch
        return ""

    def _matches_filter(self, idx: int) -> bool:
        """Return True if invocation at index matches the current filter."""
        if not self._filter_text:
            return True
        inv = self._invocations[idx]
        needle = self._filter_text.lower()
        for col_idx in range(len(COLUMNS)):
            if needle in self._get_field(inv, col_idx).lower():
                return True
        return False

    def _rebuild_view(self) -> None:
        """Rebuild the filtered+sorted index list."""
        self._view = [
            i for i in range(len(self._invocations)) if self._matches_filter(i)
        ]

        if self._sort_column is not None:
            col_idx = self._sort_column
            col_key = COLUMNS[col_idx][0]
            if col_key == "num_commits":
                self._view.sort(
                    key=lambda i: self._invocations[i].num_commits or 0,
                    reverse=self._sort_reverse,
                )
            else:
                self._view.sort(
                    key=lambda i: self._get_field(
                        self._invocations[i], col_idx
                    ).lower(),
                    reverse=self._sort_reverse,
                )

    def _rebuild_table(self) -> None:
        """Rebuild the DataTable from scratch."""
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"

        # Add a marker column + the data columns
        table.add_column(" ", key="marker")
        for col_idx, (key, label) in enumerate(COLUMNS):
            marker = " >" if col_idx == self._selected_column else "  "
            table.add_column(f"{marker}{label}", key=key)

        self._rebuild_view()

        for view_idx in self._view:
            inv = self._invocations[view_idx]
            marker = "D" if inv.id in self._marked_for_deletion else " "
            cells = [marker]
            for col_idx in range(len(COLUMNS)):
                cells.append(self._get_field(inv, col_idx))
            table.add_row(*cells, key=str(inv.id))

        self._update_status()

    def _update_status(self) -> None:
        """Update the status bar label."""
        label = self.query_one("#status-label", Label)
        n_total = len(self._invocations)
        n_visible = len(self._view)
        n_marked = len(self._marked_for_deletion)

        parts = [f"{n_visible}/{n_total} invocations"]
        if n_marked:
            parts.append(f"{n_marked} marked for deletion")
        if self._filter_text:
            parts.append(f"filter: {self._filter_text}")

        if self._sort_column is not None:
            sort_dir = "desc" if self._sort_reverse else "asc"
            sort_col_label = COLUMNS[self._sort_column][1]
            parts.append(f"sort: {sort_col_label} {sort_dir}")

        label.update(" | ".join(parts))

    def _current_invocation(self) -> Invocation | None:
        """Return the invocation under the cursor, or None."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            inv_id = int(row_key.value)
            for inv in self._invocations:
                if inv.id == inv_id:
                    return inv
        except Exception:
            pass
        return None

    # -- Actions --

    def action_quit_app(self) -> None:
        """Quit and apply pending deletions."""
        if self._marked_for_deletion:
            delete_invocations(list(self._marked_for_deletion))
        self.exit()

    def action_cursor_down(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_up()

    def action_column_left(self) -> None:
        if self._selected_column > 0:
            self._selected_column -= 1
            self._rebuild_table()

    def action_column_right(self) -> None:
        if self._selected_column < len(COLUMNS) - 1:
            self._selected_column += 1
            self._rebuild_table()

    def action_sort_asc(self) -> None:
        self._sort_column = self._selected_column
        self._sort_reverse = False
        self._rebuild_table()

    def action_sort_desc(self) -> None:
        self._sort_column = self._selected_column
        self._sort_reverse = True
        self._rebuild_table()

    def action_mark_delete(self) -> None:
        inv = self._current_invocation()
        if inv is None:
            return
        self._marked_for_deletion.add(inv.id)
        # Update marker cell in place
        table = self.query_one(DataTable)
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            table.update_cell(row_key, "marker", "D")
        except Exception:
            pass
        self._update_status()
        table.action_cursor_down()

    def action_unmark_delete(self) -> None:
        inv = self._current_invocation()
        if inv is None:
            return
        self._marked_for_deletion.discard(inv.id)
        table = self.query_one(DataTable)
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            table.update_cell(row_key, "marker", " ")
        except Exception:
            pass
        self._update_status()

    def action_open_terminal(self) -> None:
        """Open a shell in the invocation's directory with PAPAGAI_BRANCH set."""
        inv = self._current_invocation()
        if inv is None:
            return

        directory = inv.directory
        if not Path(directory).is_dir():
            self.notify(f"Directory does not exist: {directory}", severity="error")
            return

        shell = os.environ.get("SHELL", "/bin/sh")
        env = os.environ.copy()
        env["PAPAGAI_BRANCH"] = inv.branch

        with self.suspend():
            try:
                subprocess.run([shell], cwd=directory, env=env, check=False)
            except FileNotFoundError:
                self.notify(f"Shell '{shell}' not found. Set $SHELL.", severity="error")

    def action_start_filter(self) -> None:
        """Show the filter input."""
        filter_input = self.query_one("#filter-input", Input)
        filter_input.add_class("visible")
        filter_input.value = self._filter_text
        filter_input.focus()

    def action_clear_filter(self) -> None:
        """Clear the current filter."""
        filter_input = self.query_one("#filter-input", Input)
        filter_input.remove_class("visible")
        filter_input.value = ""
        if self._filter_text:
            self._filter_text = ""
            self._rebuild_table()
        self.query_one(DataTable).focus()

    @on(Input.Submitted, "#filter-input")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        """Apply the filter when Enter is pressed in the filter input."""
        self._filter_text = event.value
        filter_input = self.query_one("#filter-input", Input)
        filter_input.remove_class("visible")
        self._rebuild_table()
        self.query_one(DataTable).focus()

    # Map of key -> action method name for keys handled in on_key().
    _KEY_MAP: dict[str, str] = {
        "j": "action_cursor_down",
        "down": "action_cursor_down",
        "k": "action_cursor_up",
        "up": "action_cursor_up",
        "h": "action_column_left",
        "left": "action_column_left",
        "l": "action_column_right",
        "right": "action_column_right",
        "s": "action_sort_asc",
        "S": "action_sort_desc",
        "d": "action_mark_delete",
        "u": "action_unmark_delete",
        "enter": "action_open_terminal",
        "slash": "action_start_filter",
    }

    def on_key(self, event: Key) -> None:
        """Central key handler.

        All custom keys are handled here instead of via BINDINGS so that
        they take priority over the DataTable's built-in key bindings
        (which would otherwise consume enter, arrow keys, etc.).
        """
        # If the filter input is focused, let it handle keys normally
        filter_input = self.query_one("#filter-input", Input)
        if filter_input.has_focus:
            return

        # Check character first (for S vs s), then key name
        action = self._KEY_MAP.get(event.character or "", None)
        if action is None:
            action = self._KEY_MAP.get(event.key, None)
        if action is not None:
            event.stop()
            event.prevent_default()
            getattr(self, action)()


def run_tracker() -> None:
    """Entry point for the tracker TUI."""
    app = TrackerApp()
    app.run()
