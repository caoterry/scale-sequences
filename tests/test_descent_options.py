# SPDX-License-Identifier: MIT
"""Per-section descent options: stop=N (the descent ends at group N, then the line lands on note 0) and
skip=N[+N...] (the descent leaves those groups out) -- in --patterns, and as Section.desc_stop /
Section.desc_skip in the Python API.

The streams below are written out by hand from the definitions (group N = [N + o for o in shape]; the
descent plays the groups' retrogrades from the top down), not produced by the code.
"""
import json
import re

import pytest

import scaleseq_cli
from conftest import alphatab_available
from scaleseq.boxes import get_box
from scaleseq.exercise import Section, build_bars, realize
from scaleseq.gp5 import read_plan_shape
from scaleseq.patterns import get_pattern, load_pattern_file
from scaleseq.pipeline import resolve_sections
from scaleseq.verify import check_plan


def flat(*groups):
    return [x for g in groups for x in g]


def stream(sec: Section, n: int) -> list[int]:
    return sec.pat().stream(n)


# ---------- the Python API: Section(desc_stop=..., desc_skip=...) ----------

@pytest.mark.parametrize("pattern,kw,n,want", [
    # 3s, stop at group 2: down [5,4,3] [4,3,2], then land on [0]
    ("3s", {"desc_stop": 2}, 6,
     flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5], [5, 4, 3], [4, 3, 2], [0])),
    # thirds, group 2 left out: down [5,3] [3,1] [2,0] (no [4,2]); ends on 0, so no landing note
    ("thirds", {"desc_skip": (2,)}, 6,
     flat([0, 2], [1, 3], [2, 4], [3, 5], [5, 3], [3, 1], [2, 0])),
    # 6s on 9 notes, groups 3 (the top) and 2 left out: from the top group up straight to group 1 down
    ("6s", {"desc_skip": (2, 3)}, 9,
     flat([0, 1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7], [3, 4, 5, 6, 7, 8],
          [6, 5, 4, 3, 2, 1], [5, 4, 3, 2, 1, 0])),
    # 3s on 7 notes, stop at 2 and group 4 left out: down [5,4,3] [4,3,2], land [0]
    ("3s", {"desc_stop": 2, "desc_skip": (4,)}, 7,
     flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6], [5, 4, 3], [4, 3, 2], [0])),
    # neighbor3 (pickup [0], palindromic top played once), stop at group 2: down [3,2,3], land [0]
    ("neighbor3", {"desc_stop": 2}, 5,
     flat([0], [1, 0, 1], [2, 1, 2], [3, 2, 3], [4, 3, 4], [3, 2, 3], [0])),
    # the top group left out of a non-palindromic pattern: 4s on 6 notes, skip 2 -> down [4,3,2,1] [3,2,1,0]
    ("4s", {"desc_skip": (2,)}, 6,
     flat([0, 1, 2, 3], [1, 2, 3, 4], [2, 3, 4, 5], [4, 3, 2, 1], [3, 2, 1, 0])),
    # options may leave the descent no group: the line goes up, then lands on [0]
    ("3s", {"desc_stop": 2, "desc_skip": (3, 2)}, 6, flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5], [0])),
    ("scale", {"desc_stop": 4}, 5, [0, 1, 2, 3, 4, 0]),
    # stop at 0 and an empty skip are the plain pattern
    ("3s", {"desc_stop": 0, "desc_skip": ()}, 5,
     flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [4, 3, 2], [3, 2, 1], [2, 1, 0])),
])
def test_section_descent_options_match_hand_written_streams(pattern, kw, n, want):
    assert stream(Section("s", pattern, **kw), n) == want


def test_no_option_leaves_the_pattern_as_it_is():
    sec = Section("3s", "3s")
    assert sec.pat() is get_pattern("3s")
    assert (sec.desc_stop, sec.desc_skip) == (None, None)


def test_skip_is_kept_sorted_without_repeats_and_a_list_is_accepted():
    assert Section("s", "thirds", desc_skip=[4, 2, 4]).desc_skip == (2, 4)


def test_section_options_replace_the_patterns_own(tmp_path, restore_library):
    """A pattern from a pattern file may set desc_stop/desc_skip itself; a section's option replaces it."""
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"3s-low": {"shape": [0, 1, 2], "desc_stop": 3, "desc_skip": [4]}}))
    load_pattern_file(str(pf))
    up = flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6])
    # the pattern's own: groups 4 down to 3, group 4 left out -> [5,4,3], land
    assert stream(Section("s", "3s-low"), 7) == up + flat([5, 4, 3], [0])
    # the section's stop replaces 3 (the pattern's skip stays): groups 4 down to 2, 4 left out
    assert stream(Section("s", "3s-low", desc_stop=2), 7) == up + flat([5, 4, 3], [4, 3, 2], [0])
    # the section's skip replaces [4] (the pattern's stop stays): groups 4 down to 3, 3 left out
    assert stream(Section("s", "3s-low", desc_skip=(3,)), 7) == up + flat([6, 5, 4], [0])
    # an empty skip clears the pattern's own
    assert stream(Section("s", "3s-low", desc_skip=()), 7) == up + flat([6, 5, 4], [5, 4, 3], [0])


@pytest.mark.parametrize("kw,msg", [
    ({"desc_stop": -1}, "desc_stop must be a group number, 0 or more, not -1"),
    ({"desc_stop": "2"}, "desc_stop must be a group number, 0 or more, not '2'"),
    ({"desc_stop": True}, "desc_stop must be a group number, 0 or more, not True"),
    ({"desc_skip": 2}, "desc_skip must be group numbers, 0 or more, not 2"),
    ({"desc_skip": (2, -3)}, "desc_skip must be group numbers, 0 or more, not (2, -3)"),
    ({"desc_skip": (2, "4")}, "desc_skip must be group numbers, 0 or more, not (2, '4')"),
])
def test_section_options_of_the_wrong_type_are_refused(kw, msg):
    with pytest.raises(ValueError, match=r"^section x: " + re.escape(msg) + "$"):
        Section("x", "3s", **kw)


@pytest.mark.parametrize("pattern,kw,n,msg", [
    ("3s", {"desc_stop": 4}, 6,
     "pattern 3s: the descent cannot stop at group 4: on a box of 6 notes its groups are 0 to 3"),
    ("thirds", {"desc_skip": (4,)}, 6,
     "pattern thirds: group 4 is not in the descent: on a box of 6 notes it plays groups 3 down to 0"),
    ("3s", {"desc_stop": 2, "desc_skip": (0,)}, 6,
     "pattern 3s: group 0 is not in the descent: on a box of 6 notes it plays groups 3 down to 2"),
    # a palindromic top group is played once, on the way up: it is not in the descent
    ("upper-neighbor3", {"desc_skip": (3,)}, 5,
     ("pattern upper-neighbor3: group 3 is not in the descent: on a box of 5 notes it plays groups 2 down to 0 "
      "(its top group reads the same both ways and is played once, on the way up)")),
    ("scale", {"desc_stop": 4, "desc_skip": (3,)}, 5,
     "pattern scale: group 3 is not in the descent: on a box of 5 notes it plays no group"),
])
def test_options_outside_the_descent_are_refused_with_the_groups_named(pattern, kw, n, msg):
    sec = Section("s", pattern, **kw)
    with pytest.raises(ValueError, match="^" + re.escape(msg) + "$"):
        stream(sec, n)
    with pytest.raises(ValueError, match="^" + re.escape(msg) + "$"):
        build_bars([sec], n)


def test_a_box_too_small_for_the_shape_is_still_reported_as_such():
    with pytest.raises(ValueError, match="^pattern 6s: box of 4 notes is too small$"):
        get_pattern("6s").stream(4)


@pytest.mark.parametrize("box_id", ["b7", "root", "b3", "4", "5"])
@pytest.mark.parametrize("spec", ["3s:8t:stop=3", "thirds:16:skip=2+5", "4s:stop=2:skip=4", "neighbor3:stop=6",
                                  "6s:16s:skip=3", "upper-neighbor3:skip=0+7"])
@pytest.mark.parametrize("bend", [False, True])
def test_options_pass_the_plan_check_on_every_box(box_id, spec, bend):
    box = get_box(box_id)
    secs = resolve_sections([spec])
    plan = realize(build_bars(secs, box.n), box, bend_blue=bend)
    assert check_plan(plan, box, secs, bend_blue=bend) == []
    # the plan check compares against the options: claiming the plain pattern fails
    plain = [Section(secs[0].label, secs[0].pattern, note=secs[0].note)]
    assert any("index stream differs" in p for p in check_plan(plan, box, plain, bend_blue=bend))


# ---------- --patterns syntax: pattern[:rhythm][:stop=N][:skip=N[+N...]] ----------

@pytest.mark.parametrize("spec,want", [
    ("3s:8t:stop=3", ("3s stop=3", "3s", "8t", 3, None)),
    ("thirds:skip=2+5", ("thirds skip=2+5", "thirds", "8", None, (2, 5))),
    ("1234:16:skip=4:stop=2", ("4s stop=2 skip=4", "4s", "16", 2, (4,))),
    (" 6s : 16s : skip = 5 + 3 + 5 ", ("6s skip=3+5", "6s", "16s", None, (3, 5))),
    ("3s::stop=2", ("3s stop=2", "3s", "8t", 2, None)),
    ("4s:stop=0", ("4s stop=0", "4s", "8", 0, None)),
])
def test_patterns_spec_options(spec, want):
    (sec,) = resolve_sections([spec])
    assert (sec.label, sec.pattern, sec.note, sec.desc_stop, sec.desc_skip) == want


@pytest.mark.parametrize("specs,want", [
    (["3s", "3s:stop=2"], ["3s", "3s stop=2"]),
    (["3s:8t:stop=2", "3s:16s:stop=2"], ["3s stop=2 in eighth triplets", "3s stop=2 in sextuplets"]),
    (["thirds:skip=3", "thirds:skip=3", "thirds"], ["thirds skip=3 in eighths #1", "thirds skip=3 in eighths #2",
                                                     "thirds"]),
])
def test_sections_with_options_are_labelled_with_them(specs, want):
    assert [s.label for s in resolve_sections(specs)] == want


SPEC_FORM = "pattern[:rhythm][:stop=N][:skip=N[+N...]]"


@pytest.mark.parametrize("spec,msg", [
    ("4s:slow=2", "unknown option 'slow' in '4s:slow=2'; options: stop=N, skip=N[+N...]"),
    ("4s:stop=x", "stop needs a group number, 0 or more, not 'x', in '4s:stop=x'"),
    ("4s:stop=-2", "stop needs a group number, 0 or more, not '-2', in '4s:stop=-2'"),
    ("4s:stop=", "stop needs a group number, 0 or more, not '', in '4s:stop='"),
    ("4s:stop=2+3", "stop needs a group number, 0 or more, not '2+3', in '4s:stop=2+3'"),
    ("4s:skip=", "skip needs group numbers, 0 or more, joined by '+' (e.g. skip=2+4), not '', in '4s:skip='"),
    ("4s:skip=2+", "skip needs group numbers, 0 or more, joined by '+' (e.g. skip=2+4), not '2+', in '4s:skip=2+'"),
    ("4s:skip=two", ("skip needs group numbers, 0 or more, joined by '+' (e.g. skip=2+4), not 'two', "
                     "in '4s:skip=two'")),
    ("4s:stop=2:stop=3", "stop given twice in '4s:stop=2:stop=3'"),
    ("4s:stop=2:16", (f"'16' in '4s:stop=2:16' is not an option; write {SPEC_FORM} (the rhythm right after "
                      "the pattern name)")),
    ("4s:16:8", f"'8' in '4s:16:8' is not an option; write {SPEC_FORM} (the rhythm right after the pattern name)"),
])
def test_bad_options_are_refused_on_the_command_line(tmp_path, capsys, spec, msg):
    out = tmp_path / "x.gp5"
    code = scaleseq_cli.main(["generate", "--box", "root", "--patterns", f"3s,{spec}", "-o", str(out),
                              "--no-alphatab"])
    assert (code, capsys.readouterr().err) == (1, f"FAILED: {msg}\n")
    assert not out.exists()


def test_an_option_outside_the_box_fails_on_the_command_line(tmp_path, capsys):
    out = tmp_path / "x.gp5"
    code = scaleseq_cli.main(["generate", "--box", "root", "--patterns", "3s:stop=12", "-o", str(out), "--no-alphatab"])
    assert (code, capsys.readouterr().err) == (
        1, "FAILED: pattern 3s: the descent cannot stop at group 12: on a box of 14 notes its groups are 0 to 11\n")
    assert not out.exists()


def test_patterns_command_documents_the_options(capsys):
    assert scaleseq_cli.main(["patterns", "--n", "6"]) == 0
    out = capsys.readouterr().out
    assert ("section options (after the rhythm): stop=N -- the descent ends at group N, then lands on note 0; "
            "skip=N[+N...] -- the descent leaves those groups out. Group N = the group built on box note N.") in out


# ---------- end to end: the command line, the file, alphaTab ----------

def _expected_5_shape_streams() -> list[list[int]]:
    """On the 5 shape (14 notes), from the definitions."""
    s1 = (flat(*[[i, i + 1, i + 2] for i in range(12)])                     # 3s up, groups 0..11
          + flat(*[[i + 2, i + 1, i] for i in range(11, 2, -1)]) + [0])    # down to group 3, land
    s2 = (flat(*[[i, i + 2] for i in range(12)])                            # thirds up, groups 0..11
          + flat(*[[i + 2, i] for i in range(11, -1, -1) if i not in (2, 5)]))
    s3 = (flat(*[[i, i + 1, i + 2, i + 3] for i in range(11)])              # 4s up, groups 0..10
          + flat(*[[i + 3, i + 2, i + 1, i] for i in range(10, 1, -1) if i != 4]) + [0])
    return [s1, s2, s3]


@pytest.mark.skipif(not alphatab_available(), reason="node / alphaTab not available")
def test_cli_generates_the_options_and_alphatab_checks_the_file(tmp_path, capsys):
    out = tmp_path / "options.gp5"
    code = scaleseq_cli.main(["generate", "--box", "5", "--patterns", "3s:8t:stop=3,thirds:16:skip=2+5,4s:stop=2:skip=4",
                              "-o", str(out), "--json"])
    cap = capsys.readouterr()
    assert (code, cap.err) == (0, "")
    rep = json.loads(cap.out)
    assert rep["n_box_notes"] == 14
    assert all(v == "ok" for v in rep["checks"].values())
    assert any(k.startswith("alphaTab parse + MIDI") for k in rep["checks"])
    want = _expected_5_shape_streams()
    assert [(s["label"], s["pattern"], s["rhythm"], s["notes"]) for s in rep["sections"]] == [
        ("3s stop=3", "3s", "8t", len(want[0])), ("thirds skip=2+5", "thirds", "16", len(want[1])),
        ("4s stop=2 skip=4", "4s", "8", len(want[2]))]
    assert rep["sections"][0]["index_notation"].endswith("[5,4,3] | land [0]")
    assert "[7,5]" not in rep["sections"][1]["index_notation"].split("down")[1]
    # the file, read back: every section's notes are the box positions of the expected index streams
    box = get_box("5")
    song = read_plan_shape(str(out))
    markers = [b["marker"] for b in song["bars"] if b["marker"]]
    assert markers == ["3s stop=3 (5 shape)", "thirds skip=2+5 (5 shape)", "4s stop=2 skip=4 (5 shape)"]
    got, cur = [], None
    for b in song["bars"]:
        if b["marker"]:
            cur = []
            got.append(cur)
        cur += [(n["string"], n["fret"]) for x in b["beats"] for n in x["notes"]]
    assert got == [[box.positions[i].sf for i in s] for s in want]
    # after the stop, the line lands on note 0 as a quarter on a beat (eighth triplets before it)
    sec1 = [x for b in song["bars"][:rep["sections"][0]["bars"]] for x in b["beats"] if x["notes"]]
    assert [(x["value"], x["tuplet"]) for x in sec1[-2:]] == [(8, [3, 2]), (4, [1, 1])]
