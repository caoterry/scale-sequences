# SPDX-License-Identifier: MIT
"""Deterministic checks. Each returns a list of problems (empty = pass); nothing here "looks" at
anything -- every claim is a comparison against the plan, the box, or the pattern definition."""

from __future__ import annotations

import bisect
import json
import math
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from .boxes import Box
from .exercise import BEND_SHAPES, Section, ends_bent
from .gp5 import BEND_POINTS, BEND_TYPES, read_plan_shape
from .theory import fret_pitch, note_name, scale_pcs

HERE = Path(__file__).resolve().parent.parent

# alphaTab's BendType after it loads a note (Note.finish): a 4-point bend whose middle values differ stays
# 1 = Custom, i.e. played as written; a held pre-bend is 6 = Prebend.
ALPHATAB_BEND_TYPE = {None: 0, "bend": 1, "prebend": 6, "release": 1}
# A bend or a release reaches its target within this fraction of its note (BEND_POINTS: 2/12), then holds.
REACH = Fraction(1, 6)


def _beats(b: dict) -> Fraction:
    return Fraction(4, b["value"]) * Fraction(b["tuplet"][1], b["tuplet"][0])


def _shape(b: dict) -> tuple[int, int]:
    """Half steps above the fret's own pitch at the start and the end of a note."""
    return BEND_SHAPES[b["bend_kind"]] if b["bend_kind"] else (0, 0)


def sounding_end(b: dict) -> int:
    return fret_pitch(b["string"], b["fret"]) + _shape(b)[1]


def split_sections(plan: list[dict]) -> list[list[dict]]:
    """The plan's bars, one list per run of bars with the same `section_index`. Sections are told apart
    by that index, not by label: two sections may share a label (the same pattern twice)."""
    out: list[list[dict]] = []
    for bar in plan:
        if out and out[-1][0]["section_index"] == bar["section_index"]:
            out[-1].append(bar)
        else:
            out.append([bar])
    return out


def check_plan(plan: list[dict], box: Box, sections: list[Section], *, bend_blue: bool = False,
               one_pick_bends: bool = False) -> list[str]:
    """Bar fill, pitch class, in-box, bends (none, blue-note bends, or one pick per bend -- whichever the
    plan was asked for), and pattern/rhythm of every section."""
    probs = []
    if bend_blue and one_pick_bends:
        probs.append("both blue-note bends and one-pick bends asked for")
    pcs = scale_pcs(box.scale, box.root_pc)
    by_sf = box.index_of_sf()
    blue = set(box.blue_indices())
    for k, bar in enumerate(plan, 1):
        tot = sum((_beats(b) for b in bar["beats"]), Fraction(0))
        want = Fraction(4 * bar["ts"][0], bar["ts"][1])
        if tot != want:
            probs.append(f"bar {k}: beats sum {tot}, time signature {bar['ts']} wants {want}")
        for b in bar["beats"]:
            if b["rest"]:
                continue
            i = b["idx"]
            if b["bend_kind"] not in (None, *BEND_SHAPES) or b["bend"] != (2 if b["bend_kind"] else 0):
                probs.append(f"bar {k}: bend {b['bend']} / {b['bend_kind']!r} is not a half-step bend")
                continue
            sounding = sounding_end(b)
            if sounding != b["pitch"] or sounding != box.positions[i].pitch:
                probs.append(f"bar {k}: s{b['string']}f{b['fret']} {b['bend_kind'] or 'unbent'} sounds {sounding}, "
                             f"box index {i} is {box.positions[i].pitch}")
            if sounding % 12 not in pcs:
                probs.append(f"bar {k}: pitch class {sounding % 12} not in {box.key} {box.scale}")
            if (b["string"], b["fret"]) not in by_sf:
                probs.append(f"bar {k}: s{b['string']}f{b['fret']} is not a position of the {box.label}")
            elif b["finger"] != box.positions[by_sf[b["string"], b["fret"]]].finger:
                probs.append(f"bar {k}: s{b['string']}f{b['fret']} finger {b['finger']}, the {box.label} "
                             f"fingers it with {box.positions[by_sf[b['string'], b['fret']]].finger}")
            if one_pick_bends:
                continue  # _check_one_pick
            should_bend = bend_blue and i in blue
            if bool(b["bend_kind"]) != should_bend or b["tie"] or b["bend_kind"] not in (None, "bend"):
                probs.append(f"bar {k}: idx {i} {b['bend_kind'] or 'unbent'}{' tied' if b['tie'] else ''} "
                             f"but blue-note bend expected={should_bend}")
            if b["bend"] and i in blue and box.bend_source(i).sf != (b["string"], b["fret"]):
                probs.append(f"bar {k}: bent note s{b['string']}f{b['fret']} is not the fret below the blue note")
    if one_pick_bends:
        probs += _check_one_pick(plan, box)
    groups = split_sections(plan)
    if [g[0]["section_index"] for g in groups] != list(range(len(groups))):
        probs.append(f"section order in the plan {[g[0]['section_index'] for g in groups]}: "
                     "a section is split or out of order")
    if len(groups) != len(sections):
        probs.append(f"{len(groups)} sections in the plan, {len(sections)} expected")
    for k, (sec, sbars) in enumerate(zip(sections, groups), 1):
        name = f"section {k} ({sec.label})"
        if any(bar["section"] != sec.label for bar in sbars):
            probs.append(f"{name}: bars labelled {sorted({bar['section'] for bar in sbars})}")
        got = [x for bar in sbars for x in bar["beats"] if not x["rest"]]
        pat = sec.pat()
        want_idx = pat.stream(box.n)
        if [b["idx"] for b in got] != want_idx:
            probs.append(f"{name}: index stream differs from pattern {pat.name}")
        parts = pat.sections(box.n)
        n_pick = sum(len(g) for g in parts["pickup"])
        n_land = sum(len(g) for g in parts["land"])
        want_d = ([sec.pickup] * n_pick + [sec.note_dur().key] * (len(want_idx) - n_pick - n_land)
                  + [sec.land] * n_land)
        if [b["dur"] for b in got] != want_d:
            probs.append(f"{name}: rhythm differs from {want_d[:3]}...")
        if not sbars[0]["marker"] or any(b["marker"] for b in sbars[1:]):
            probs.append(f"{name}: marker must be on its first bar only")
        if not sbars[-1]["double_bar"] or any(b["double_bar"] for b in sbars[:-1]):
            probs.append(f"{name}: double bar must be on its last bar only")
        # rests only after the last line note (to complete the final bar or put the landing on a beat)
        flat = [b for bar in sbars for b in bar["beats"]]
        last_line = max((j for j, b in enumerate(flat) if not b["rest"] and b["role"] in ("up", "down", "pickup")),
                        default=len(flat))
        if any(b["rest"] for b in flat[:last_line]):
            probs.append(f"{name}: rest inside the line")
        if any(b["rest"] for b in flat) and not any(b["rest"] for b in sbars[-1]["beats"]):
            probs.append(f"{name}: rests outside the final bar")
    return probs


def _check_one_pick(plan: list[dict], box: Box) -> list[str]:
    """One pick per bend, from the box's bend pairs and the rules alone (not by re-running the planner):
    two adjacent notes of a pair (no rest between) are one picked note -- going up the upper note is the
    lower one tied and bent up, going down the lower note is tied and releases the upper one, which is
    bent (a picked pre-bend, or the bend of the way up); a pair's upper note is never played on its own
    fret; a tie continues the note before it on the same fret and pitch, inside its section; a pre-bend
    is released, and does not come right after a note on its own string; a bend is never picked again
    (also across a section's double bar: only a rest separates notes); nothing is bent off a pair's
    fret, or with the index or little finger."""
    probs = []
    pairs = box.bend_pairs()
    up = {(p.lower, p.upper): p for p in pairs}
    down = {(p.upper, p.lower): p for p in pairs}
    upper_pair = {p.upper: p for p in pairs}
    pair_frets = {(p.string, p.fret) for p in pairs}

    def name(i: int) -> str:
        return note_name(box.positions[i].pitch)

    beats = [(f"bar {k} beat {j}", bar["section_index"], b)
             for k, bar in enumerate(plan, 1) for j, b in enumerate(bar["beats"], 1)]
    for n, (where, sec, b) in enumerate(beats):
        if b["rest"]:
            continue
        before = beats[n - 1][2] if n and not beats[n - 1][2]["rest"] else None  # the note heard just before
        prev = before if before is not None and beats[n - 1][1] == sec else None   # ... in this section
        nxt = beats[n + 1][2] if n + 1 < len(beats) and not beats[n + 1][2]["rest"] and beats[n + 1][1] == sec \
            else None
        i, kind, sf = b["idx"], b["bend_kind"], (b["string"], b["fret"])
        if b["tie"]:
            if prev is None or (prev["string"], prev["fret"]) != sf:
                probs.append(f"{where}: a tie to {'no note' if prev is None else 'another string or fret'}")
            elif kind not in ("bend", "release"):
                probs.append(f"{where}: a tie with no bend up or release")
            elif _shape(prev)[1] != _shape(b)[0]:
                probs.append(f"{where}: the tie starts {_shape(b)[0]} half steps up, the note before "
                             f"ends {_shape(prev)[1]}")
        else:
            if kind in ("bend", "release"):
                probs.append(f"{where}: {name(i)} is a {kind} picked again (one pick per bend: a tied note)")
            if before is not None and ends_bent(before) and (before["string"], before["fret"]) == sf:
                probs.append(f"{where}: {name(i)} picks the bend held from the note before again")
            elif kind == "prebend" and before is not None and before["string"] == b["string"]:
                probs.append(f"{where}: the pre-bend {name(i)} comes right after a note on the same string")
        if kind and b["finger"] not in (2, 3):
            probs.append(f"{where}: bent with finger {b['finger']} (only middle or ring bend)")
        if kind == "prebend" and not (nxt and nxt["tie"] and nxt["bend_kind"] == "release"):
            probs.append(f"{where}: the pre-bend {name(i)} is not released by a tied note")
        if kind and sf not in pair_frets:
            probs.append(f"{where}: bent on s{sf[0]}f{sf[1]}, which is not the fret of a bend pair")
        if i in upper_pair and sf == box.positions[i].sf:
            p = upper_pair[i]
            probs.append(f"{where}: {name(i)} is played on its own fret (s{sf[0]}f{sf[1]}); one pick per "
                         f"bend plays it by bending s{p.string}f{p.fret}")
        if prev is not None:
            pair = (prev["idx"], i)
            if pair in up and not (b["tie"] and kind == "bend"):
                probs.append(f"{where}: {name(i)} follows {name(prev['idx'])} but is picked again, not "
                             "tied and bent up from it")
            if pair in down and not (b["tie"] and kind == "release"):
                probs.append(f"{where}: {name(i)} follows {name(prev['idx'])} but is picked again, not "
                             "tied and released from it")
            if b["tie"] and pair not in up and pair not in down:
                probs.append(f"{where}: a tie from {name(prev['idx'])} to {name(i)}, not a bend pair")
    return probs


def check_readback(path: str, plan: list[dict], *, title: str, tempo: int, fingering: bool) -> list[str]:
    """Parse the written file (pyguitarpro) and compare with the plan exactly."""
    got = read_plan_shape(path)
    probs = []
    if got["title"] != title or got["tempo"] != tempo:
        probs.append(f"title/tempo {got['title']!r}/{got['tempo']} != {title!r}/{tempo}")
    if len(got["bars"]) != len(plan):
        return probs + [f"{len(got['bars'])} bars read back, plan has {len(plan)}"]
    for k, (g, p) in enumerate(zip(got["bars"], plan), 1):
        if g["ts"] != p["ts"] or g["marker"] != p["marker"] or g["double_bar"] != p["double_bar"]:
            probs.append(f"bar {k}: header {g['ts'], g['marker'], g['double_bar']} != "
                         f"{p['ts'], p['marker'], p['double_bar']}")
        if g["other_voices"] != [[("empty", g["bar_time"])]]:
            probs.append(f"bar {k}: voice 2 is not one empty full-bar beat: {g['other_voices']}")
        gb = [(x["rest"], x["value"], x["tuplet"],
               [(n["string"], n["fret"], n["finger"] if fingering else -1, n["tie"], n["bend"], n["bend_type"],
                 n["bend_points"]) for n in x["notes"]])
              for x in g["beats"]]
        pb = [(x["rest"], x["value"], x["tuplet"], [] if x["rest"] else [
               (x["string"], x["fret"], x["finger"] if fingering else -1, x["tie"], x["bend"],
                BEND_TYPES[x["bend_kind"]].name if x["bend_kind"] else None,
                list(BEND_POINTS[x["bend_kind"]]) if x["bend_kind"] else [])])
              for x in p["beats"]]
        if gb != pb:
            probs.append(f"bar {k}: read back {gb}\n   plan {pb}")
    return probs


def find_alphatab() -> str | None:
    """$ALPHATAB_MJS, else the skill's own node_modules (`npm ci --prefix <skill dir>`)."""
    cands = [os.environ.get("ALPHATAB_MJS"),
             str(HERE.parent / "node_modules/@coderline/alphatab/dist/alphaTab.mjs")]
    return next((c for c in cands if c and Path(c).is_file()), None)


def alphatab_dump(path: str, render: bool = True) -> dict:
    atp = find_alphatab()
    node = shutil.which("node")
    if not atp or not node:
        raise RuntimeError("alphaTab check unavailable: need `node` and alphaTab 1.8.x "
                           f"(npm ci --prefix {HERE.parent}, or set ALPHATAB_MJS=/path/to/alphaTab.mjs)")
    cmd = [node, str(HERE / "alphatab_check.mjs"), atp, path] + (["--render"] if render else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"alphatab_check exited {r.returncode}")
    return json.loads(r.stdout)


def check_alphatab(path: str, plan: list[dict], *, title: str, tempo: int, render: bool = True) -> tuple[list[str], dict]:
    """alphaTab's own parse vs the plan: bars, time signatures, markers, every beat and note (string,
    fret, tie, bend type and points as written, pitch at the end of the note), the MIDI alphaTab plays
    (check_midi), and (render) ½ labels on exactly the notes that bend up or are pre-bent."""
    d = alphatab_dump(path, render=render)
    probs = []
    if d["title"] != title or d["tempo"] != tempo or d["tracks"] != 1:
        probs.append(f"alphaTab title/tempo/tracks {d['title']!r}/{d['tempo']}/{d['tracks']}")
    if len(d["masterBars"]) != len(plan) or len(d["bars"]) != len(plan):
        return probs + [f"alphaTab sees {len(d['masterBars'])} bars, plan {len(plan)}"], d
    bent_where = set()
    for k, (mb, bar, p) in enumerate(zip(d["masterBars"], d["bars"], plan)):
        if mb["ts"] != p["ts"] or mb["marker"] != p["marker"] or mb["doubleBar"] != p["double_bar"]:
            probs.append(f"bar {k + 1}: alphaTab header {mb} vs plan {p['ts'], p['marker'], p['double_bar']}")
        v1 = bar["voices"][0]
        others = bar["voices"][1:]
        if any(not all(b["isEmpty"] for b in v) for v in others):
            probs.append(f"bar {k + 1}: alphaTab sees content in voice 2+")
        if len(v1) != len(p["beats"]):
            probs.append(f"bar {k + 1}: alphaTab {len(v1)} beats, plan {len(p['beats'])}")
            continue
        for j, (a, b) in enumerate(zip(v1, p["beats"])):
            tup = [1, 1] if a["tuplet"][0] in (-1, 0, 1) else a["tuplet"]
            if a["isRest"] != b["rest"] or a["duration"] != b["value"] or tup != b["tuplet"]:
                probs.append(f"bar {k + 1} beat {j + 1}: alphaTab rest/dur/tuplet "
                             f"{a['isRest'], a['duration'], tup} vs {b['rest'], b['value'], b['tuplet']}")
            want = [] if b["rest"] else [(b["string"], b["fret"], b["bend"], b["pitch"])]
            got = [(n["string"], n["fret"], n["maxBendQuarterTones"], n["soundingEnd"]) for n in a["notes"]]
            if got != want:
                probs.append(f"bar {k + 1} beat {j + 1}: alphaTab notes {got} vs plan {want}")
                continue
            if b["rest"]:
                continue
            n, kind = a["notes"][0], b["bend_kind"]
            if n["tie"] != b["tie"]:
                probs.append(f"bar {k + 1} beat {j + 1}: alphaTab tie={n['tie']}, plan tie={b['tie']}")
            points = [[5 * pos, val] for pos, val in BEND_POINTS[kind]] if kind else []  # alphaTab offsets 0-60
            if n["bendType"] != ALPHATAB_BEND_TYPE[kind] or n["bendPoints"] != points:
                probs.append(f"bar {k + 1} beat {j + 1}: alphaTab bend type {n['bendType']} points {n['bendPoints']}, "
                             f"plan {kind} = type {ALPHATAB_BEND_TYPE[kind]} points {points}")
            if kind in ("bend", "prebend"):
                bent_where.add((k, 0, j))
    probs += check_midi(d["midi"], plan)
    if render:
        labels = d["render"]["bendLabels"]
        got_where = [tuple(x["where"]) if x["where"] else None for x in labels]
        if any(x["text"] != "½" for x in labels):
            probs.append(f"render: bend labels other than ½: {sorted({x['text'] for x in labels})}")
        if None in got_where or len(got_where) != len(set(got_where)) or set(got_where) != bent_where:
            probs.append(f"render: ½ labels on {len(labels)} beats {sorted(w for w in got_where if w)[:6]}..., "
                         f"notes bent up or pre-bent {len(bent_where)}")
    return probs, d


def check_midi(midi: dict, plan: list[dict]) -> list[str]:
    """The MIDI alphaTab plays (alphatab_check.mjs `midi`: events in alphaTab's order, per-note bends in
    half steps) vs the plan: one note-on per pick (tied notes are not picked), at the pick's tick and
    fret's key, held to the end of its last tied note; and, beat by beat, that note's bend: it starts at
    the plan's value (for the picked note, also the value set before its note-on), reaches the target
    within REACH of the beat, holds it to the beat's end and never leaves the range between the two.
    No channel-wide pitch bends."""
    div = midi["division"]
    ev = sorted(midi["events"], key=lambda e: e["tick"])  # stable: alphaTab's order within a tick
    bends: dict[tuple, tuple[list, list, list]] = {}  # (channel, key) -> NoteBend event indices, ticks, values
    offs: dict[tuple, tuple[list, list]] = {}         # (channel, key) -> NoteOff event indices, ticks
    for n, e in enumerate(ev):
        if e["type"] == "NoteBend":
            for col, x in zip(bends.setdefault((e["channel"], e["key"]), ([], [], [])), (n, e["tick"], e["semitones"])):
                col.append(x)
        elif e["type"] == "NoteOff":
            for col, x in zip(offs.setdefault((e["channel"], e["key"]), ([], [])), (n, e["tick"])):
                col.append(x)
    probs = []
    if any(e["type"] == "PitchBend" for e in ev):
        probs.append("alphaTab MIDI: channel pitch bends (bends must be per note)")
    picks: list[dict] = []
    t = Fraction(0)
    for k, bar in enumerate(plan, 1):
        for j, b in enumerate(bar["beats"], 1):
            d = _beats(b) * div
            if not b["rest"]:
                beat = (f"bar {k} beat {j}", t, t + d, _shape(b))
                if b["tie"] and picks:
                    picks[-1]["beats"].append(beat)
                    picks[-1]["end"] = t + d
                else:
                    picks.append({"key": fret_pitch(b["string"], b["fret"]), "start": t, "end": t + d,
                                  "beats": [beat]})
            t += d
    ons = [(n, e) for n, e in enumerate(ev) if e["type"] == "NoteOn"]
    if len(ons) != len(picks):
        return probs + [f"alphaTab MIDI: {len(ons)} note-ons, plan has {len(picks)} picks"]
    for p, (n, on) in zip(picks, ons):
        where = p["beats"][0][0]
        if (on["tick"], on["key"]) != (p["start"], p["key"]):
            probs.append(f"{where}: alphaTab note-on key {on['key']} at tick {on['tick']}, "
                         f"plan key {p['key']} at tick {p['start']}")
            continue
        note = (on["channel"], on["key"])
        off_idx, off_ticks = offs.get(note, ([], []))
        m = bisect.bisect_right(off_idx, n)
        off = off_ticks[m] if m < len(off_idx) else None
        if off != p["end"]:
            probs.append(f"{where}: alphaTab note-off at tick {off}, plan {p['end']} (the end of its last tied note)")
        idx, ticks, vals = bends.get(note, ([], [], []))
        m = bisect.bisect_left(idx, n)
        if abs((vals[m - 1] if m else 0) - p["beats"][0][3][0]) > 1e-9:  # the bend set before the note-on
            probs.append(f"{where}: alphaTab picks it bent {vals[m - 1] if m else 0} half steps, "
                         f"plan {p['beats'][0][3][0]}")

        def at(tick: Fraction) -> float:  # the bend in effect at `tick`: the last event at or before it
            m = bisect.bisect_right(ticks, tick)
            return vals[m - 1] if m else 0

        for beat, start, end, (v0, v1) in p["beats"]:
            reach = start + math.ceil((end - start) * REACH)
            lo, mid, hi = (bisect.bisect_left(ticks, x) for x in (start, reach, end))
            inside = [(int(ticks[x] - start), round(vals[x], 3)) for x in range(lo, hi)]  # (tick, half steps)
            if abs(at(start) - v0) > 1e-9:
                probs.append(f"{beat}: alphaTab bend starts at {at(start)} half steps, plan {v0}")
            if abs(at(reach) - v1) > 1e-9:
                probs.append(f"{beat}: alphaTab bend is {at(reach):.3f} half steps at {REACH} of the note, "
                             f"plan {v1}: it reaches its target late or never ({inside})")
            elif any(abs(vals[x] - v1) > 1e-9 for x in range(mid, hi)):
                probs.append(f"{beat}: alphaTab bend leaves {v1} half steps after reaching it: a bend holds "
                             f"its target to the end of the note ({inside})")
            if any(not min(v0, v1) - 1e-9 <= v <= max(v0, v1) + 1e-9 for _, v in inside):
                probs.append(f"{beat}: alphaTab bend goes outside {v0}..{v1} half steps ({inside})")
    return probs


# ---------- comparisons with an existing reference ----------

def compare_reads(plan: list[dict], reads_dir: str, keys: list[str] | None = None) -> list[str]:
    """Note-for-note against a TAB read and a staff read of a reference exercise, in the flat layout
    {section: {"short_first_bar": bool, "bars": [{"notes": [[s, f], ...]}]}} (tab) and
    {section: {"bars": [{"events": [{"dur", "triplet", "rest"}]}]}} (staff), sections in plan order.
    Compares string, fret, duration, tuplet, rests, bar count/boundaries, time signatures."""
    tab = json.load(open(Path(reads_dir) / "tab_read.json"))
    staff = json.load(open(Path(reads_dir) / "staff_read.json"))
    keys = keys or list(tab)
    probs = []
    groups = split_sections(plan)
    if len(groups) != len(keys):
        return [f"plan has {len(groups)} sections, reads {len(keys)}"]
    for pbars, key in zip(groups, keys):
        tb, sb = tab[key]["bars"], staff[key]["bars"]
        if not (len(pbars) == len(tb) == len(sb)):
            probs.append(f"{key}: bars plan {len(pbars)} tab {len(tb)} staff {len(sb)}")
            continue
        for bi, (p, t, s) in enumerate(zip(pbars, tb, sb)):
            ev_beats = sum((Fraction(4, int(e["dur"])) * (Fraction(2, 3) if e.get("triplet") else 1)
                            for e in s["events"]), Fraction(0))
            want_ts = [4, 4] if ev_beats == 4 else [int(ev_beats * 2), 8]
            if p["ts"] != want_ts:
                probs.append(f"{key} bar {bi + 1}: time signature {p['ts']} vs reads {want_ts}")
            pn = [(x["string"], x["fret"]) for x in p["beats"] if not x["rest"]]
            if pn != [tuple(n) for n in t["notes"]]:
                probs.append(f"{key} bar {bi + 1}: notes {pn} vs tab read {t['notes']}")
            pr = [(x["rest"], x["value"], x["tuplet"] == [3, 2]) for x in p["beats"]]
            sr = [(bool(e.get("rest")), int(e["dur"]), bool(e.get("triplet"))) for e in s["events"]]
            if pr != sr:
                probs.append(f"{key} bar {bi + 1}: rhythm {pr} vs staff read {sr}")
            if any(x["bend"] for x in p["beats"] if not x["rest"]):
                probs.append(f"{key} bar {bi + 1}: plan has bends; reads have none")
    return probs


def diff_gp5(a: str, b: str) -> list[tuple]:
    """Structural differences between two .gp5 files (headers, beats, notes). [] = musically identical."""
    ga, gb = read_plan_shape(a), read_plan_shape(b)
    diffs = []
    if len(ga["bars"]) != len(gb["bars"]):
        return [("bars", len(ga["bars"]), len(gb["bars"]))]
    for k, (x, y) in enumerate(zip(ga["bars"], gb["bars"]), 1):
        for f in ("ts", "marker", "double_bar", "other_voices"):
            if x[f] != y[f]:
                diffs.append((k, f, x[f], y[f]))
        if len(x["beats"]) != len(y["beats"]):
            diffs.append((k, "beat count", len(x["beats"]), len(y["beats"])))
            continue
        for j, (u, v) in enumerate(zip(x["beats"], y["beats"]), 1):
            if (u["rest"], u["value"], u["tuplet"], u["status"]) != (v["rest"], v["value"], v["tuplet"], v["status"]):
                diffs.append((k, j, "beat", u, v))
            elif u["notes"] != v["notes"]:
                diffs.append((k, j, "notes", u["notes"], v["notes"]))
    return diffs

