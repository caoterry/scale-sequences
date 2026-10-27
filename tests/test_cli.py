# SPDX-License-Identifier: MIT
"""The command line: section labels for a repeated pattern, error messages, and user pattern files."""
import json

import pytest

import scaleseq_cli
from conftest import alphatab_available
from scaleseq.boxes import get_box
from scaleseq.exercise import Section, build_bars, realize
from scaleseq.gp5 import read_plan_shape
from scaleseq.patterns import PATTERNS, get_pattern
from scaleseq.pipeline import resolve_sections
from scaleseq.verify import check_plan

RHYTHMS = "1, 2, 4, 8, 16, 4t, 8t, 16t, 16s"


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = scaleseq_cli.main(list(args))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def at_flags() -> list[str]:
    return [] if alphatab_available() else ["--no-alphatab"]


# ---------- the same pattern more than once ----------

def test_a_pattern_used_once_is_labelled_with_its_name():
    assert [s.label for s in resolve_sections(["1234", " 3s:16", "6s"])] == ["4s", "3s", "6s"]


@pytest.mark.parametrize("specs,want", [
    (["3s:8t", "3s:16s"], ["3s in eighth triplets", "3s in sextuplets"]),
    (["4s", "1234:16", "3s"], ["4s in eighths", "4s in sixteenths", "3s"]),
    (["3s", "3s:8t"], ["3s in eighth triplets #1", "3s in eighth triplets #2"]),  # 8t is the 3s default
    (["4s", "fours", "4s:16"], ["4s in eighths #1", "4s in eighths #2", "4s in sixteenths"]),
])
def test_a_repeated_pattern_gets_a_label_per_section(specs, want):
    secs = resolve_sections(specs)
    assert [s.label for s in secs] == want
    assert len({s.label for s in secs}) == len(secs)


@pytest.mark.parametrize("box_id", ["b7", "root", "b3"])
@pytest.mark.parametrize("bend", [False, True])
def test_a_repeated_pattern_passes_the_plan_check(box_id, bend):
    box = get_box(box_id)
    secs = resolve_sections(["3s:8t", "3s:16s", "4s", "1234", "neighbor3:16", "neighbor3"])
    plan = realize(build_bars(secs, box.n), box, bend_blue=bend)
    assert check_plan(plan, box, secs, bend_blue=bend) == []


def test_the_plan_check_keeps_sections_with_one_label_apart():
    """Sections given through the API may share a label; each is still checked on its own bars."""
    box = get_box("root")
    secs = [Section("3s", "3s", note="8t"), Section("3s", "3s", note="16s")]
    plan = realize(build_bars(secs, box.n), box)
    assert check_plan(plan, box, secs, bend_blue=False) == []
    claimed = [Section("3s", "3s", note="8t"), Section("3s", "3s", note="8t")]
    probs = check_plan(plan, box, claimed, bend_blue=False)
    assert probs and all(p.startswith("section 2 (3s)") and "rhythm" in p for p in probs)
    probs = check_plan(plan, box, secs[:1], bend_blue=False)
    assert any("2 sections in the plan, 1 expected" in p for p in probs)
    split = [dict(bar) for bar in plan]
    split[-1]["section_index"] = 0  # the last bar of section 2 claims to belong to section 1
    assert any("a section is split or out of order" in p for p in check_plan(split, box, secs, bend_blue=False))


def test_cli_writes_one_pattern_in_two_rhythms(tmp_path, capsys):
    out = tmp_path / "3s two rhythms.gp5"
    code, stdout, err = run(capsys, "generate", "--box", "b7", "--patterns", "3s:8t,3s:16s", "-o", str(out),
                            "--json", *at_flags())
    assert (code, err) == (0, "")
    rep = json.loads(stdout)
    # 3s on the 14-note b7 box: 12 groups up + 12 down = 72 notes; 72 x 1/3 beat = 6 bars, 72 x 1/6 = 3 bars
    assert [(s["label"], s["pattern"], s["rhythm"], s["bars"], s["notes"]) for s in rep["sections"]] == [
        ("3s in eighth triplets", "3s", "8t", 6, 72), ("3s in sextuplets", "3s", "16s", 3, 72)]
    assert rep["bars"] == 9 and all(v == "ok" for v in rep["checks"].values())
    markers = [b["marker"] for b in read_plan_shape(str(out))["bars"] if b["marker"]]
    assert markers == ["3s in eighth triplets (b7 shape)", "3s in sextuplets (b7 shape)"]


# ---------- error messages ----------

def test_unknown_rhythm_lists_the_valid_rhythms(tmp_path, capsys):
    out = tmp_path / "x.gp5"
    code, _, err = run(capsys, "generate", "--box", "b7", "--patterns", "4s,3s:9", "-o", str(out))
    assert code == 1 and not out.exists()
    assert err == f"FAILED: unknown rhythm '9' in '3s:9'; valid rhythms: {RHYTHMS} (t = triplet, 16s = sextuplet)\n"


def test_unknown_rhythm_through_the_api():
    with pytest.raises(KeyError, match=f"unknown rhythm '9'; valid rhythms: {RHYTHMS}"):
        Section("3s", "3s", note="9").note_dur()
    with pytest.raises(KeyError, match="unknown rhythm '3'"):
        build_bars([Section("n", "neighbor3", pickup="3")], 14)


def test_unknown_pattern_is_quoted_once(tmp_path, capsys):
    code, _, err = run(capsys, "generate", "--box", "b7", "--patterns", "5s", "-o", str(tmp_path / "x.gp5"))
    assert code == 1
    assert err == f"FAILED: unknown pattern '5s'; known: {', '.join(PATTERNS)}\n"


def test_any_key_error_prints_its_message_not_its_repr(monkeypatch, capsys):
    def boom(a):
        raise KeyError("no 'x' here")
    monkeypatch.setattr(scaleseq_cli, "cmd_boxes", boom)
    assert run(capsys, "boxes") == (1, "", "FAILED: no 'x' here\n")


# ---------- patterns the user defines in a file of their own ----------

def write_pattern_file(tmp_path, spec: dict) -> str:
    path = tmp_path / "my patterns.json"
    path.write_text(json.dumps(spec))
    return str(path)


def test_pattern_file_adds_a_pattern_for_the_run(tmp_path, capsys, restore_library):
    pf = write_pattern_file(tmp_path, {"132": {"shape": [0, 2, 1], "default_rhythm": "8t"}})
    out = tmp_path / "132.gp5"
    code, stdout, err = run(capsys, "generate", "--box", "root", "--pattern-file", pf, "--patterns", "132,132:16",
                            "-o", str(out), "--json", *at_flags())
    assert (code, err) == (0, "")
    rep = json.loads(stdout)
    assert [(s["label"], s["rhythm"]) for s in rep["sections"]] == [("132 in eighth triplets", "8t"),
                                                                    ("132 in sixteenths", "16")]
    assert rep["sections"][0]["index_notation"].startswith("up [0,2,1] [1,3,2] [2,4,3]")
    assert get_pattern("132").shape == (0, 2, 1)


def test_patterns_command_shows_the_file_patterns(tmp_path, capsys, restore_library):
    pf = write_pattern_file(tmp_path, {"132": {"shape": [0, 2, 1], "about": "one-three-two"}})
    code, stdout, _ = run(capsys, "patterns", "--n", "5", "--pattern-file", pf)
    assert code == 0
    assert "132 -- default rhythm 8\n  one-three-two\n  N=5: up [0,2,1] [1,3,2] [2,4,3] |" in stdout


def test_analyze_matches_a_file_pattern(tmp_path, capsys, mini_box, restore_library):
    pf = write_pattern_file(tmp_path, {"132": {"shape": [0, 2, 1]}})
    from scaleseq import patterns
    patterns.load_pattern_file(pf)
    plan = realize(build_bars([Section("132", "132")], mini_box.n), mini_box)
    patterns.PATTERNS.pop("132")
    reads = tmp_path / "reads"
    reads.mkdir()
    (reads / "tab_read.json").write_text(json.dumps({"ex": {"bars": [
        {"notes": [[x["string"], x["fret"]] for x in bar["beats"] if not x["rest"]]} for bar in plan]}}))
    assert "matches: NONE" in run(capsys, "analyze", "--box", "mini", "--reads", str(reads))[1]
    code, stdout, _ = run(capsys, "analyze", "--box", "mini", "--reads", str(reads), "--pattern-file", pf)
    assert code == 0 and "ex: 24 notes; matches: 132" in stdout


@pytest.mark.parametrize("spec,msg", [
    ({"3s": {"shape": [0, 1, 2]}}, "pattern '3s' is already in the library; use another name"),
    ({"1234": {"shape": [0, 1, 2]}}, "pattern '1234' is already in the library; use another name"),
    ({"x": {"shape": [0, 1], "speed": 3}}, "pattern 'x' has unknown fields ['speed']"),
    ({"x": {"about": "no shape"}}, "pattern 'x' needs a shape"),
    ({"x": {"shape": []}}, "pattern 'x' needs a shape"),
    ({"x": {"shape": [0, -1]}}, "pattern 'x' needs a shape"),
    ({"x": {"shape": [0, 1], "desc_stop": "1"}}, "pattern 'x': wrong type for desc_stop"),
    ({"x": {"shape": [0, 1], "default_rhythm": "9"}}, "pattern 'x': unknown default_rhythm '9'"),
    ({"a,b": {"shape": [0, 1]}}, "pattern name 'a,b'"),
    ({"x": {"shape": [0, 1], "aliases": ["4s"]}}, "alias '4s' of pattern 'x' is already in the library"),
    (["not", "a", "mapping"], "must be a JSON object"),
])
def test_pattern_file_is_refused_when_wrong(tmp_path, capsys, restore_library, spec, msg):
    pf = write_pattern_file(tmp_path, spec)
    out = tmp_path / "x.gp5"
    code, _, err = run(capsys, "generate", "--box", "root", "--pattern-file", pf, "--patterns", "4s", "-o", str(out))
    assert code == 1 and not out.exists()
    assert err.startswith(f"FAILED: {pf}: ") and msg in err, err
    assert set(PATTERNS) == {"scale", "thirds", "3s", "4s", "6s", "1231", "upper-neighbor3", "neighbor3"}


def test_missing_input_files_fail_with_a_message(tmp_path, capsys):
    missing = tmp_path / "nowhere"
    code, _, err = run(capsys, "analyze", "--box", "root", "--reads", str(missing))
    assert code == 1 and err.startswith("FAILED: ") and "tab_read.json" in err
    code, _, err = run(capsys, "generate", "--box", "b7", "--patterns", "4s", "-o", str(tmp_path / "x.gp5"),
                       "--no-alphatab", "--expect-gp5", str(missing / "ref.gp5"))
    assert code == 1 and err.startswith("FAILED: ") and "ref.gp5" in err
    assert not list(tmp_path.glob("*.gp5")) and not list(tmp_path.glob("*.tmp*"))


def test_english_only_check_covers_every_cjk_block():
    from test_repo import CJK
    for cp in (0x2F00, 0x3042, 0x4E2D, 0xAC00, 0xF900, 0xFF21, 0x20000):
        assert CJK.search(chr(cp)), hex(cp)
    assert not CJK.search("half-step ½ · ¼ ¾ é")
