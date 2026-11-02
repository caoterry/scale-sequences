# SPDX-License-Identifier: MIT
import pytest

from scaleseq import boxes
from scaleseq.boxes import BoxError, get_box
from scaleseq.theory import note_name, scale_pcs


BUILT_IN = [
    ("b7", 14, (6, 3), [(5, 5), (2, 3)]),
    ("root", 14, (6, 5), [(5, 5), (3, 7)]),
    ("b3", 15, (6, 8), [(6, 10), (3, 7), (1, 10)]),
    ("4", 15, (6, 10), [(6, 10), (4, 12), (1, 10)]),
    ("5", 14, (6, 12), [(4, 12), (2, 15)]),
]


def test_every_built_in_box_is_tested():
    assert sorted(boxes.ALIASES[bid] for bid, *_ in BUILT_IN) == sorted(boxes.BOX_SPECS)


@pytest.mark.parametrize("bid,n,lowest,blue_sources", BUILT_IN)
def test_builtin_boxes_are_gap_free_scale_runs(bid, n, lowest, blue_sources):
    box = get_box(bid)
    assert box.n == n
    assert box.positions[0].sf == lowest
    pcs = scale_pcs("minor-blues", 9)
    assert {p.pitch % 12 for p in box.positions} == pcs == {9, 0, 2, 3, 4, 7}
    names = [note_name(p.pitch) for p in box.positions]
    cycle = ["A", "C", "D", "D#", "E", "G"]
    start = cycle.index(names[0])
    assert names == [cycle[(start + k) % 6] for k in range(n)]  # consecutive scale degrees
    assert all(b.pitch > a.pitch for a, b in zip(box.positions, box.positions[1:]))
    assert [box.bend_source(i).sf for i in box.blue_indices()] == blue_sources


def test_suggested_fingering_kept():
    box = get_box("b3")
    assert {p.sf: p.finger for p in box.positions}[(3, 8)] == 2
    assert {p.sf: p.finger for p in box.positions}[(1, 11)] == 4


def test_transpose_by_key_and_offset():
    c = get_box("root", key="C")
    assert c.fret_offset == 3 and c.positions[0].sf == (6, 8) and note_name(c.positions[0].pitch) == "C"
    assert {p.pitch % 12 for p in c.positions} == scale_pcs("minor-blues", 0)
    e = get_box("root", key="E")          # -5 would need open strings -> goes up to fret 12
    assert e.fret_offset == 7 and e.fret_span() == (12, 15)
    assert get_box("root", fret_offset=-5).fret_span() == (0, 3)


@pytest.mark.parametrize("frets,msg", [
    ({6: [(5, 1), (7, 3)], 5: [(5, 1)]}, "not in"),                      # B is not in A minor blues
    ({6: [(5, 1)], 5: [(5, 1)]}, "gap"),                                 # A then D skips C
    ({6: [(5, 1), (8, 3), (10, 4)], 5: [(5, 1)]}, "duplicate"),          # D twice
    ({6: [(5, 3), (8, 1)]}, "fingers do not ascend"),
])
def test_bad_boxes_are_refused(monkeypatch, frets, msg):
    monkeypatch.setitem(boxes.BOX_SPECS, "bad", {"label": "bad", "key": "A", "scale": "minor-blues",
                                                 "frets": frets})
    with pytest.raises(BoxError, match=msg):
        get_box("bad")


def test_bend_needs_fret_below(monkeypatch):
    monkeypatch.setitem(boxes.BOX_SPECS, "nob", {"label": "nob", "key": "A", "scale": "minor-blues",
                                                 "frets": {5: [(5, 1), (7, 3)], 4: [(1, 1)]}})
    box = get_box("nob")  # D(5/5) E(5/7) D#(4/1): D# has no fret-below on its string
    with pytest.raises(BoxError, match="no box note one fret below"):
        box.bend_source(box.blue_indices()[0])
