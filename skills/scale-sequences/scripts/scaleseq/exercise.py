# SPDX-License-Identifier: MIT
"""Turn patterns + rhythm into bars (4/4, pickup bar of its own), then into a concrete plan of
(string, fret, bend) notes on a box. The plan is what gets written AND what every check compares to.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .boxes import Box
from .patterns import Pattern, get_pattern

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


@dataclass(frozen=True)
class Section:
    label: str
    pattern: str
    note: str | None = None      # rhythm of the line; None = the pattern's default
    pickup: str = "8"            # rhythm of pickup notes (if the pattern has any)
    land: str = "4"              # rhythm of the landing note (if the pattern needs one)

    def pat(self) -> Pattern:
        return get_pattern(self.pattern)

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


def realize(bars: list[Bar], box: Box, *, bend_blue: bool = False, marker_fmt: str = "{label}") -> list[dict]:
    """Concrete plan: per bar {section, section_index, marker, double_bar, ts, beats:[{rest, dur, value,
    tuplet, idx, string, fret, bend, pitch, finger, role}]}. bend: quarter tones (2 = half step)."""
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
                    d.update(string=src.string, fret=src.fret, bend=2, finger=src.finger, pitch=p.pitch)
                else:
                    d.update(string=p.string, fret=p.fret, bend=0, finger=p.finger, pitch=p.pitch)
            beats.append(d)
        plan.append({"section": b.section, "section_index": b.section_index,
                     "marker": marker_fmt.format(label=b.section, shape=box.label) if b.first else None,
                     "double_bar": b.last, "ts": list(b.ts), "beats": beats})
    return plan
