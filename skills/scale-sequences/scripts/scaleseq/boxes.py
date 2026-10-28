# SPDX-License-Identifier: MIT
"""Scale boxes (fretboard shapes) and their validation.

A box is a set of (string, fret, finger) positions for one scale in one key. Sorted by pitch, a
valid box is a gap-free run of the scale with exactly one position per pitch -- that ordering is the
index space every sequence pattern works in (index 0 = lowest note of the box).

Add a box: append to BOX_SPECS (frets per string as (fret, finger) pairs, in any key; `key` says
which). `validate_box` refuses anything that is not a gap-free scale run.
"""

from __future__ import annotations

from dataclasses import dataclass

from .theory import (STANDARD_TUNING, blue_pc, degree_name, fret_pitch, next_scale_pitch, note_name,
                     pitch_class, scale_pcs)

# Three common A minor blues boxes, named after the scale degree of their lowest note on string 6
# (G = b7, A = root, C = b3). Fingers 1-4 = suggested left-hand fingering. String 6 = low E ... 1 = high e.
BOX_SPECS = {
    "blues-b7": {
        "label": "b7 shape", "key": "A", "scale": "minor-blues",
        "frets": {6: [(3, 1), (5, 3)], 5: [(3, 1), (5, 3), (6, 4)], 4: [(2, 1), (5, 4)],
                  3: [(2, 1), (5, 4)], 2: [(3, 1), (4, 2), (5, 3)], 1: [(3, 1), (5, 3)]},
    },
    "blues-root": {
        "label": "root shape", "key": "A", "scale": "minor-blues",
        "frets": {6: [(5, 1), (8, 4)], 5: [(5, 1), (6, 2), (7, 3)], 4: [(5, 1), (7, 3)],
                  3: [(5, 1), (7, 3), (8, 4)], 2: [(5, 1), (8, 4)], 1: [(5, 1), (8, 4)]},
    },
    "blues-b3": {
        "label": "b3 shape", "key": "A", "scale": "minor-blues",
        "frets": {6: [(8, 1), (10, 3), (11, 4)], 5: [(7, 1), (10, 4)], 4: [(7, 1), (10, 4)],
                  3: [(7, 1), (8, 2), (9, 3)], 2: [(8, 1), (10, 3)], 1: [(8, 1), (10, 3), (11, 4)]},
    },
}
ALIASES = {"b7": "blues-b7", "root": "blues-root", "b3": "blues-b3"}


class BoxError(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    string: int
    fret: int
    finger: int
    pitch: int

    @property
    def sf(self) -> tuple[int, int]:
        return (self.string, self.fret)


@dataclass(frozen=True)
class BendPair:
    """Two adjacent box notes a half step apart, played as ONE fret: the lower note on its own fret, the
    upper one by bending that fret up a half step (the upper note's own fret is not played)."""
    lower: int      # box index of the lower note
    upper: int      # box index of the upper note (lower + 1)
    string: int
    fret: int       # the lower note's fret, the one that is picked and bent
    finger: int     # the finger that bends it


FINGER_NAMES = {1: "index", 2: "middle", 3: "ring", 4: "little"}


@dataclass(frozen=True)
class Box:
    id: str
    label: str
    scale: str
    root_pc: int
    positions: tuple[Position, ...]  # sorted by pitch: positions[i] is box index i
    fret_offset: int = 0
    about: str = ""

    @property
    def n(self) -> int:
        return len(self.positions)

    @property
    def key(self) -> str:
        return note_name(self.root_pc)

    def index_of_sf(self) -> dict[tuple[int, int], int]:
        return {p.sf: i for i, p in enumerate(self.positions)}

    def index_of_pitch(self) -> dict[int, int]:
        return {p.pitch: i for i, p in enumerate(self.positions)}

    def fret_span(self) -> tuple[int, int]:
        frets = [p.fret for p in self.positions]
        return min(frets), max(frets)

    def blue_indices(self) -> list[int]:
        b = blue_pc(self.scale, self.root_pc)
        return [] if b is None else [i for i, p in enumerate(self.positions) if p.pitch % 12 == b]

    def bend_source(self, i: int) -> Position:
        """The box position a fret below position i on the same string (the note bent up a half step)."""
        p = self.positions[i]
        for q in self.positions:
            if q.string == p.string and q.fret == p.fret - 1:
                return q
        raise BoxError(f"{self.label}: no box note one fret below {note_name(p.pitch)} "
                       f"(string {p.string} fret {p.fret}) to bend from")

    def bend_pairs(self) -> list[BendPair]:
        """The pair each blue note is bent in, one pick per bend, by the box's fingering. If the blue
        note's string also holds the notes a fret below and a fret above it (e.g. D-D#-E, fingers
        1-2-3), the blue note is bent up to the note above; otherwise the note a fret below is bent up
        to the blue note. The bend is never the index or the little finger's."""
        pairs = []
        for i in self.blue_indices():
            p, below = self.positions[i], self.bend_source(i)
            above = next((q for q in self.positions if q.string == p.string and q.fret == p.fret + 1), None)
            lower = p if above is not None else below
            j = self.positions.index(lower)  # the upper note is j + 1: one position per pitch, no gaps
            if lower.finger not in (2, 3):
                raise BoxError(f"{self.label}: the bend at string {lower.string} fret {lower.fret} would be "
                               f"the {FINGER_NAMES[lower.finger]} finger's (only middle or ring bend)")
            pairs.append(BendPair(j, j + 1, lower.string, lower.fret, lower.finger))
        return pairs

    def diagram(self) -> str:
        lo, hi = self.fret_span()
        lines = [f"{self.label} ({self.id}), {self.key} {self.scale}, frets {lo}-{hi}"
                 + (f", {self.about}" if self.about else "")]
        lines.append("      " + "".join(f"{f:^5}" for f in range(lo, hi + 1)))
        by_sf = {p.sf: p for p in self.positions}
        for s in range(1, 7):
            cells = []
            for f in range(lo, hi + 1):
                p = by_sf.get((s, f))
                if p is None:
                    cells.append("  -  ")
                else:
                    tag = "R" if p.pitch % 12 == self.root_pc else degree_name(p.pitch, self.root_pc)
                    cells.append(f"{tag:>2}/{p.finger} ")
            lines.append(f"  s{s}  " + "".join(cells))
        lines.append("  (cell = scale degree / suggested finger; R = root)")
        return "\n".join(lines)


def _offset_for_key(spec_key_pc: int, target_pc: int, frets: list[int]) -> int:
    """Smallest fret offset that moves the box to the target key with no open strings."""
    base = (target_pc - spec_key_pc) % 12
    for off in (base - 12, base, base + 12):
        if min(frets) + off >= 1:
            return off
    raise BoxError("cannot place box")


def get_box(box_id: str, key: str | None = None, fret_offset: int | None = None) -> Box:
    """Build + validate a box. key: transpose to that root (lowest placement without open strings);
    fret_offset: explicit shift in frets (wins over key)."""
    bid = ALIASES.get(box_id, box_id)
    if bid not in BOX_SPECS:
        raise BoxError(f"unknown box {box_id!r}; known: {', '.join(sorted(BOX_SPECS))} "
                       f"(aliases {', '.join(sorted(ALIASES))})")
    spec = BOX_SPECS[bid]
    spec_pc = pitch_class(spec["key"])
    frets = [f for pairs in spec["frets"].values() for f, _ in pairs]
    if fret_offset is None:
        fret_offset = 0 if key is None else _offset_for_key(spec_pc, pitch_class(key), frets)
    root_pc = (spec_pc + fret_offset) % 12
    pos = []
    for s, pairs in spec["frets"].items():
        for f, finger in pairs:
            fret = f + fret_offset
            if fret < 0:
                raise BoxError(f"fret offset {fret_offset} puts string {s} below the nut")
            pos.append(Position(s, fret, finger, fret_pitch(s, fret, STANDARD_TUNING)))
    pos.sort(key=lambda p: p.pitch)
    roots = [f"s{p.string}f{p.fret}" for p in pos if p.pitch % 12 == root_pc]
    about = (f"lowest note {note_name(pos[0].pitch)} ({degree_name(pos[0].pitch, root_pc)}); "
             f"root at {', '.join(roots)}")
    box = Box(bid, spec["label"], spec["scale"], root_pc, tuple(pos), fret_offset, about)
    validate_box(box)
    return box


def validate_box(box: Box) -> None:
    """Every pitch class in the scale; sorted by pitch the positions form a strictly ascending,
    gap-free run of the scale (each consecutive pair = adjacent scale degrees). Raises BoxError."""
    problems = []
    pcs = scale_pcs(box.scale, box.root_pc)
    for p in box.positions:
        if p.pitch % 12 not in pcs:
            problems.append(f"string {p.string} fret {p.fret} = {note_name(p.pitch)} is not in "
                            f"{box.key} {box.scale}")
        if p.finger not in (1, 2, 3, 4):
            problems.append(f"string {p.string} fret {p.fret}: finger {p.finger} not in 1-4")
    for a, b in zip(box.positions, box.positions[1:]):
        if b.pitch <= a.pitch:
            problems.append(f"duplicate/non-ascending pitch: s{a.string}f{a.fret} and s{b.string}f{b.fret} "
                            f"both {note_name(a.pitch)}")
        elif a.pitch % 12 in pcs and b.pitch != next_scale_pitch(a.pitch, box.scale, box.root_pc):
            problems.append(f"gap between s{a.string}f{a.fret} ({note_name(a.pitch)}) and "
                            f"s{b.string}f{b.fret} ({note_name(b.pitch)}): not adjacent scale degrees")
    by_string: dict[int, list[Position]] = {}
    for p in box.positions:
        by_string.setdefault(p.string, []).append(p)
    for s, ps in by_string.items():
        ps.sort(key=lambda p: p.fret)
        if any(q.finger <= p.finger for p, q in zip(ps, ps[1:])):
            problems.append(f"string {s}: fingers do not ascend with frets {[(p.fret, p.finger) for p in ps]}")
    if problems:
        raise BoxError(f"box {box.id} ({box.label}) is invalid:\n  - " + "\n  - ".join(problems))
