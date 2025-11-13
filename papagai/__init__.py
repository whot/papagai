#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""papagai: A CLI tool to run Claude on git worktrees with automated commits."""

__version__ = "0.1.0"

from .cli import papagai

__all__ = ["papagai"]
