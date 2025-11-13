#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Entry point for running papagai as a module: python -m papagai"""

import sys

from .cli import papagai

if __name__ == "__main__":
    sys.exit(papagai())
