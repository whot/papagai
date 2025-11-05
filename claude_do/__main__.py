#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Entry point for running claude-do as a module: python -m claude_do"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
