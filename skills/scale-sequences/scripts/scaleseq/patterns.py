# SPDX-License-Identifier: MIT
"""Sequence patterns over a box's notes in pitch order (index 0 = lowest box note, N-1 = highest).

One model covers every pattern here:

  ascent   groups G(i) = [i + o for o in shape], i = 0 .. top  (top = N-1-max(shape))
  turn     optionally the top ascending group's last note is moved (1-2-3-1 -> 1-2-3-2 at the top)
  descent  the ascent played backwards: the RETROGRADE of G(i) (notes reversed), i = top .. desc_stop,
           the top group left out when it is a palindrome (repeat_top=None) or when repeat_top=False,
           and any i in desc_skip left out
  pickup   indices played before the first group (own pickup bar)
  landing  if the line does not already end on index 0, a final index-0 note is appended
           (its length comes from the rhythm), then rests complete the bar

Index notation used in docs/reports: groups written with 0-based box indices, e.g. 4s = [0123][1234]...

Group i is the group built on box note i: G(i) = [i + o for o in shape] (for every built-in pattern,
the group whose lowest note is box index i). The built-in patterns use shape, turn_last and pickup
only. desc_stop and desc_skip are set per section of a file (`stop=N` and `skip=N[+N...]` in
--patterns, Section.desc_stop / Section.desc_skip; see exercise.Section), or by a pattern the user
defines to reproduce an exercise they already have. Such a pattern lives in a pattern file of the
user's own, outside this skill, and is added for one run (`--pattern-file`, add_patterns); it is never
added to the library below (see SKILL.md, "Transferring an exercise").
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Pattern:
    name: str
    shape: tuple[int, ...]
    about: str
    turn_last: int | None = None      # top ascending group: last note -> i + turn_last
    repeat_top: bool | None = None    # None: repeat the top group in the descent unless palindrome
    desc_stop: int = 0                # the descent ends at group desc_stop (0 = at the bottom)
    desc_skip: tuple[int, ...] = ()   # groups the descent leaves out
    pickup: tuple[int, ...] = ()
    land: bool = True                 # append index 0 if the line does not end there
    default_rhythm: str = "8"
    aliases: tuple[str, ...] = field(default=())

    def top(self, n: int) -> int:
        t = n - 1 - max(self.shape)
        if t < 0 or min(self.shape) < 0:
            raise ValueError(f"pattern {self.name}: box of {n} notes is too small")
        return t

    def group(self, i: int) -> list[int]:
        return [i + o for o in self.shape]

    def is_palindrome(self) -> bool:
        return list(self.shape) == list(reversed(self.shape))

    def sections(self, n: int) -> dict[str, list[list[int]]]:
        """{'pickup': [[...]], 'up': [groups], 'down': [groups], 'land': [[0]] or []}"""
        top = self.top(n)
        up = [self.group(i) for i in range(0, top + 1)]
        if self.turn_last is not None:
            up[-1] = up[-1][:-1] + [top + self.turn_last]
        repeat = (not self.is_palindrome()) if self.repeat_top is None else self.repeat_top
        first_down = top if repeat else top - 1
        down = [list(reversed(self.group(i))) for i in self._descent_groups(n, top, first_down)]
        line = [x for g in up + down for x in g]
        land = [[0]] if (self.land and line and line[-1] != 0) else []
        out = {"pickup": [list(self.pickup)] if self.pickup else [], "up": up, "down": down, "land": land}
        for k, gs in out.items():
            for g in gs:
                if any(x < 0 or x >= n for x in g):
                    raise ValueError(f"pattern {self.name}: {k} group {g} outside a box of {n} notes")
        return out

    def _descent_groups(self, n: int, top: int, first_down: int) -> list[int]:
        """The groups the descent plays, top down: first_down .. desc_stop, desc_skip left out (possibly
        none: a line that only goes up). ValueError if desc_stop or desc_skip name a group the descent
        does not have."""
        if self.desc_stop > top:
            raise ValueError(f"pattern {self.name}: the descent cannot stop at group {self.desc_stop}: "
                             f"on a box of {n} notes its groups are 0 to {top}")
        played = range(first_down, self.desc_stop - 1, -1)
        for g in self.desc_skip:
            if g not in played:
                plays = f"groups {first_down} down to {self.desc_stop}" if played else "no group"
                both_ways = " reads the same both ways and" if self.is_palindrome() else ""
                once = f" (its top group{both_ways} is played once, on the way up)" if g == top > first_down else ""
                raise ValueError(f"pattern {self.name}: group {g} is not in the descent: on a box of {n} "
                                 f"notes it plays {plays}{once}")
        return [i for i in played if i not in self.desc_skip]

    def stream(self, n: int) -> list[int]:
        s = self.sections(n)
        return [x for k in ("pickup", "up", "down", "land") for g in s[k] for x in g]

    def notation(self, n: int) -> str:
        s = self.sections(n)
        f = lambda gs: " ".join("[" + ",".join(map(str, g)) + "]" for g in gs)  # noqa: E731
        parts = []
        if s["pickup"]:
            parts.append(f"pickup {f(s['pickup'])}")
        parts.append(f"up {f(s['up'])}")
        parts.append(f"down {f(s['down'])}")
        if s["land"]:
            parts.append(f"land {f(s['land'])}")
        return " | ".join(parts)


PATTERNS: dict[str, Pattern] = {}


def _add(p: Pattern) -> None:
    PATTERNS[p.name] = p


_add(Pattern("scale", (0,), aliases=("1",),
             about="the plain box scale, up and down (top note once)"))
_add(Pattern("thirds", (0, 2), aliases=("3rds",),
             about="box-step thirds: [i,i+2] up, [i+2,i] down"))
_add(Pattern("3s", (0, 1, 2), default_rhythm="8t", aliases=("threes", "123"),
             about="groups of three: [i,i+1,i+2] up, [i+2,i+1,i] down (top group repeated)"))
_add(Pattern("4s", (0, 1, 2, 3), aliases=("fours", "1234"),
             about="groups of four: [i..i+3] up, [i+3..i] down"))
_add(Pattern("6s", (0, 1, 2, 3, 4, 5), default_rhythm="16s", aliases=("sixes",),
             about="groups of six (sextuplets): [i..i+5] up, [i+5..i] down"))
_add(Pattern("1231", (0, 1, 2, 0), turn_last=1,
             about="1-2-3-1 up (top turned 1-2-3-2), retrograde 1-3-2-1 down to [0,2,1,0]"))
_add(Pattern("upper-neighbor3", (0, 1, 0), default_rhythm="8t",
             about="upper-neighbour triplets: [i,i+1,i] up and back"))
_add(Pattern("neighbor3", (1, 0, 1), default_rhythm="8t", pickup=(0,), aliases=("lower-neighbor",),
             about="lower-neighbour triplets: pickup [0], then [k,k-1,k] up to the top and back "
                   "(top group once), land on [0]"))


ALIASES = {a: p.name for p in PATTERNS.values() for a in p.aliases}


def get_pattern(name: str) -> Pattern:
    key = ALIASES.get(name, name)
    if key not in PATTERNS:
        raise KeyError(f"unknown pattern {name!r}; known: {', '.join(PATTERNS)}")
    return PATTERNS[key]


# ---------- patterns defined outside the library (a user's pattern file, a private fixture) ----------

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")  # usable in --patterns name[:rhythm],...
_INTS = ("shape", "desc_skip", "pickup")


def _is_int(x: object) -> bool:
    return type(x) is int  # not bool


def _field_ok(k: str, v: object) -> bool:
    """JSON value `v` has the type Pattern field `k` needs (box indices/offsets: ints >= 0)."""
    if k in _INTS:
        return (isinstance(v, list) and all(_is_int(x) and x >= 0 for x in v)
                and (k != "shape" or len(v) > 0))
    if k == "aliases":
        return isinstance(v, list) and all(isinstance(a, str) for a in v)
    if k == "turn_last":
        return v is None or _is_int(v)
    if k == "repeat_top":
        return v is None or isinstance(v, bool)
    if k == "desc_stop":
        return _is_int(v)
    if k == "land":
        return isinstance(v, bool)
    return isinstance(v, str)  # about, default_rhythm


def add_patterns(spec: object, source: str) -> list[str]:
    """Add patterns defined outside the library to it, for this process only.

    spec: {"<name>": {"shape": [0, 2, 1], <any other Pattern field>, ...}, ...} -- lists for the tuple
    fields, e.g. "desc_skip": [2]. Names must be new and usable in --patterns. Nothing is added unless
    every definition is valid (ValueError, prefixed with `source`). Returns the names added."""
    from .exercise import DURS  # exercise imports this module

    if not isinstance(spec, dict):
        raise ValueError(f'{source}: must be a JSON object {{"<name>": {{"shape": [...], ...}}, ...}}')
    fields = {f.name for f in dataclasses.fields(Pattern)} - {"name"}
    taken = set(PATTERNS) | set(ALIASES)
    new: list[Pattern] = []
    for name, d in spec.items():
        if not NAME.match(name):
            raise ValueError(f"{source}: pattern name {name!r} must be letters, digits, '.', '_' or '-'")
        if name in taken:
            raise ValueError(f"{source}: pattern {name!r} is already in the library; use another name")
        if not isinstance(d, dict):
            raise ValueError(f"{source}: pattern {name!r} must be a JSON object of Pattern fields")
        if set(d) - fields:
            raise ValueError(f"{source}: pattern {name!r} has unknown fields {sorted(set(d) - fields)}; "
                             f"fields: {', '.join(sorted(fields))}")
        if "shape" not in d or not _field_ok("shape", d["shape"]):
            raise ValueError(f"{source}: pattern {name!r} needs a shape: a list of box-index offsets "
                             "(0 or more), e.g. [0, 1, 2]")
        bad = sorted(k for k, v in d.items() if not _field_ok(k, v))
        if bad:
            raise ValueError(f"{source}: pattern {name!r}: wrong type for {', '.join(bad)}")
        if d.get("default_rhythm", "8") not in DURS:
            raise ValueError(f"{source}: pattern {name!r}: unknown default_rhythm {d['default_rhythm']!r}; "
                             f"valid rhythms: {', '.join(DURS)}")
        for a in d.get("aliases", []):
            if a in taken or a == name or not NAME.match(a):
                raise ValueError(f"{source}: alias {a!r} of pattern {name!r} is already in the library "
                                 "or not a usable name")
        kw = {k: tuple(v) if isinstance(v, list) else v for k, v in d.items()}
        new.append(Pattern(name=name, **{"about": f"defined in {source}", **kw}))
        taken |= {name, *new[-1].aliases}
    for p in new:
        _add(p)
        ALIASES.update({a: p.name for a in p.aliases})
    return [p.name for p in new]


def load_pattern_file(path: str) -> list[str]:
    """add_patterns() from a JSON pattern file (the user's own, kept outside this skill)."""
    try:
        spec = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: cannot read the pattern file: {e}") from None
    return add_patterns(spec, source=str(path))
