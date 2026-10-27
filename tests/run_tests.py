#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyguitarpro==0.11",
#     "pytest==9.1.1",
# ]
# ///
# SPDX-License-Identifier: MIT
"""Run the test suite with the same pinned versions the skill's script is locked to.

usage: uv run --locked --script tests/run_tests.py [pytest args, e.g. -q -k bend]

Runs from the repository root. The pins must match the scripts' inline metadata; tests/test_pins.py
checks that. The alphaTab tests are skipped unless alphaTab is installed (npm ci --prefix
skills/scale-sequences) and `node` is on PATH.
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:  # re-exec isolated (-I): no PYTHONPATH / user site / cwd
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent.parent)
    sys.exit(pytest.main(sys.argv[1:]))
