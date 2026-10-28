# SPDX-License-Identifier: MIT
"""End-to-end: generate -> .gp5 -> read back, including a hand-written known exercise."""

import guitarpro as gp
import pytest

from conftest import alphatab_available
from scaleseq.boxes import get_box
from scaleseq.exercise import Section, build_bars, realize
from scaleseq.gp5 import read_plan_shape, write_gp5
from scaleseq.pipeline import CheckFailed, generate, resolve_sections
from scaleseq.verify import check_alphatab, check_readback

# 4s on the mini box (A C D D# E G), straight eighths, written out by hand as (string, fret):
# up [0123][1234][2345], down [5432][4321][3210] -> 24 eighths = 3 full bars, no rests.
KNOWN_4S_MINI = [
    [(6, 5), (6, 8), (5, 5), (5, 6), (6, 8), (5, 5), (5, 6), (5, 7)],
    [(5, 5), (5, 6), (5, 7), (4, 5), (4, 5), (5, 7), (5, 6), (5, 5)],
    [(5, 7), (5, 6), (5, 5), (6, 8), (5, 6), (5, 5), (6, 8), (6, 5)],
]


def _no_at():
    return not alphatab_available()


def test_regenerates_known_exercise_exactly(mini_box, tmp_path):
    out = tmp_path / "mini4s.gp5"
    rep = generate(mini_box, str(out), sections=[Section("4s", "4s", note="8")], title="mini 4s",
                   alphatab=alphatab_available())
    song = read_plan_shape(str(out))
    assert [b["ts"] for b in song["bars"]] == [[4, 4]] * 3
    got = [[(n["string"], n["fret"]) for x in b["beats"] for n in x["notes"]] for b in song["bars"]]
    assert got == KNOWN_4S_MINI
    assert all((x["value"], x["tuplet"], x["rest"]) == (8, [1, 1], False) for b in song["bars"] for x in b["beats"])
    assert rep["notes"] == 24 and rep["bars"] == 3


def test_bend_blue_notes_on_known_exercise(mini_box, tmp_path):
    out = tmp_path / "mini4s_bend.gp5"
    generate(mini_box, str(out), sections=[Section("4s", "4s", note="8")], title="mini 4s bends",
             bend_blue=True, alphatab=alphatab_available())
    song = gp.parse(str(out))
    want = [[(s, f - 1 if (s, f) == (5, 6) else f, (s, f) == (5, 6)) for s, f in bar] for bar in KNOWN_4S_MINI]
    got = []
    for meas in song.tracks[0].measures:
        row = []
        for beat in meas.voices[0].beats:
            for n in beat.notes:
                bend = n.effect.bend
                if bend:  # up a half step within 2/12 of the note, then held (4 points, middles differ)
                    assert bend.type == gp.BendType.bend
                    assert [(p.position, p.value) for p in bend.points] == [(0, 0), (1, 0), (2, 2), (12, 2)]
                row.append((n.string, n.value, bend is not None))
        got.append(row)
    assert got == want


def test_readback_check_catches_a_wrong_file(tmp_path):
    box = get_box("b7")
    secs = [Section("neighbor3", "neighbor3", note="16"), Section("4s", "4s", note="8")]
    plan = realize(build_bars(secs, box.n), box)
    path = tmp_path / "x.gp5"
    write_gp5(plan, str(path), title="t")
    assert check_readback(str(path), plan, title="t", tempo=80, fingering=False) == []
    plan[3]["beats"][2]["fret"] += 1
    assert check_readback(str(path), plan, title="t", tempo=80, fingering=False)


@pytest.mark.skipif(_no_at(), reason="node / alphaTab not available")
def test_alphatab_check_catches_a_wrong_plan(tmp_path):
    box = get_box("root")
    secs = [Section("1231", "1231", note="16")]
    plan = realize(build_bars(secs, box.n), box, bend_blue=True)
    path = tmp_path / "x.gp5"
    write_gp5(plan, str(path), title="t")
    probs, dump = check_alphatab(str(path), plan, title="t", tempo=80)
    assert probs == []
    n_bent = sum(1 for b in plan for x in b["beats"] if not x["rest"] and x["bend"])
    assert n_bent > 0 and len(dump["render"]["bendLabels"]) == n_bent
    plan[2]["beats"][0]["pitch"] += 1
    assert check_alphatab(str(path), plan, title="t", tempo=80, render=False)[0]


def test_no_overwrite_and_no_file_on_failure(tmp_path, monkeypatch):
    out = tmp_path / "a.gp5"
    out.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        generate("root", str(out), sections=[Section("3s", "3s")], alphatab=False)
    assert out.read_bytes() == b"keep"
    import scaleseq.pipeline as pl
    monkeypatch.setattr(pl, "check_readback", lambda *a, **k: ["forced failure"])
    out2 = tmp_path / "b.gp5"
    with pytest.raises(CheckFailed):
        generate("root", str(out2), sections=[Section("3s", "3s")], alphatab=False)
    assert not out2.exists() and not list(tmp_path.glob("*.tmp.gp5"))


def test_pattern_specs():
    assert [(s.label, s.pattern, s.note_dur().key) for s in resolve_sections(["1234", " 3s:16", "6s"])] == [
        ("4s", "4s", "8"), ("3s", "3s", "16"), ("6s", "6s", "16s")]
    with pytest.raises(ValueError):
        resolve_sections([])
    with pytest.raises(KeyError):
        resolve_sections(["5s"])


def test_another_scale_box_end_to_end(monkeypatch, tmp_path):
    """A box of another scale (A minor pentatonic, 12 notes) goes through the same pipeline; it has no
    blue note, so --bend-blue-notes bends nothing."""
    from scaleseq import boxes
    monkeypatch.setitem(boxes.BOX_SPECS, "pent", {
        "label": "pentatonic box", "key": "A", "scale": "minor-pentatonic",
        "frets": {6: [(5, 1), (8, 4)], 5: [(5, 1), (7, 3)], 4: [(5, 1), (7, 3)], 3: [(5, 1), (7, 3)],
                  2: [(5, 1), (8, 4)], 1: [(5, 1), (8, 4)]},
    })
    out = tmp_path / "pent.gp5"
    rep = generate(boxes.get_box("pent", key="G"), str(out), sections=[Section("4s", "4s", note="8")],
                   bend_blue=True, alphatab=alphatab_available())
    assert rep["bends"] == 0 and rep["key"] == "G" and rep["n_box_notes"] == 12
    first = [(n["string"], n["fret"]) for x in read_plan_shape(str(out))["bars"][0]["beats"] for n in x["notes"]]
    # [0,1,2,3] [1,2,3,4] two frets lower (G): G Bb C D, Bb C D F
    assert first == [(6, 3), (6, 6), (5, 3), (5, 5), (6, 6), (5, 3), (5, 5), (4, 3)]
