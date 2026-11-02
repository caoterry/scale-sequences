# SPDX-License-Identifier: MIT
import math
from fractions import Fraction

import pytest

from scaleseq.boxes import get_box
from scaleseq.exercise import DURS, Section, build_bars, realize, rest_fill
from scaleseq.patterns import PATTERNS
from scaleseq.verify import check_plan


@pytest.mark.parametrize("pos,unit,want", [
    (Fraction(2), "8", ["2"]),
    (Fraction(3), "8", ["4"]),
    (Fraction(1), "8", ["4", "2"]),
    (Fraction(0), "8", ["1"]),
    (Fraction(5, 2), "8", ["8", "4"]),
    (Fraction(4, 3), "8t", ["8t", "8t", "2"]),
    (Fraction(7, 4), "16", ["16", "2"]),
])
def test_rest_fill(pos, unit, want):
    got = rest_fill(pos, Fraction(4), DURS[unit])
    assert [d.key for d in got] == want
    assert pos + sum(d.beats for d in got) == 4


@pytest.mark.parametrize("box_id", ["b7", "root", "b3", "4", "5"])
@pytest.mark.parametrize("name", list(PATTERNS))
@pytest.mark.parametrize("rhythm", ["8", "8t", "16", "16s"])
@pytest.mark.parametrize("bend", [False, True])
def test_every_combination_passes_plan_checks(box_id, name, rhythm, bend):
    box = get_box(box_id)
    secs = [Section(name, name, note=rhythm)]
    plan = realize(build_bars(secs, box.n), box, bend_blue=bend)
    assert check_plan(plan, box, secs, bend_blue=bend) == []


def _bars_by_arithmetic(sec, n: int) -> int:
    """Bars a section needs, from its index stream and rhythm alone: a pickup bar of its own, the line,
    then (if the line does not end on index 0) a landing quarter on the next beat."""
    parts = sec.pat().sections(n)
    line = sum(len(g) for k in ("up", "down") for g in parts[k])
    beats = line * sec.note_dur().beats
    if parts["land"]:
        beats = math.ceil(beats) + DURS[sec.land].beats
    return (1 if parts["pickup"] else 0) + math.ceil(beats / 4)


# One file of several sections (the CLI's --patterns neighbor3:16,thirds,4s:16,6s,upper-neighbor3).
MIXED = [Section("neighbor3", "neighbor3", note="16"), Section("thirds", "thirds", note="8"),
         Section("4s", "4s", note="16"), Section("6s", "6s", note="16s"),
         Section("upper-neighbor3", "upper-neighbor3", note="8t")]


# root/b7/5 boxes have 14 notes, b3/4 have 15. On 14 notes: neighbor3 in sixteenths = 1/8 pickup bar, then
# 13 groups up + 12 down = 75 sixteenths = 18.75 beats, landing quarter on beat 20 -> 1 + 5 bars;
# thirds in eighths: 12 + 12 pairs = 48 eighths = 6 bars; 4s in sixteenths: 11 + 11 groups = 88
# sixteenths = 22 beats -> 6 bars; 6s in sextuplets: 9 + 9 groups = 108 x 1/6 beat = 18 beats -> 5 bars;
# upper-neighbor3 in triplet eighths: 13 + 12 groups = 75 x 1/3 beat = 25 beats -> 7 bars.
@pytest.mark.parametrize("bid,counts", [("root", [6, 6, 6, 5, 7]), ("b7", [6, 6, 6, 5, 7]),
                                        ("b3", [7, 7, 6, 5, 7]), ("4", [7, 7, 6, 5, 7]),
                                        ("5", [6, 6, 6, 5, 7])])
def test_multi_section_bar_counts(bid, counts):
    box = get_box(bid)
    bars = build_bars(MIXED, box.n)
    got = [sum(1 for b in bars if b.section == s.label) for s in MIXED]
    assert got == counts == [_bars_by_arithmetic(s, box.n) for s in MIXED]
    assert bars[0].ts == (1, 8) and all(b.ts == (4, 4) for b in bars[1:])


@pytest.mark.parametrize("pickup,ts", [("8", (1, 8)), ("16", (1, 16)), ("4", (2, 8))])
def test_pickup_bar_time_signature(pickup, ts):
    bars = build_bars([Section("n", "neighbor3", pickup=pickup)], 14)
    assert bars[0].ts == ts and [e.idx for e in bars[0].events] == [0]


@pytest.mark.parametrize("name", list(PATTERNS))
@pytest.mark.parametrize("rhythm", ["8", "8t", "16", "16s"])
@pytest.mark.parametrize("n", [14, 15])
def test_bar_count_matches_arithmetic(name, rhythm, n):
    sec = Section(name, name, note=rhythm)
    assert len(build_bars([sec], n)) == _bars_by_arithmetic(sec, n)


def _tamper(plan, **kw):
    import copy
    p = copy.deepcopy(plan)
    beat = next(b for b in p[1]["beats"] if not b["rest"])
    beat.update(kw)
    return p


def test_plan_check_catches_errors():
    box = get_box("root")
    secs = MIXED
    plan = realize(build_bars(secs, box.n), box)
    assert check_plan(plan, box, secs, bend_blue=False) == []
    assert any("not a position" in x or "sounds" in x for x in check_plan(_tamper(plan, fret=9), box, secs, bend_blue=False))
    assert any("index stream" in x for x in check_plan(_tamper(plan, idx=4, string=5, fret=7, pitch=52), box, secs, bend_blue=False))
    assert any("beats sum" in x for x in check_plan(_tamper(plan, value=4), box, secs, bend_blue=False))
    bent = realize(build_bars(secs, box.n), box, bend_blue=True)
    assert check_plan(bent, box, secs, bend_blue=True) == []
    assert any("bend" in x for x in check_plan(bent, box, secs, bend_blue=False))
