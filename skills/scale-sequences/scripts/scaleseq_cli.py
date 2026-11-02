#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyguitarpro==0.11"]
# ///
# SPDX-License-Identifier: MIT
"""scaleseq -- scale-box sequence exercises as verified .gp5 files.

  scaleseq_cli.py boxes [--key K]                      box diagrams (degree / suggested finger)
  scaleseq_cli.py patterns [--n N] [--pattern-file F]  pattern library in index notation
  scaleseq_cli.py generate --box b7 --patterns 4s,3s:8t,1231 -o out.gp5 [--bend-blue-notes | --one-pick-bends]
              [--tempo 80] [--key A | --fret-offset N] [--title T] [--subtitle S] [--plain-markers]
              [--fingering] [--no-alphatab] [--no-render] [--force] [--json]
              [--expect-reads DIR] [--expect-gp5 FILE] [--pattern-file F]
  scaleseq_cli.py analyze --box root --reads DIR [--pattern-file F]
                                                       index streams of a reference + matching patterns

--patterns: one section per entry, pattern[:rhythm][:stop=N][:skip=N[+N...]]. Groups are numbered from
0 at the bottom of the box (group N = the group built on box note N). stop=N: the descent ends at group N
instead of coming all the way down, then the line lands on the box's lowest note. skip=N+M: the descent
leaves groups N and M out. E.g. --patterns 3s:8t:stop=3,thirds:16:skip=2+5.

--pattern-file F: a JSON file of the user's own, kept outside this skill, that defines extra patterns
for this run only: {"<name>": {"shape": [0, 2, 1], "default_rhythm": "8t", ...}} (any field of
scaleseq.patterns.Pattern; lists for its tuple fields).

Every generate runs all checks (plan, read-back, alphaTab parse + MIDI + render) before the file
is moved into place; any failure exits 1 and leaves no file.
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:  # re-exec isolated (-I): no PYTHONPATH / user site / cwd
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

import argparse  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir from sys.path

from scaleseq.boxes import ALIASES as BOX_ALIASES  # noqa: E402
from scaleseq.boxes import BOX_SPECS, BoxError, get_box  # noqa: E402
from scaleseq.exercise import DURS  # noqa: E402
from scaleseq.patterns import PATTERNS, load_pattern_file  # noqa: E402
from scaleseq.pipeline import SPEC_FORM, CheckFailed, generate, resolve_sections  # noqa: E402


def cmd_boxes(a) -> int:
    for bid in BOX_SPECS:
        box = get_box(bid, key=a.key)
        print(box.diagram())
        print(f"  {box.n} notes; blue notes (b5) at box indices {box.blue_indices()}\n")
    return 0


def cmd_patterns(a) -> int:
    for p in PATTERNS.values():
        al = f" (aliases: {', '.join(p.aliases)})" if p.aliases else ""
        print(f"{p.name}{al} -- default rhythm {p.default_rhythm}\n  {p.about}")
        try:
            print(f"  N={a.n}: {p.notation(a.n)}\n")
        except ValueError as e:
            print(f"  {e}\n")
    print(f"rhythms: {', '.join(DURS)}  (8t = triplet eighth, 16s = sextuplet sixteenth)")
    print("section options (after the rhythm): stop=N -- the descent ends at group N, then lands on note 0; "
          "skip=N[+N...] -- the descent leaves those groups out. Group N = the group built on box note N.")
    print(f"  {SPEC_FORM}, e.g. 3s:8t:stop=3 or thirds:16:skip=2+5")
    return 0


def cmd_generate(a) -> int:
    box = get_box(a.box, key=a.key, fret_offset=a.fret_offset)
    sections = resolve_sections(a.patterns.split(","))
    rep = generate(box, a.out, sections=sections, bend_blue=a.bend_blue_notes, one_pick_bends=a.one_pick_bends,
                   tempo=a.tempo, title=a.title, subtitle=a.subtitle or "",
                   marker_fmt="{label}" if a.plain_markers else "{label} ({shape})",
                   fingering=a.fingering, alphatab=not a.no_alphatab, render=not a.no_render,
                   force=a.force, expect_reads=a.expect_reads, expect_gp5=a.expect_gp5)
    if a.json:
        print(json.dumps({k: v for k, v in rep.items() if k != "plan"}, indent=1))
        return 0
    print(f"OK {rep['out']}\n  {rep['label']} ({rep['key']}), {rep['bars']} bars, {rep['notes']} notes, "
          f"{rep['picks']} picks, {rep['bends']} half-step bends"
          + (f" ({rep['releases']} released)" if rep["releases"] else ""))
    for s in rep["sections"]:
        print(f"  {s['label']}: {s['pattern']} in {s['rhythm']}, {s['bars']} bars, {s['notes']} notes")
    for k, v in rep["checks"].items():
        print(f"  check {k}: {v}")
    return 0


def cmd_analyze(a) -> int:
    box = get_box(a.box, key=a.key, fret_offset=a.fret_offset)
    tab = json.load(open(Path(a.reads) / "tab_read.json"))
    idx = box.index_of_sf()
    for key, sec in tab.items():
        notes = [tuple(n) for b in sec["bars"] for n in b["notes"]]
        missing = [n for n in notes if n not in idx]
        if missing:
            print(f"{key}: {len(missing)} notes outside the {box.label}: {missing[:5]}")
            continue
        s = [idx[n] for n in notes]
        hits = []
        for p in PATTERNS.values():
            try:
                if p.stream(box.n) == s:
                    hits.append(p.name)
            except ValueError:
                pass
        print(f"{key}: {len(s)} notes; matches: {', '.join(hits) or 'NONE'}\n  {s}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scaleseq", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("boxes")
    b.add_argument("--key")
    p = sub.add_parser("patterns")
    p.add_argument("--n", type=int, default=14, help="box size for the index-notation examples")
    pattern_file_help = "JSON file of extra patterns (the user's own, outside this skill), for this run only"
    p.add_argument("--pattern-file", help=pattern_file_help)
    for name in ("generate", "analyze"):
        g = sub.add_parser(name)
        g.add_argument("--box", required=True, help=f"one of {', '.join(BOX_SPECS)} (or {'/'.join(BOX_ALIASES)})")
        g.add_argument("--key", help="transpose to this root (lowest placement without open strings)")
        g.add_argument("--fret-offset", type=int, help="explicit transposition in frets (wins over --key)")
        g.add_argument("--pattern-file", help=pattern_file_help)
        if name == "analyze":
            g.add_argument("--reads", required=True, help="dir with tab_read.json (flat section layout)")
            continue
        g.add_argument("-o", "--out", required=True)
        g.add_argument("--patterns", required=True,
                       help=f"comma list of {SPEC_FORM}, one section each in this order, e.g. "
                            "4s,3s:8t,thirds:16:stop=3 (stop=N: the descent ends at group N, then lands on "
                            "note 0; skip=N[+N...]: the descent leaves those groups out)")
        bends = g.add_mutually_exclusive_group()
        bends.add_argument("--bend-blue-notes", action="store_true",
                           help="play every blue note (b5) as a half-step bend from the fret below, each picked")
        bends.add_argument("--one-pick-bends", action="store_true",
                           help="half-step bends with one pick per bend: up = pick, tied bend into the next "
                                "note; down = picked pre-bend, tied release (e.g. the plain scale)")
        g.add_argument("--tempo", type=int, default=80)
        g.add_argument("--title")
        g.add_argument("--subtitle")
        g.add_argument("--plain-markers", action="store_true", help="markers without the shape name")
        g.add_argument("--fingering", action="store_true", help="write the box's suggested left-hand fingers")
        g.add_argument("--no-alphatab", action="store_true", help="skip the alphaTab checks (not recommended)")
        g.add_argument("--no-render", action="store_true", help="skip the alphaTab render check")
        g.add_argument("--force", action="store_true", help="replace an existing output file")
        g.add_argument("--json", action="store_true")
        g.add_argument("--expect-reads", help="fail unless note-for-note equal to these reads")
        g.add_argument("--expect-gp5", help="fail unless equal to this .gp5 (the notes the run bends excepted)")
    a = ap.parse_args(argv)
    try:
        if getattr(a, "pattern_file", None):
            load_pattern_file(a.pattern_file)
        return {"boxes": cmd_boxes, "patterns": cmd_patterns, "generate": cmd_generate,
                "analyze": cmd_analyze}[a.cmd](a)
    except (BoxError, CheckFailed, OSError, ValueError, KeyError, RuntimeError) as e:
        # str(KeyError) is the repr of its argument; print the message itself, quoted once
        msg = e.args[0] if isinstance(e, KeyError) and len(e.args) == 1 else e
        print(f"FAILED: {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
