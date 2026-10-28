# SPDX-License-Identifier: MIT
"""generate = build plan -> check plan -> write temp .gp5 -> read-back -> alphaTab (+render) -> move
into place. A file only lands at `out` when every check passed."""

from __future__ import annotations

import os
from pathlib import Path

from .boxes import Box, get_box
from .exercise import Section, build_bars, get_dur, realize
from .gp5 import read_plan_shape, write_gp5
from .patterns import get_pattern
from .verify import check_alphatab, check_plan, check_readback, compare_reads, diff_gp5, split_sections


class CheckFailed(RuntimeError):
    pass


def resolve_sections(patterns: list[str]) -> list[Section]:
    """One section per `pattern[:rhythm]` spec, in the order given. A section is labelled with its
    pattern's name; a pattern that occurs more than once is labelled with its rhythm too ("3s in
    eighth triplets", "3s in sextuplets"), and "#1", "#2", ... tell apart any label still repeated."""
    specs = []
    for spec in patterns:
        name, _, rhythm = (x.strip() for x in spec.strip().partition(":"))
        p = get_pattern(name)
        rhythm = rhythm or p.default_rhythm
        get_dur(rhythm, where=f" in {spec.strip()!r}")
        specs.append((p.name, rhythm))
    if not specs:
        raise ValueError("nothing to generate: give --patterns")
    names = [name for name, _ in specs]
    labels = [name if names.count(name) == 1 else f"{name} in {get_dur(rhythm).words}" for name, rhythm in specs]
    repeated = {label for label in labels if labels.count(label) > 1}
    seen: dict[str, int] = {}
    for k, label in enumerate(labels):
        if label in repeated:
            seen[label] = seen.get(label, 0) + 1
            labels[k] = f"{label} #{seen[label]}"
    return [Section(label, name, note=rhythm) for label, (name, rhythm) in zip(labels, specs)]


def check_against_reference_gp5(new: str, ref: str, plan: list[dict]) -> list[str]:
    """`new` must equal `ref` beat for beat, except where the plan bends a note: there `ref` has the
    note unbent and `new` has it on the same string with a half-step bend that ends where `ref`'s note
    sounds -- one fret lower if the bend ends up a half step (a bend up or a pre-bend), on the same fret
    if it ends released."""
    probs = []
    shape_new = read_plan_shape(new)["bars"]
    for d in diff_gp5(ref, new):
        if len(d) == 5 and d[2] == "notes":
            k, j, _, a, b = d
            pb = plan[k - 1]["beats"][j - 1]
            ends = b[0]["bend_points"][-1][1] if len(b) == 1 and b[0]["bend_points"] else None  # quarter tones
            ok = (len(a) == len(b) == 1 and pb.get("bend_kind") and not a[0]["bend"] and not a[0]["tie"]
                  and b[0]["bend"] == 2 and ends in (0, 2) and b[0]["string"] == a[0]["string"]
                  and b[0]["fret"] == a[0]["fret"] - ends // 2)
            if ok:
                continue
        probs.append(f"differs from reference: {d}")
    n_bent = sum(1 for bar in shape_new for x in bar["beats"] for n in x["notes"] if n["bend"])
    n_plan = sum(1 for bar in plan for x in bar["beats"] if not x["rest"] and x["bend_kind"])
    if n_bent != n_plan:
        probs.append(f"{n_bent} bent notes in file, plan has {n_plan}")
    return probs


def generate(box: Box | str, out: str, *, sections: list[Section], bend_blue: bool = False,
             one_pick_bends: bool = False, tempo: int = 80,
             title: str | None = None, subtitle: str = "", marker_fmt: str = "{label} ({shape})",
             fingering: bool = False, alphatab: bool = True, render: bool = True, force: bool = False,
             expect_reads: str | None = None, expect_gp5: str | None = None) -> dict:
    if isinstance(box, str):
        box = get_box(box)
    outp = Path(out)
    if outp.exists() and not force:
        raise FileExistsError(f"{out} exists (use --force to replace it)")
    title = title or f"{box.key} {box.scale.replace('-', ' ')} sequences ({box.label})"
    bars = build_bars(sections, box.n)
    plan = realize(bars, box, bend_blue=bend_blue, one_pick_bends=one_pick_bends, marker_fmt=marker_fmt)
    played = [x for b in plan for x in b["beats"] if not x["rest"]]
    report: dict = {"box": box.id, "label": box.label, "key": box.key, "n_box_notes": box.n,
                    "bars": len(plan), "notes": len(played),
                    "picks": sum(1 for x in played if not x["tie"]),
                    "bends": sum(1 for x in played if x["bend_kind"] in ("bend", "prebend")),
                    "releases": sum(1 for x in played if x["bend_kind"] == "release"),
                    "sections": [{"label": s.label, "pattern": s.pat().name,
                                  "rhythm": s.note_dur().key,
                                  "bars": len(sbars),
                                  "notes": sum(1 for b in sbars for x in b["beats"] if not x["rest"]),
                                  "index_notation": s.pat().notation(box.n)}
                                 for s, sbars in zip(sections, split_sections(plan))],
                    "checks": {}}
    probs = check_plan(plan, box, sections, bend_blue=bend_blue, one_pick_bends=one_pick_bends)
    report["checks"]["plan (bar fill, pitch class, in-box, bends" + (", one pick per bend" if one_pick_bends else "")
                     + ", pattern, rhythm)"] = probs or "ok"
    if expect_reads:
        p2 = compare_reads(plan, expect_reads)
        report["checks"]["note-for-note vs reference reads"] = p2 or "ok"
        probs += p2
    if probs:
        raise CheckFailed("plan checks failed:\n - " + "\n - ".join(probs))
    tmp = outp.with_name(outp.name + ".tmp.gp5")
    try:
        write_gp5(plan, str(tmp), title=title, subtitle=subtitle, tempo=tempo, root_pc=box.root_pc,
                  fingering=fingering)
        p3 = check_readback(str(tmp), plan, title=title, tempo=tempo, fingering=fingering)
        report["checks"]["read-back (pyguitarpro) exact"] = p3 or "ok"
        if expect_gp5:
            p5 = check_against_reference_gp5(str(tmp), expect_gp5, plan)
            report["checks"]["vs reference .gp5 (only bends may differ)"] = p5 or "ok"
            p3 = p3 + p5
        if alphatab:
            p4, dump = check_alphatab(str(tmp), plan, title=title, tempo=tempo, render=render)
            report["alphatab_version"] = dump.get("version")
            report["checks"]["alphaTab parse + MIDI (picks, bend timing)"
                             + (" + render (bend labels)" if render else "")] = p4 or "ok"
            if render:
                report["render_bend_labels"] = len(dump["render"]["bendLabels"])
            p3 = p3 + p4
        if p3:
            raise CheckFailed("file checks failed:\n - " + "\n - ".join(p3))
        os.replace(tmp, outp)
    finally:
        if tmp.exists():
            tmp.unlink()
    report["out"] = str(outp)
    report["plan"] = plan
    return report
