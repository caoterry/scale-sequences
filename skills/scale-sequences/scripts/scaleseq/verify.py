# SPDX-License-Identifier: MIT
"""Deterministic checks. Each returns a list of problems (empty = pass); nothing here "looks" at
anything -- every claim is a comparison against the plan, the box, or the pattern definition."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from .boxes import Box
from .exercise import Section
from .gp5 import read_plan_shape
from .theory import fret_pitch, scale_pcs

HERE = Path(__file__).resolve().parent.parent


def _beats(b: dict) -> Fraction:
    return Fraction(4, b["value"]) * Fraction(b["tuplet"][1], b["tuplet"][0])


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


def check_plan(plan: list[dict], box: Box, sections: list[Section], *, bend_blue: bool) -> list[str]:
    """Bar fill, pitch class, in-box, bends, and pattern/rhythm of every section."""
    probs = []
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
            sounding = fret_pitch(b["string"], b["fret"]) + b["bend"] // 2
            if sounding != b["pitch"] or sounding != box.positions[i].pitch:
                probs.append(f"bar {k}: s{b['string']}f{b['fret']} bend {b['bend']} sounds {sounding}, "
                             f"box index {i} is {box.positions[i].pitch}")
            if sounding % 12 not in pcs:
                probs.append(f"bar {k}: pitch class {sounding % 12} not in {box.key} {box.scale}")
            if (b["string"], b["fret"]) not in by_sf:
                probs.append(f"bar {k}: s{b['string']}f{b['fret']} is not a position of the {box.label}")
            should_bend = bend_blue and i in blue
            if bool(b["bend"]) != should_bend or (b["bend"] and b["bend"] != 2):
                probs.append(f"bar {k}: idx {i} bend={b['bend']} but blue-note bend expected={should_bend}")
            if b["bend"] and box.bend_source(i).sf != (b["string"], b["fret"]):
                probs.append(f"bar {k}: bent note s{b['string']}f{b['fret']} is not the fret below the blue note")
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
               [(n["string"], n["fret"], n["bend"], n["finger"] if fingering else -1) for n in x["notes"]])
              for x in g["beats"]]
        pb = [(x["rest"], x["value"], x["tuplet"],
               [] if x["rest"] else [(x["string"], x["fret"], x["bend"], x["finger"] if fingering else -1)])
              for x in p["beats"]]
        if gb != pb:
            probs.append(f"bar {k}: read back {gb}\n   plan {pb}")
        for x in g["beats"]:
            for n in x["notes"]:
                if n["bend"] and n["bend_type"] != "bend":
                    probs.append(f"bar {k}: bend type {n['bend_type']}")
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
    """alphaTab's own parse vs the plan: bars, time signatures, markers, every beat and note, the
    sounding pitch of every note (fret + bend), and (render) bend labels on exactly the bent notes."""
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
            got = [(n["string"], n["fret"], n["maxBendQuarterTones"], n["sounding"]) for n in a["notes"]]
            if got != want:
                probs.append(f"bar {k + 1} beat {j + 1}: alphaTab notes {got} vs plan {want}")
            if not b["rest"] and b["bend"]:
                bent_where.add((k, 0, j))
                if a["notes"][0]["bendType"] != 2:  # alphaTab BendType.Bend
                    probs.append(f"bar {k + 1} beat {j + 1}: alphaTab bend type {a['notes'][0]['bendType']}")
    if render:
        labels = d["render"]["bendLabels"]
        got_where = [tuple(x["where"]) if x["where"] else None for x in labels]
        if any(x["text"] != "½" for x in labels):
            probs.append(f"render: bend labels other than ½: {sorted({x['text'] for x in labels})}")
        if None in got_where or len(got_where) != len(set(got_where)) or set(got_where) != bent_where:
            probs.append(f"render: ½ labels on {len(labels)} beats {sorted(w for w in got_where if w)[:6]}..., "
                         f"bent notes {len(bent_where)}")
    return probs, d


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

