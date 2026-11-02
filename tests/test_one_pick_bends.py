# SPDX-License-Identifier: MIT
"""One pick per bend (--one-pick-bends): up = pick the lower note, a TIED note bends it up into the next
scale note; down = a picked PRE-BEND sounds the upper note, a TIED note releases it into the next one.

The expected notes below are written out by hand, beat by beat, for the plain scale (one quarter per
note) on each built-in box. Notation: "string/fret", "^" = tied note bent up a half step, "pb" = picked
pre-bend (sounds a half step above the fret), "v" = tied release back to the fret's own pitch.
"""
import copy

import guitarpro as gp
import pytest

import scaleseq_cli
from conftest import alphatab_available
from scaleseq import boxes
from scaleseq.boxes import BoxError, get_box
from scaleseq.exercise import Section, build_bars, realize
from scaleseq.gp5 import read_plan_shape, write_gp5
from scaleseq.patterns import PATTERNS
from scaleseq.pipeline import CheckFailed, generate
from scaleseq.theory import STANDARD_TUNING, note_name
from scaleseq.verify import check_midi, check_plan, check_readback

SCALE = [Section("scale", "scale", note="4")]

ONE_PICK_SCALE = {
    "root": "6/5 6/8 5/5 5/6 5/6^ 4/5 4/7 3/5 3/7 3/7^ 2/5 2/8 1/5 1/8 "
            "1/5 2/8 2/5 3/7pb 3/7v 3/5 4/7 4/5 5/6pb 5/6v 5/5 6/8 6/5",
    "b7": "6/3 6/5 5/3 5/5 5/5^ 4/2 4/5 3/2 3/5 2/3 2/4 2/4^ 1/3 1/5 "
          "1/3 2/4pb 2/4v 2/3 3/5 3/2 4/5 4/2 5/5pb 5/5v 5/3 6/5 6/3",
    "b3": "6/8 6/10 6/10^ 5/7 5/10 4/7 4/10 3/7 3/8 3/8^ 2/8 2/10 1/8 1/10 1/10^ "
          "1/10v 1/8 2/10 2/8 3/8pb 3/8v 3/7 4/10 4/7 5/10 5/7 6/10pb 6/10v 6/8",
    "4": "6/10 6/11 6/11^ 5/10 5/12 4/10 4/12 4/12^ 3/9 3/12 2/10 2/13 1/10 1/11 1/11^ "
         "1/11v 1/10 2/13 2/10 3/12 3/9 4/12pb 4/12v 4/10 5/12 5/10 6/11pb 6/11v 6/10",
    "5": "6/12 6/15 5/12 5/15 4/12 4/13 4/13^ 3/12 3/14 2/13 2/15 2/15^ 1/12 1/15 "
         "1/12 2/15pb 2/15v 2/13 3/14 3/12 4/13pb 4/13v 4/12 5/15 5/12 6/15 6/12",
}
KIND = {"": (False, None), "^": (True, "bend"), "pb": (False, "prebend"), "v": (True, "release")}

# the file encoding of each kind: (GP note type, GP bend type, points as (position 0-12, quarter tones))
FILE = {"bend": ("tie", "bend", [(0, 0), (1, 0), (2, 2), (12, 2)]),
        "prebend": ("normal", "prebend", [(0, 2), (12, 2)]),
        "release": ("tie", "prebendRelease", [(0, 2), (1, 2), (2, 0), (12, 0)])}


def parse(spec: str) -> list[tuple]:
    out = []
    for tok in spec.split():
        s, rest = tok.split("/")
        f = rest.rstrip("^pbv")
        out.append((int(s), int(f), *KIND[rest[len(f):]]))
    return out


def notes(plan) -> list[dict]:
    return [b for bar in plan for b in bar["beats"] if not b["rest"]]


def one_pick_plan(box, sections=SCALE):
    return realize(build_bars(sections, box.n), box, one_pick_bends=True)


def ends_at(b) -> int:
    """Sounding pitch at the end of the beat, from the hand notation's meaning of each kind."""
    return STANDARD_TUNING[b["string"]] + b["fret"] + (1 if b["bend_kind"] in ("bend", "prebend") else 0)


# ---------- which pair of notes is bent, from the box's fingering ----------

@pytest.mark.parametrize("bid,pairs", [
    ("root", [(5, 6, 2, "D#", "E"), (3, 7, 3, "D", "D#")]),
    ("b7", [(5, 5, 3, "D", "D#"), (2, 4, 2, "D#", "E")]),
    ("b3", [(6, 10, 3, "D", "D#"), (3, 8, 2, "D#", "E"), (1, 10, 3, "D", "D#")]),
    ("4", [(6, 11, 2, "D#", "E"), (4, 12, 3, "D", "D#"), (1, 11, 2, "D#", "E")]),
    ("5", [(4, 13, 2, "D#", "E"), (2, 15, 3, "D", "D#")]),
])
def test_bend_pairs_follow_the_box_fingering(bid, pairs):
    """D-D#-E on one string (fingers 1-2-3): the middle finger bends D# up to E. Otherwise the ring finger
    bends D up to D#."""
    box = get_box(bid)
    got = [(p.string, p.fret, p.finger, note_name(box.positions[p.lower].pitch),
            note_name(box.positions[p.upper].pitch)) for p in box.bend_pairs()]
    assert got == pairs
    for p in box.bend_pairs():
        assert p.upper == p.lower + 1 and box.positions[p.lower].sf == (p.string, p.fret)


def test_bend_pairs_transpose_with_the_box():
    pairs = get_box("root", key="C").bend_pairs()
    assert [(p.string, p.fret, p.finger) for p in pairs] == [(5, 9, 2), (3, 10, 3)]


def test_a_bend_with_the_index_finger_is_refused(monkeypatch):
    # D (finger 1) and D# (finger 2) on string 5, E on string 4: the bend would be the index finger's
    monkeypatch.setitem(boxes.BOX_SPECS, "idx", {"label": "idx", "key": "A", "scale": "minor-blues",
                                                 "frets": {6: [(5, 1), (8, 4)], 5: [(5, 1), (6, 2)],
                                                           4: [(2, 1), (5, 4)]}})
    with pytest.raises(BoxError, match="index finger"):
        get_box("idx").bend_pairs()


def test_a_bend_pair_needs_the_fret_below(monkeypatch):
    monkeypatch.setitem(boxes.BOX_SPECS, "nob", {"label": "nob", "key": "A", "scale": "minor-blues",
                                                 "frets": {5: [(5, 1), (7, 3)], 4: [(1, 1)]}})
    with pytest.raises(BoxError, match="no box note one fret below"):
        get_box("nob").bend_pairs()


# ---------- the plan ----------

@pytest.mark.parametrize("bid", list(ONE_PICK_SCALE))
def test_one_pick_scale_is_the_hand_written_exercise(bid):
    box = get_box(bid)
    plan = one_pick_plan(box)
    got = [(b["string"], b["fret"], b["tie"], b["bend_kind"]) for b in notes(plan)]
    assert got == parse(ONE_PICK_SCALE[bid])
    up = [p.pitch for p in box.positions]
    assert [ends_at(b) for b in notes(plan)] == [b["pitch"] for b in notes(plan)] == up + up[-2::-1]
    assert all(b["dur"] == "4" for b in notes(plan))  # every scale note keeps its own beat
    assert check_plan(plan, box, SCALE, one_pick_bends=True) == []


def test_one_pick_on_the_mini_box(mini_box):
    """A C D D# E G; string 5 holds D-D#-E (fingers 1-2-3), so D# is bent up to E and E's fret 7 is never
    played."""
    plan = one_pick_plan(mini_box)
    got = [(b["string"], b["fret"], b["tie"], b["bend_kind"]) for b in notes(plan)]
    assert got == parse("6/5 6/8 5/5 5/6 5/6^ 4/5 5/6pb 5/6v 5/5 6/8 6/5")


def test_the_bent_to_notes_own_fret_is_never_played():
    for bid in ONE_PICK_SCALE:
        box = get_box(bid)
        own = {box.positions[p.upper].sf for p in box.bend_pairs()}
        assert not own & {(b["string"], b["fret"]) for b in notes(one_pick_plan(box))}


def test_one_pick_needs_a_bent_to_note_next_to_the_note_it_bends_from():
    """In 3s on the root box, E (bent to from D#) also follows G, with no D# beside it."""
    with pytest.raises(ValueError, match="one pick per bend"):
        one_pick_plan(get_box("root"), [Section("3s", "3s")])


@pytest.mark.parametrize("bid", ["b7", "root", "b3", "4", "5"])
@pytest.mark.parametrize("name", list(PATTERNS))
def test_every_pattern_is_either_planned_and_checked_or_refused(bid, name):
    box = get_box(bid)
    secs = [Section(name, name)]
    try:
        plan = one_pick_plan(box, secs)
    except ValueError as e:
        assert name != "scale" and "one pick per bend" in str(e)
        return
    assert check_plan(plan, box, secs, one_pick_bends=True) == []
    for a, b in zip(notes(plan), notes(plan)[1:]):  # a tie continues the note before it
        if b["tie"]:
            assert (a["string"], a["fret"]) == (b["string"], b["fret"])


def test_one_pick_and_blue_note_bends_are_exclusive():
    box = get_box("root")
    with pytest.raises(ValueError, match="one of"):
        realize(build_bars(SCALE, box.n), box, bend_blue=True, one_pick_bends=True)


def _retouch(plan, k, **kw):
    p = copy.deepcopy(plan)
    notes(p)[k].update(kw)
    return p


@pytest.mark.parametrize("k,change,msg", [
    (4, dict(tie=False), "picked again"),                                   # bend, then pick again
    (4, dict(string=5, fret=7, tie=False, bend_kind=None, bend=0), "own fret"),  # E on its own fret
    (18, dict(tie=False, bend_kind=None, bend=0), "pre-bend"),                # pre-bend never released
    (5, dict(tie=True), "tie"),                                             # tied to another fret
    (4, dict(bend_kind="prebend", tie=False), "picked again"),              # re-picks the held bend
    (0, dict(tie=True), "a tie to no note"),                                # tie at the section's start
    (0, dict(bend_kind="bend", bend=2, pitch=46), "not the fret of a bend pair"),
    (16, dict(string=3, fret=5, idx=7, pitch=60), "same string"),           # C on s3 right before the pre-bend
    (4, dict(finger=1), "finger"),                                          # bent with the index finger
])
def test_the_plan_check_catches_one_pick_errors(k, change, msg):
    box = get_box("root")
    plan = one_pick_plan(box)
    assert check_plan(plan, box, SCALE, one_pick_bends=True) == []
    probs = check_plan(_retouch(plan, k, **change), box, SCALE, one_pick_bends=True)
    assert any(msg in p for p in probs), probs


# Patterns a user could define in a pattern file. On the b3 box, "asc" climbs to the top note D# (s1f10
# bent up from D) and stops; "pk13" starts with a pickup D on that same fret.
ASC_THEN_D = {"asc": {"shape": [0], "desc_stop": 14, "land": False}, "pk13": {"shape": [0], "pickup": [13]}}


def test_a_held_bend_is_not_picked_again_in_the_next_section(restore_library):
    from scaleseq.patterns import add_patterns
    add_patterns(ASC_THEN_D, source="test")
    box = get_box("b3")
    secs = [Section("asc", "asc", note="1"), Section("pk13", "pk13", note="4")]
    with pytest.raises(ValueError, match="bend held"):
        one_pick_plan(box, secs)
    # each section alone is fine; one after the other, the plan check catches the second pick of s1f10
    first, second = one_pick_plan(box, secs[:1]), one_pick_plan(box, secs[1:])
    for bar in second:
        bar["section_index"] = 1
    assert check_plan(first, box, secs[:1], one_pick_bends=True) == []
    assert any("bend held" in p for p in check_plan(first + second, box, secs, one_pick_bends=True))


def test_a_pre_bend_right_after_a_note_on_its_string_is_refused(restore_library):
    """D on s5f5, then E as a pre-bend on s5f6: that string is still sounding D, so it cannot be bent
    silently before the pick."""
    from scaleseq.patterns import add_patterns
    add_patterns({"pkx": {"shape": [0], "pickup": [2, 4, 3]}}, source="test")
    with pytest.raises(ValueError, match="same string"):
        one_pick_plan(get_box("root"), [Section("pkx", "pkx", note="4")])


def test_the_plan_check_wants_the_mode_the_plan_was_made_in():
    box = get_box("root")
    plan = one_pick_plan(box)
    assert check_plan(plan, box, SCALE, bend_blue=True)
    assert check_plan(plan, box, SCALE)


# ---------- the file ----------

@pytest.mark.parametrize("bid,picks,bends,releases", [("root", 23, 4, 2), ("b7", 23, 4, 2), ("b3", 23, 5, 3),
                                                      ("4", 23, 5, 3), ("5", 23, 4, 2)])
def test_one_pick_scale_file(bid, picks, bends, releases, tmp_path):
    out = tmp_path / f"{bid}.gp5"
    rep = generate(bid, str(out), sections=SCALE, one_pick_bends=True, alphatab=alphatab_available())
    assert all(v == "ok" for v in rep["checks"].values()), rep["checks"]
    assert (rep["picks"], rep["bends"], rep["releases"]) == (picks, bends, releases)
    want = parse(ONE_PICK_SCALE[bid])
    song = gp.parse(str(out))
    got = []
    for meas in song.tracks[0].measures:
        for beat in meas.voices[0].beats:
            for n in beat.notes:
                bend = n.effect.bend
                got.append((n.string, n.value, n.type.name,
                            (bend.type.name, [(p.position, p.value) for p in bend.points]) if bend else None))
    assert got == [(s, f, FILE[k][0] if k else "normal", (FILE[k][1], FILE[k][2]) if k else None)
                   for s, f, _, k in want]
    if alphatab_available():
        assert rep["render_bend_labels"] == bends


def test_readback_check_catches_a_wrong_tie_or_bend(tmp_path):
    box = get_box("root")
    plan = one_pick_plan(box)
    path = tmp_path / "x.gp5"
    write_gp5(plan, str(path), title="t")
    assert check_readback(str(path), plan, title="t", tempo=80, fingering=False) == []
    assert check_readback(str(path), _retouch(plan, 4, tie=False), title="t", tempo=80, fingering=False)
    assert check_readback(str(path), _retouch(plan, 18, bend_kind="bend"), title="t", tempo=80, fingering=False)


def test_expect_gp5_accepts_the_one_pick_version_of_a_plain_file(tmp_path):
    ref = tmp_path / "plain.gp5"
    generate("root", str(ref), sections=SCALE, title="t", alphatab=False)
    rep = generate("root", str(tmp_path / "bent.gp5"), sections=SCALE, title="t", one_pick_bends=True,
                   expect_gp5=str(ref), alphatab=False)
    assert rep["checks"]["vs reference .gp5 (only bends may differ)"] == "ok"
    with pytest.raises(CheckFailed, match="differs from reference"):
        generate("b7", str(tmp_path / "other.gp5"), sections=SCALE, title="t", one_pick_bends=True,
                 expect_gp5=str(ref), alphatab=False)


def test_expect_gp5_judges_the_bend_in_the_file_not_the_plan(tmp_path, monkeypatch):
    """A release written as a bend up ends a half step sharp: the file no longer sounds the reference."""
    from scaleseq import gp5
    from scaleseq.pipeline import check_against_reference_gp5
    box = get_box("root")
    ref, new = tmp_path / "plain.gp5", tmp_path / "bent.gp5"
    write_gp5(realize(build_bars(SCALE, box.n), box), str(ref), title="t")
    plan = one_pick_plan(box)
    write_gp5(plan, str(new), title="t")
    assert check_against_reference_gp5(str(new), str(ref), plan) == []
    monkeypatch.setitem(gp5.BEND_POINTS, "release", gp5.BEND_POINTS["bend"])
    write_gp5(plan, str(new), title="t")
    probs = check_against_reference_gp5(str(new), str(ref), plan)
    assert len(probs) == 2 and all("differs from reference" in p for p in probs), probs  # the two releases


# ---------- alphaTab: its parse, its MIDI ----------

@pytest.mark.skipif(not alphatab_available(), reason="node / alphaTab not available")
def test_alphatab_check_on_the_one_pick_scale(tmp_path, monkeypatch):
    from scaleseq import gp5
    from scaleseq.verify import check_alphatab
    box = get_box("b3")
    plan = one_pick_plan(box)
    path = tmp_path / "x.gp5"
    write_gp5(plan, str(path), title="t")
    probs, dump = check_alphatab(str(path), plan, title="t", tempo=80)
    assert probs == []
    assert sum(1 for e in dump["midi"]["events"] if e["type"] == "NoteOn") == 23
    # a tie the plan does not have: alphaTab's ties and note-ons disagree with it
    probs = check_alphatab(str(path), _retouch(plan, 2, tie=False), title="t", tempo=80, render=False)[0]
    assert any("tie" in p for p in probs) and any("note-on" in p for p in probs)
    # the bend written as a plain ramp (2 points): alphaTab bends across the whole note
    monkeypatch.setitem(gp5.BEND_POINTS, "bend", ((0, 0), (12, 2)))
    write_gp5(plan, str(path), title="t")
    probs = check_alphatab(str(path), plan, title="t", tempo=80, render=False)[0]
    assert any("reaches" in p for p in probs), probs


# ---------- the MIDI check on events written out by hand ----------

def _two_beats():
    """Pick D# on string 5 fret 6, tie it and bend it up to E, then a half rest (4/4, 960 ticks a beat)."""
    pick = {"rest": False, "value": 4, "tuplet": [1, 1], "string": 5, "fret": 6, "tie": False, "bend_kind": None}
    tied = dict(pick, tie=True, bend_kind="bend")
    rest = {"rest": True, "value": 2, "tuplet": [1, 1]}
    return [{"beats": [pick, tied, rest]}]


def _midi(*bends, on=((0, 51),), off=1920, extra=()):
    """alphaTab's order: at one tick, a note's bend value comes before its note-on."""
    ev = [{"type": "NoteBend", "tick": t, "channel": 1, "key": 51, "semitones": v} for t, v in bends]
    ev += [{"type": "NoteOn", "tick": t, "channel": 1, "key": k, "semitones": None} for t, k in on]
    ev += [{"type": "NoteOff", "tick": off, "channel": 1, "key": k, "semitones": None} for _, k in on[:1]]
    ev += list(extra)
    return {"division": 960, "events": sorted(ev, key=lambda e: e["tick"])}


def _prebend_release():
    """A pre-bend on string 5 fret 6 (sounds E), tied and released to D#, then a half rest."""
    pick = {"rest": False, "value": 4, "tuplet": [1, 1], "string": 5, "fret": 6, "tie": False,
            "bend_kind": "prebend"}
    return [{"beats": [pick, dict(pick, tie=True, bend_kind="release"), {"rest": True, "value": 2, "tuplet": [1, 1]}]}]


GOOD = [(0, 0.0), (960, 0.0), (1040, 0.0), (1120, 1.0), (1500, 1.0)]


def test_midi_check_accepts_a_bend_that_arrives_early_and_holds():
    assert check_midi(_midi(*GOOD), _two_beats()) == []


@pytest.mark.parametrize("bends,on,msg", [
    ([(0, 0.0), (960, 0.0), (1440, 0.5), (1919, 1.0)], ((0, 51),), "reaches"),     # slow ramp over the note
    ([(0, 0.0), (960, 0.0), (1120, 1.0), (1500, 0.5)], ((0, 51),), "holds"),       # sags after arriving
    ([(0, 0.0), (500, 0.5), (960, 0.0), (1120, 1.0)], ((0, 51),), "beat 1"),       # bend inside the pick
    (GOOD, ((0, 51), (960, 51)), "2 note-ons"),                                   # picked again
    (GOOD, ((0, 52),), "key"),                                                    # E's own key picked
])
def test_midi_check_catches_a_wrong_bend(bends, on, msg):
    probs = check_midi(_midi(*bends, on=on), _two_beats())
    assert any(msg in p for p in probs), probs


def test_midi_check_wants_the_note_held_through_its_tied_note():
    assert any("note-off" in p for p in check_midi(_midi(*GOOD, off=960), _two_beats()))


def test_midi_check_wants_a_pre_bend_set_before_its_note_on():
    release = [(960, 1.0), (1040, 1.0), (1120, 0.0), (1500, 0.0)]
    assert check_midi(_midi((0, 1.0), *release), _prebend_release()) == []
    late = _midi(*release)  # the +1 arrives at tick 0 only after the note-on: the pick sounds unbent first
    late["events"].insert(1, {"type": "NoteBend", "tick": 0, "channel": 1, "key": 51, "semitones": 1.0})
    assert [e["type"] for e in late["events"][:2]] == ["NoteOn", "NoteBend"]
    assert any("picks it bent 0" in p for p in check_midi(late, _prebend_release()))


def test_midi_check_refuses_channel_pitch_bends():
    wheel = {"type": "PitchBend", "tick": 0, "channel": 1, "key": None, "semitones": 0.0}
    assert any("channel pitch bends" in p for p in check_midi(_midi(*GOOD, extra=[wheel]), _two_beats()))


# ---------- the command line ----------

def test_cli_one_pick_bends(tmp_path, capsys):
    out = tmp_path / "root one pick.gp5"
    flags = [] if alphatab_available() else ["--no-alphatab"]
    code = scaleseq_cli.main(["generate", "--box", "root", "--patterns", "scale:4", "--one-pick-bends",
                              "-o", str(out), *flags])
    stdout = capsys.readouterr().out
    assert code == 0 and out.exists()
    assert "27 notes, 23 picks, 4 half-step bends (2 released)" in stdout
    marks = read_plan_shape(str(out))["bars"]
    assert sum(1 for bar in marks for x in bar["beats"] for n in x["notes"] if n["tie"]) == 4


def test_cli_refuses_one_pick_on_a_pattern_it_cannot_play(tmp_path, capsys):
    out = tmp_path / "x.gp5"
    code = scaleseq_cli.main(["generate", "--box", "root", "--patterns", "3s", "--one-pick-bends", "-o", str(out)])
    err = capsys.readouterr().err
    assert code == 1 and not out.exists() and "one pick per bend" in err


def test_cli_one_pick_and_blue_note_bends_together_is_an_error(tmp_path, capsys):
    with pytest.raises(SystemExit):
        scaleseq_cli.main(["generate", "--box", "root", "--patterns", "scale", "--one-pick-bends",
                           "--bend-blue-notes", "-o", str(tmp_path / "x.gp5")])
