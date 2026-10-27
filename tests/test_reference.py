# SPDX-License-Identifier: MIT
"""Checks against a reference (--expect-reads, --expect-gp5, analyze) on hand-written synthetic reads.

The reads below are written out by hand from the pattern definitions on the 6-note mini box
(index -> string/fret: 0=6/5 A, 1=6/8 C, 2=5/5 D, 3=5/6 D#, 4=5/7 E, 5=4/5 G), not produced by the code.
"""
import json

import pytest

import scaleseq_cli
from conftest import alphatab_available
from scaleseq.exercise import Section
from scaleseq.pipeline import CheckFailed, generate

S = {0: (6, 5), 1: (6, 8), 2: (5, 5), 3: (5, 6), 4: (5, 7), 5: (4, 5)}


def sf(*idx):
    return [list(S[i]) for i in idx]


# neighbor3 in triplet eighths: pickup [0] (its own 1/8 bar), [1,0,1]..[5,4,5] up, [4,3,4]..[1,0,1] down,
# landing quarter [0] on the next beat, half rest.
NEIGHBOR3_TAB = [
    sf(0),
    sf(1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4),
    sf(5, 4, 5, 4, 3, 4, 3, 2, 3, 2, 1, 2),
    sf(1, 0, 1, 0),
]
T8 = {"dur": 8, "triplet": True}
NEIGHBOR3_STAFF = [[{"dur": 8}], [T8] * 12, [T8] * 12, [T8] * 3 + [{"dur": 4}, {"dur": 2, "rest": True}]]
# 4s in straight eighths: [0123][1234][2345] up, [5432][4321][3210] down, three full bars.
FOURS_TAB = [sf(0, 1, 2, 3, 1, 2, 3, 4), sf(2, 3, 4, 5, 5, 4, 3, 2), sf(4, 3, 2, 1, 3, 2, 1, 0)]
FOURS_STAFF = [[{"dur": 8}] * 8] * 3

SECTIONS = [Section("neighbor3", "neighbor3", note="8t"), Section("4s", "4s", note="8")]


def write_reads(d, tab=None, staff=None):
    tab = tab or {"neighbor3": NEIGHBOR3_TAB, "4s": FOURS_TAB}
    staff = staff or {"neighbor3": NEIGHBOR3_STAFF, "4s": FOURS_STAFF}
    d.mkdir(exist_ok=True)
    (d / "tab_read.json").write_text(json.dumps({k: {"bars": [{"notes": b} for b in v]} for k, v in tab.items()}))
    (d / "staff_read.json").write_text(json.dumps({k: {"bars": [{"events": b} for b in v]} for k, v in staff.items()}))
    return str(d)


def test_expect_reads_passes_on_the_hand_written_reads(mini_box, tmp_path):
    reads = write_reads(tmp_path / "reads")
    rep = generate(mini_box, str(tmp_path / "ok.gp5"), sections=SECTIONS, expect_reads=reads,
                   alphatab=alphatab_available())
    assert rep["checks"]["note-for-note vs reference reads"] == "ok"
    assert rep["bars"] == 4 + 3 and rep["notes"] == 1 + 24 + 4 + 24


@pytest.mark.parametrize("tamper,msg", [("fret", "4s bar 2: notes .* vs tab read"),
                                        ("rhythm", "neighbor3 bar 4: rhythm .* vs staff read"),
                                        ("bar", "4s: bars plan 3 tab 2 staff 2")])
def test_expect_reads_catches_a_difference(mini_box, tmp_path, tamper, msg):
    tab = {"neighbor3": [list(b) for b in NEIGHBOR3_TAB], "4s": [list(b) for b in FOURS_TAB]}
    staff = {"neighbor3": [list(b) for b in NEIGHBOR3_STAFF], "4s": [list(b) for b in FOURS_STAFF]}
    if tamper == "fret":
        tab["4s"][1] = tab["4s"][1][:-1] + [[5, 7]]
    elif tamper == "rhythm":
        staff["neighbor3"][3] = [T8] * 3 + [{"dur": 4}, {"dur": 4, "rest": True}, {"dur": 4, "rest": True}]
    else:
        tab["4s"] = tab["4s"][:2]
        staff["4s"] = staff["4s"][:2]
    reads = write_reads(tmp_path / "reads", tab, staff)
    out = tmp_path / "bad.gp5"
    with pytest.raises(CheckFailed, match=msg):
        generate(mini_box, str(out), sections=SECTIONS, expect_reads=reads, alphatab=False)
    assert not out.exists()


def test_expect_reads_refuses_bends(mini_box, tmp_path):
    reads = write_reads(tmp_path / "reads")
    with pytest.raises(CheckFailed, match="plan has bends"):
        generate(mini_box, str(tmp_path / "b.gp5"), sections=SECTIONS, expect_reads=reads, bend_blue=True,
                 alphatab=False)


def test_expect_gp5_allows_only_bent_blue_notes(mini_box, tmp_path):
    ref = tmp_path / "ref.gp5"
    generate(mini_box, str(ref), sections=SECTIONS, title="t", alphatab=False)
    rep = generate(mini_box, str(tmp_path / "bent.gp5"), sections=SECTIONS, title="t", bend_blue=True,
                   expect_gp5=str(ref), alphatab=alphatab_available())
    assert rep["bends"] > 0
    assert rep["checks"]["vs reference .gp5 (only bends may differ)"] == "ok"
    out = tmp_path / "other.gp5"
    with pytest.raises(CheckFailed, match="differs from reference"):
        generate(mini_box, str(out), sections=[SECTIONS[0], Section("4s", "3s", note="8")], title="t",
                 expect_gp5=str(ref), alphatab=False)
    assert not out.exists()


def test_analyze_names_the_matching_patterns(mini_box, tmp_path, capsys):
    reads = write_reads(tmp_path / "reads")
    assert scaleseq_cli.main(["analyze", "--box", "mini", "--reads", reads]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "matches" in ln]
    assert lines == ["neighbor3: 29 notes; matches: neighbor3", "4s: 24 notes; matches: 4s"]


def test_expect_reads_keeps_sections_with_one_label_apart(mini_box, tmp_path):
    """Two sections of the same pattern and label are compared with their own reads, in order."""
    secs = [Section("4s", "4s", note="8"), Section("4s", "4s", note="8")]
    reads = write_reads(tmp_path / "reads", {"first": FOURS_TAB, "second": FOURS_TAB},
                        {"first": FOURS_STAFF, "second": FOURS_STAFF})
    rep = generate(mini_box, str(tmp_path / "twice.gp5"), sections=secs, expect_reads=reads, alphatab=False)
    assert rep["checks"]["note-for-note vs reference reads"] == "ok"
    assert [(s["bars"], s["notes"]) for s in rep["sections"]] == [(3, 24), (3, 24)]
    short = [list(b) for b in FOURS_TAB[:2]]
    reads = write_reads(tmp_path / "reads2", {"first": FOURS_TAB, "second": short},
                        {"first": FOURS_STAFF, "second": FOURS_STAFF[:2]})
    with pytest.raises(CheckFailed, match="second: bars plan 3 tab 2 staff 2"):
        generate(mini_box, str(tmp_path / "bad.gp5"), sections=secs, expect_reads=reads, alphatab=False)
