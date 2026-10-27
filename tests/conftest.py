# SPDX-License-Identifier: MIT
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills" / "scale-sequences" / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def mini_box(monkeypatch):
    """A 6-note one-octave A minor blues box (A C D D# E G) small enough to write out by hand."""
    from scaleseq import boxes
    monkeypatch.setitem(boxes.BOX_SPECS, "mini", {
        "label": "mini shape", "key": "A", "scale": "minor-blues",
        "frets": {6: [(5, 1), (8, 4)], 5: [(5, 1), (6, 2), (7, 3)], 4: [(5, 1)]},
    })
    return boxes.get_box("mini")


@pytest.fixture
def restore_library():
    """Patterns a test loads from a pattern file are gone again after the test."""
    from scaleseq import patterns
    saved = dict(patterns.PATTERNS), dict(patterns.ALIASES)
    yield
    for live, old in zip((patterns.PATTERNS, patterns.ALIASES), saved):
        live.clear()
        live.update(old)


def alphatab_available() -> bool:
    import shutil
    from scaleseq.verify import find_alphatab
    return bool(find_alphatab() and shutil.which("node"))
