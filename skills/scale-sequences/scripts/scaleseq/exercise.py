# SPDX-License-Identifier: MIT
"""Turn patterns + rhythm into bars (4/4, pickup bar of its own), then into a concrete plan of
(string, fret, bend) notes on a box. The plan is what gets written AND what every check compares to.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from fractions import Fraction

from .boxes import Box
from .patterns import Pattern, get_pattern
from .theory import note_name

BAR_BEATS = Fraction(4)


@dataclass(frozen=True)
class Dur:
    key: str
    value: int            # GP duration value: 1 whole, 2 half, 4 quarter, 8 eighth, 16 sixteenth
    enters: int = 1       # tuplet enters:times (3:2 triplet, 6:4 sextuplet)
    times: int = 1
    words: str = ""       # plural name for labels, e.g. "eighth triplets"

    @property
    def beats(self) -> Fraction:
        return Fraction(4, self.value) * Fraction(self.times, self.enters)


DURS = {d.key: d for d in (
    Dur("1", 1, words="whole notes"), Dur("2", 2, words="half notes"), Dur("4", 4, words="quarters"),
    Dur("8", 8, words="eighths"), Dur("16", 16, words="sixteenths"),
    Dur("4t", 4, 3, 2, "quarter triplets"), Dur("8t", 8, 3, 2, "eighth triplets"),
    Dur("16t", 16, 3, 2, "sixteenth triplets"), Dur("16s", 16, 6, 4, "sextuplets"),
)}


def get_dur(key: str, where: str = "") -> Dur:
    """The rhythm called `key`; `where` is added to the error message (e.g. " in '3s:9'")."""
    if key not in DURS:
        raise KeyError(f"unknown rhythm {key!r}{where}; valid rhythms: {', '.join(DURS)} "
                       "(t = triplet, 16s = sextuplet)")
    return DURS[key]


def _group_number(x: object) -> bool:
    return type(x) is int and x >= 0  # not bool


@dataclass(frozen=True)
class Section:
    """One section of a file: a pattern in a rhythm. desc_stop / desc_skip change where the pattern's
    descent goes in this section only (None = as the pattern defines it). Group N is the group built on
    box note N (patterns.Pattern), counted from 0 at the bottom of the box.

    desc_stop=N  the descent ends at group N instead of coming all the way down; the line then lands on
                 the box's lowest note (`stop=N` in --patterns)
    desc_skip    groups the descent leaves out: coming down, the line goes from the group above each one
                 straight to the group below it (`skip=N[+N...]` in --patterns); kept sorted, without
                 repeats; () plays every group"""
    label: str
    pattern: str
    note: str | None = None      # rhythm of the line; None = the pattern's default
    pickup: str = "8"            # rhythm of pickup notes (if the pattern has any)
    land: str = "4"              # rhythm of the landing note (if the pattern needs one)
    desc_stop: int | None = None
    desc_skip: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.desc_stop is not None and not _group_number(self.desc_stop):
            raise ValueError(f"section {self.label}: desc_stop must be a group number, 0 or more, "
                             f"not {self.desc_stop!r}")
        if self.desc_skip is not None:
            if not (isinstance(self.desc_skip, (tuple, list)) and all(map(_group_number, self.desc_skip))):
                raise ValueError(f"section {self.label}: desc_skip must be group numbers, 0 or more, "
                                 f"not {self.desc_skip!r}")
            object.__setattr__(self, "desc_skip", tuple(sorted(set(self.desc_skip))))

    def pat(self) -> Pattern:
        """The section's pattern, with its descent options applied."""
        p = get_pattern(self.pattern)
        opts = {k: v for k, v in (("desc_stop", self.desc_stop), ("desc_skip", self.desc_skip)) if v is not None}
        return dataclasses.replace(p, **opts) if opts else p

    def note_dur(self) -> Dur:
        return get_dur(self.note or self.pat().default_rhythm)


@dataclass
class Event:
    idx: int | None          # box index; None = rest
    dur: Dur
    role: str                # pickup / up / down / land / rest


@dataclass
class Bar:
    section: str             # the section's label
    ts: tuple[int, int]
    events: list[Event]
    first: bool = False
    last: bool = False
    section_index: int = 0   # position of the section in the file (labels need not be unique)

    @property
    def length(self) -> Fraction:
        return Fraction(4 * self.ts[0], self.ts[1])


def rest_fill(pos: Fraction, end: Fraction, unit: Dur) -> list[Dur]:
    """Rests from pos to end inside one 4/4 bar: finish the current beat in the line's own unit
    (so a triplet stays a complete triplet), then quarter/half/whole rests on their usual beats."""
    out: list[Dur] = []
    while pos < end:
        if pos.denominator != 1:
            for d in (unit, DURS["16"], DURS["16t"]):
                if (pos % 1) % d.beats == 0 and pos + d.beats <= end:
                    break
            else:
                raise ValueError(f"cannot fill a rest at beat {pos}")
            out.append(d)
            pos += d.beats
            continue
        left = end - pos
        if pos == 0 and left >= 4:
            d = DURS["1"]
        elif pos % 2 == 0 and left >= 2:
            d = DURS["2"]
        elif left >= 1:
            d = DURS["4"]
        else:
            d = next(x for x in (DURS["8"], DURS["16"]) if x.beats <= left)
        out.append(d)
        pos += d.beats
    return out


def _pickup_ts(length: Fraction) -> tuple[int, int]:
    for den in (8, 16, 4):  # 8 first: a one-eighth pickup is 1/8, as printed in GP
        num = length * den / 4
        if num.denominator == 1:
            return int(num), den
    raise ValueError(f"pickup length {length} beats has no n/4, n/8 or n/16 time signature")


def section_bars(sec: Section, n: int, index: int = 0) -> list[Bar]:
    pat, unit = sec.pat(), sec.note_dur()
    parts = pat.sections(n)
    bars: list[Bar] = []
    if parts["pickup"]:
        pd = get_dur(sec.pickup)
        evs = [Event(i, pd, "pickup") for i in parts["pickup"][0]]
        bars.append(Bar(sec.label, _pickup_ts(sum((e.dur.beats for e in evs), Fraction(0))), evs,
                        section_index=index))
    cur: list[Event] = []
    pos = Fraction(0)

    def push(ev: Event) -> None:
        nonlocal cur, pos
        if pos + ev.dur.beats > BAR_BEATS:
            raise ValueError(f"{sec.label}: {ev.dur.key} at beat {pos} would cross the barline")
        cur.append(ev)
        pos += ev.dur.beats
        if pos == BAR_BEATS:
            bars.append(Bar(sec.label, (4, 4), cur, section_index=index))
            cur, pos = [], Fraction(0)

    for role in ("up", "down"):
        for g in parts[role]:
            for i in g:
                push(Event(i, unit, role))
    for g in parts["land"]:
        ld = get_dur(sec.land)
        if pos.denominator != 1:                      # land on a beat
            for d in rest_fill(pos, Fraction(pos.numerator // pos.denominator + 1), unit):
                push(Event(None, d, "rest"))
        if pos + ld.beats > BAR_BEATS:                # does not fit: finish the bar first
            for d in rest_fill(pos, BAR_BEATS, unit):
                push(Event(None, d, "rest"))
        for i in g:
            push(Event(i, ld, "land"))
    if cur:
        for d in rest_fill(pos, BAR_BEATS, unit):
            push(Event(None, d, "rest"))
    assert not cur
    bars[0].first = True
    bars[-1].last = True
    return bars


def build_bars(sections: list[Section], n: int) -> list[Bar]:
    return [b for k, sec in enumerate(sections) for b in section_bars(sec, n, k)]


# A bent note: half steps above its fret's own pitch at the start and at the end of the note.
#   bend     starts on the fret's pitch and rises a half step early in the note, then holds
#   prebend  picked already bent up a half step, held
#   release  starts bent up a half step and comes back to the fret's pitch early in the note, then holds
BEND_SHAPES = {"bend": (0, 1), "prebend": (1, 1), "release": (1, 0)}


def ends_bent(b: dict) -> bool:
    return not b["rest"] and b["bend_kind"] is not None and BEND_SHAPES[b["bend_kind"]][1] == 1


def realize(bars: list[Bar], box: Box, *, bend_blue: bool = False, one_pick_bends: bool = False,
            marker_fmt: str = "{label}") -> list[dict]:
    """Concrete plan: per bar {section, section_index, marker, double_bar, ts, beats:[{rest, dur, value,
    tuplet, idx, string, fret, bend, bend_kind, tie, pitch, finger, role}]}. idx and pitch are the box
    note that sounds at the end of the beat; bend: quarter tones (2 = half step, 0 = none); bend_kind:
    None or a key of BEND_SHAPES; tie: the note is not picked, it continues the note before it.

    bend_blue: every blue note is picked on the fret below and bent up (bend_kind "bend").
    one_pick_bends: each blue note is bent in its box.bend_pairs() pair, one pick per bend (_one_pick)."""
    if bend_blue and one_pick_bends:
        raise ValueError("use one of bend_blue or one_pick_bends, not both")
    blue = set(box.blue_indices()) if bend_blue else set()
    plan = []
    for b in bars:
        beats = []
        for e in b.events:
            d = {"rest": e.idx is None, "dur": e.dur.key, "value": e.dur.value,
                 "tuplet": [e.dur.enters, e.dur.times], "role": e.role, "idx": e.idx}
            if e.idx is not None:
                p = box.positions[e.idx]
                if e.idx in blue:
                    src = box.bend_source(e.idx)
                    d.update(string=src.string, fret=src.fret, bend=2, bend_kind="bend", tie=False,
                             finger=src.finger, pitch=p.pitch)
                else:
                    d.update(string=p.string, fret=p.fret, bend=0, bend_kind=None, tie=False,
                             finger=p.finger, pitch=p.pitch)
            beats.append(d)
        plan.append({"section": b.section, "section_index": b.section_index,
                     "marker": marker_fmt.format(label=b.section, shape=box.label) if b.first else None,
                     "double_bar": b.last, "ts": list(b.ts), "beats": beats})
    if one_pick_bends:
        sections: dict[int, list[dict]] = {}
        for bar in plan:
            sections.setdefault(bar["section_index"], []).extend(bar["beats"])
        for beats in sections.values():  # a tie never crosses a section's double bar
            _one_pick(beats, box)
        _refuse_unplayable(plan, box)
    return plan


def _one_pick(beats: list[dict], box: Box) -> None:
    """Rewrite one section's beats so that each bend pair is played with one pick: going up (lower
    note, then upper), the upper note is the lower one's fret tied and bent up; going down (upper,
    then lower), the upper note is a picked pre-bend on that fret -- or the bend of the way up, at the
    top -- and the lower note is tied and released."""
    pairs = box.bend_pairs()
    up = {(p.lower, p.upper): p for p in pairs}
    down = {(p.upper, p.lower): p for p in pairs}

    def bent(b: dict, p, kind: str, tie: bool) -> None:
        b.update(string=p.string, fret=p.fret, finger=p.finger, bend=2, bend_kind=kind, tie=tie)

    for a, b in zip(beats, beats[1:]):
        if a["rest"] or b["rest"]:
            continue
        if (a["idx"], b["idx"]) in up:
            bent(b, up[a["idx"], b["idx"]], "bend", tie=True)
        elif (a["idx"], b["idx"]) in down:
            p = down[a["idx"], b["idx"]]
            if a["bend_kind"] is None:
                bent(a, p, "prebend", tie=False)
            bent(b, p, "release", tie=True)


def _refuse_unplayable(plan: list[dict], box: Box) -> None:
    """ValueError where the one-pick rewrite cannot be played as written: an upper note with no lower
    note beside it (it would need its own fret), a held bend picked again, or a pre-bend right after a
    note on its own string (that string is still sounding, so it cannot be bent silently first). Only
    a rest separates two notes; a section's double bar does not."""
    def name(i: int) -> str:
        return note_name(box.positions[i].pitch)

    lower_of = {p.upper: p.lower for p in box.bend_pairs()}
    beats = [(k, j, b) for k, bar in enumerate(plan, 1) for j, b in enumerate(bar["beats"], 1)]
    problems = []
    for n, (k, j, b) in enumerate(beats):
        if b["rest"]:
            continue
        where = f"{name(b['idx'])} at bar {k} beat {j}"
        if b["idx"] in lower_of and not ends_bent(b):
            problems.append(f"{where} has no {name(lower_of[b['idx']])} next to it to bend from or into")
        a = beats[n - 1][2] if n else None
        if a is None or a["rest"] or b["tie"]:
            continue
        if ends_bent(a) and (a["string"], a["fret"]) == (b["string"], b["fret"]):
            problems.append(f"{where} would pick the bend held from the note before it again")
        elif b["bend_kind"] == "prebend" and a["string"] == b["string"]:
            problems.append(f"{where} is a pre-bend right after a note on the same string")
    if problems:
        raise ValueError("one pick per bend is not possible in this pattern on the "
                         f"{box.label}: " + "; ".join(problems))
