#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyguitarpro==0.11"]
# ///
# SPDX-License-Identifier: MIT
"""Private regression: regenerate an exercise you keep OUTSIDE the repository and compare note for note.

Everything specific to the reference lives in the fixture directory (set SCALE_SEQUENCES_PRIVATE_FIXTURE);
the repository holds only this generic harness. The directory must contain:
  sections.json     what should reproduce the reference:
                    {"box": "root",
                     "patterns": {"<name>": {"shape": [0, 2, 1], "default_rhythm": "8t"}},   (optional)
                     "sections": [{"pattern": "<name>", "note": "8", "pickup": "8", "land": "4",
                                   "label": "..."}, ...]}
                    "box" is a built-in box id; "patterns" defines patterns the library lacks, in the
                    format of the CLI's --pattern-file (scaleseq.patterns.add_patterns); each section names
                    a library pattern or one defined there; note/pickup/land/label are optional (see
                    scaleseq.exercise.Section)
  tab_read.json     a verified TAB read, flat layout {section: {"bars": [{"notes": [[s, f], ...]}]}}
  staff_read.json   the matching staff read, flat layout {section: {"bars": [{"events": [{"dur", "triplet",
                    "rest"}]}]}}; sections in the same order as sections.json
  expected.gp5      optional: an earlier file of the same exercise (its title, tempo and markers are reused)

Checks: each section's (string, fret) stream is its pattern's index stream on the box; the plan equals
both reads note for note (string, fret, duration, tuplet, rests, bars, time signatures); the regenerated
.gp5 equals expected.gp5 beat for beat and byte for byte; the full generate pipeline (plan, read-back,
alphaTab parse + render when available) passes with --expect-reads/--expect-gp5, and with
--bend-blue-notes against expected.gp5 (only bent blue notes may differ).

usage: SCALE_SEQUENCES_PRIVATE_FIXTURE=/path/to/fixture uv run --locked --script tests/private_reference.py
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:  # re-exec isolated (-I): no PYTHONPATH / user site / cwd
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

import dataclasses  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "scale-sequences" / "scripts"))

import guitarpro as gp  # noqa: E402

from scaleseq.boxes import get_box  # noqa: E402
from scaleseq.exercise import Section, build_bars, realize  # noqa: E402
from scaleseq.gp5 import read_plan_shape, write_gp5  # noqa: E402
from scaleseq.patterns import add_patterns  # noqa: E402
from scaleseq.pipeline import generate  # noqa: E402
from scaleseq.verify import compare_reads, diff_gp5, find_alphatab  # noqa: E402


def load_sections(fx_dir: Path) -> tuple[str, list[Section]]:
    """The box id and the sections from the fixture's sections.json; patterns it defines are added to the
    library for this process only."""
    spec = json.loads((fx_dir / "sections.json").read_text())
    add_patterns(spec.get("patterns", {}), source="sections.json patterns")
    sections = []
    for d in spec["sections"]:
        if set(d) - {"pattern", "label", "note", "pickup", "land"}:
            raise ValueError(f"sections.json: unknown section fields in {d}")
        d = {"label": d["pattern"], **d}
        sections.append(Section(**d))
        sections[-1].pat()  # unknown pattern -> KeyError now, not halfway through the checks
    return spec["box"], sections


def main() -> int:
    fx = os.environ.get("SCALE_SEQUENCES_PRIVATE_FIXTURE")
    if not fx:
        print("SKIP: set SCALE_SEQUENCES_PRIVATE_FIXTURE=/path/to/fixture (see the docstring)")
        return 0
    fx_dir = Path(fx)
    try:
        box_id, sections = load_sections(fx_dir)
        box = get_box(box_id)
    except (OSError, KeyError, TypeError, ValueError) as e:
        print(f"FAILED: cannot load {fx_dir / 'sections.json'} (see the docstring): {e!r}")
        return 1
    ref_gp5 = fx_dir / "expected.gp5"
    fails: list[str] = []

    # 1. the reads, mapped onto the box, are the sections' index streams
    tab = json.loads((fx_dir / "tab_read.json").read_text())
    idx = box.index_of_sf()
    if len(tab) != len(sections):
        fails.append(f"reads have {len(tab)} sections, sections.json has {len(sections)}")
    for (key, sec), s in zip(tab.items(), sections):
        notes = [tuple(n) for b in sec["bars"] for n in b["notes"]]
        got = [idx.get(n) for n in notes]
        if got != s.pat().stream(box.n):
            fails.append(f"{key}: index stream on the {box.label} is not {s.pattern}")

    # 2. note for note against both reads
    plan = realize(build_bars(sections, box.n), box, marker_fmt="{label}")
    fails += compare_reads(plan, str(fx_dir))

    n_notes = sum(1 for b in plan for x in b["beats"] if not x["rest"])
    with tempfile.TemporaryDirectory() as tmp:
        if ref_gp5.is_file():
            # 3. byte for byte against the earlier file (its title, tempo and markers reused)
            song = gp.parse(str(ref_gp5))
            markers = [b["marker"] for b in read_plan_shape(str(ref_gp5))["bars"] if b["marker"]]
            if len(markers) != len(sections):
                fails.append(f"expected.gp5 has {len(markers)} markers, sections.json has {len(sections)} sections")
            else:
                named = [dataclasses.replace(s, label=m) for s, m in zip(sections, markers)]
                plan = realize(build_bars(named, box.n), box, marker_fmt="{label}")
                regen = Path(tmp) / "regen.gp5"
                write_gp5(plan, str(regen), title=song.title, subtitle=song.subtitle, tempo=song.tempo,
                          root_pc=box.root_pc)
                fails += [f"vs expected.gp5: {d}" for d in diff_gp5(str(ref_gp5), str(regen))]
                if ref_gp5.read_bytes() != regen.read_bytes():
                    fails.append("regenerated file is not byte-identical to expected.gp5")
                # 4. the full pipeline, unbent and with half-step bends
                at = find_alphatab() is not None
                for bend in (False, True):
                    try:
                        generate(box, str(Path(tmp) / f"full_{bend}.gp5"), sections=named, bend_blue=bend,
                                 tempo=song.tempo, title=song.title, subtitle=song.subtitle,
                                 marker_fmt="{label}", alphatab=at,
                                 expect_reads=None if bend else str(fx_dir), expect_gp5=str(ref_gp5))
                    except Exception as e:  # noqa: BLE001 -- report every failure, then exit 1
                        fails.append(f"generate (bend={bend}): {e}")
                if not at:
                    print("note: alphaTab not installed, its checks were skipped")
        else:
            print("note: no expected.gp5 in the fixture, byte-for-byte check skipped")

    if fails:
        print("FAILED:\n - " + "\n - ".join(fails))
        return 1
    print(f"OK: sections.json on the {box.label} reproduces the private reference "
          f"({len(plan)} bars, {n_notes} notes, {len(sections)} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
