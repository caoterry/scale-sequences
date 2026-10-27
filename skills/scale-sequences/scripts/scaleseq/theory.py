# SPDX-License-Identifier: MIT
"""Pitch arithmetic: note names, scales, guitar tuning."""

from __future__ import annotations

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_ALIASES = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E",
                 "E#": "F", "B#": "C"}

# Standard tuning, GP string numbering: 1 = high e ... 6 = low E. Value = MIDI pitch of the open string.
STANDARD_TUNING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}

# Scale = semitones above the root. "blue" = the note a blues scale adds to its pentatonic.
SCALES = {
    "minor-blues": {"steps": (0, 3, 5, 6, 7, 10), "blue": 6},
    "minor-pentatonic": {"steps": (0, 3, 5, 7, 10), "blue": None},
    "major-blues": {"steps": (0, 2, 3, 4, 7, 9), "blue": 3},
    "major-pentatonic": {"steps": (0, 2, 4, 7, 9), "blue": None},
    "natural-minor": {"steps": (0, 2, 3, 5, 7, 8, 10), "blue": None},
    "major": {"steps": (0, 2, 4, 5, 7, 9, 11), "blue": None},
}

# Degree names for the minor-blues family (used in labels like "b7 shape").
DEGREE_NAMES = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "b5", 7: "5", 8: "b6", 9: "6",
                10: "b7", 11: "7"}

# Major-key signature (sharps > 0, flats < 0) per root pitch class -- blues charts in a key are
# usually printed with the major key signature of their root (A blues: three sharps).
MAJOR_KEY_SHARPS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}


def pitch_class(name: str) -> int:
    """'A' -> 9, 'Bb' -> 10, 'f#' -> 6."""
    n = name.strip()
    n = n[0].upper() + n[1:]
    n = _FLAT_ALIASES.get(n, n)
    if n not in NOTE_NAMES:
        raise ValueError(f"unknown note name {name!r}")
    return NOTE_NAMES.index(n)


def note_name(midi: int) -> str:
    return NOTE_NAMES[midi % 12]


def note_name_octave(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def fret_pitch(string: int, fret: int, tuning: dict[int, int] = STANDARD_TUNING) -> int:
    return tuning[string] + fret


def scale_pcs(scale: str, root_pc: int) -> set[int]:
    return {(root_pc + s) % 12 for s in SCALES[scale]["steps"]}


def blue_pc(scale: str, root_pc: int) -> int | None:
    b = SCALES[scale]["blue"]
    return None if b is None else (root_pc + b) % 12


def next_scale_pitch(midi: int, scale: str, root_pc: int) -> int:
    """The next scale tone strictly above `midi`."""
    pcs = scale_pcs(scale, root_pc)
    p = midi + 1
    while p % 12 not in pcs:
        p += 1
    return p


def degree_name(midi: int, root_pc: int) -> str:
    return DEGREE_NAMES[(midi - root_pc) % 12]
