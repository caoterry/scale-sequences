# scale-sequences

A [Claude Code](https://code.claude.com) skill that writes **Guitar Pro `.gp5` practice files of scale
sequences** -- 3s, 4s (1234), 1231, neighbour-note triplets, 6s, thirds, the plain scale -- played
through a **scale box** (shape / position), in any key, optionally with the blue notes played as
**half-step bends** -- for the plain scale with **one pick per bend**, the way the bends are played.
Ask for an exercise in plain words; you get a file you can open, loop and slow
down in any Guitar Pro or alphaTab-based player, and the skill refuses to hand over a file it could
not verify.

Built in: the five A minor blues boxes named after the scale degree of their lowest note on the
low E string -- the **b7 shape** (frets 2-6), the **root shape** (5-8), the **b3 shape** (7-11), the
**4 shape** (9-13) and the **5 shape** (12-16) -- each transposable to any key.

## Why you can trust the files

No note is typed by hand, by you or by Claude. Claude only turns your request into command-line
options; scripts build every note and check it:

1. **The box is checked.** Its positions, sorted by pitch, must be a gap-free run of the scale: every
   position a scale note, one position per pitch, no scale tone skipped, fingers ascending with the
   frets.
2. **The pattern is a recipe over box indices.** The box's notes are numbered 0..N-1 from lowest to
   highest, and a sequence is defined on those numbers (4s = `[0,1,2,3] [1,2,3,4] ...` up, then the
   same groups reversed back down). The same recipe therefore runs on any box, and what changes from
   box to box is only which string and fret each index is.
3. **The plan is checked** before anything is written: every bar adds up to its time signature;
   every note is a position of the box (or the fret below a blue note, for a bend) and sounds the
   box's note; bends are where the chosen bend mode puts them and nowhere else (with one pick per
   bend: every tie continues the note before it, every pre-bend is released, no bend is picked
   again, the bent-to note's own fret is never played); each section's note order equals the
   pattern's index stream; rhythm per role (pickup, line, landing) is as specified; rests appear
   only after the line.
4. **The file is read back** with pyguitarpro and must equal the plan beat by beat, ties and bend
   points included.
5. **alphaTab parses, plays and renders it.** [alphaTab](https://alphatab.net) (a real Guitar Pro
   engine, the one many web players use) loads the file in Node; its own reading must equal the plan
   -- bars, time signatures, markers, every beat's duration and tuplet, every note's string, fret,
   tie, bend shape (kept as written) and pitch. The MIDI its player generates must have one note-on
   per pick, and each bend must reach its pitch within 1/6 of the note and hold it. The rendered
   score must show a ½ bend label on exactly the notes that bend up or are pre-bent.

Any failed check exits with an error and leaves no file behind; an existing file is never
overwritten unless you ask.

## Requirements

- [Claude Code](https://code.claude.com) (the skill runs local scripts, so it needs a shell with uv
  and Node; it is not meant for environments without them, such as claude.ai chat).
- [uv](https://docs.astral.sh/uv/) (tested with 0.11.13). The script pins its one Python dependency
  inline and is locked in `scaleseq_cli.py.lock`; uv installs it on first run, no virtualenv to manage.
  Python 3.10+ (uv can download one if none is installed).
- Node.js 18+ (tested with 25.9), for the alphaTab check (alphaTab is installed once into the skill
  directory with `npm ci`).

## What it runs and fetches

- **uv** runs `skills/scale-sequences/scripts/scaleseq_cli.py` with `uv run --locked --script`. On
  first run it downloads [pyguitarpro](https://pypi.org/project/PyGuitarPro/) 0.11 and its dependency
  attrs from PyPI (exact versions and hashes in the lockfile) and, if needed, a Python interpreter.
- **`npm ci`** installs alphaTab (pinned to 1.8.3 in `package-lock.json`) into the skill directory,
  once.
- **Files:** it writes only the `.gp5` you asked for (via a temporary file next to it that is
  removed afterwards), besides uv's package cache and the skill's `node_modules`. It reads no other
  file of yours unless you point it at a reference to compare with.
- No other network calls and no telemetry: the scripts contain no network code, upload nothing and
  collect no personal data.

## Install

As a plugin (this repo is also a single-plugin marketplace):

```
/plugin marketplace add caoterry/scale-sequences
/plugin install scale-sequences@scale-sequences
```

Or as a plain skill -- copy or symlink the skill directory into your skills folder:

```
git clone https://github.com/caoterry/scale-sequences
ln -s "$PWD/scale-sequences/skills/scale-sequences" ~/.claude/skills/scale-sequences
npm ci --prefix ~/.claude/skills/scale-sequences      # alphaTab, for the final check
```

(With the plugin install, the skill's setup step has Claude run the same `npm ci` the first time
alphaTab is needed.)

## Use

In Claude Code, just ask:

```
> give me the 4s sequence through the root shape of A minor blues, eighth notes, 80 bpm
> transfer the 1234 sequence to the b3 shape
> add half-step bends on the blue notes
> the A minor blues scale through the root shape, half-step bends, one pick per bend
> same thing in E instead of A
> 3s in triplets and 6s in sextuplets through the b7 shape, at 70 bpm
> the 1231 sequence in all five boxes, with and without bends
> 3s through the 5 shape, but only come back down as far as group 3
> thirds through the 4 shape, leaving groups 2 and 5 out on the way down
```

Then open the `.gp5` in Guitar Pro or any alphaTab-based player -- for example, drag it into
[woodshed-web.fly.dev](https://woodshed-web.fly.dev) (free; plays, loops and slows down; no account
needed to play).

What a run prints (here "the A minor blues scale through the root shape, half-step bends, one pick
per bend", at 70 bpm):

```
OK scale - root shape, one-pick half-step bends.gp5
  root shape (A), 7 bars, 27 notes, 23 picks, 4 half-step bends (2 released)
  scale: scale in 4, 7 bars, 27 notes
  check plan (bar fill, pitch class, in-box, bends, one pick per bend, pattern, rhythm): ok
  check read-back (pyguitarpro) exact: ok
  check alphaTab parse + MIDI (picks, bend timing) + render (bend labels): ok
```

You can also run the script yourself (`--help` on each command):

```
S=skills/scale-sequences/scripts/scaleseq_cli.py
uv run --locked --script $S boxes --key E            # box diagrams: scale degree / suggested finger
uv run --locked --script $S patterns                 # the pattern library in index notation
uv run --locked --script $S generate --box b3 --patterns 1234 --bend-blue-notes -o b3-1234.gp5
uv run --locked --script $S generate --box root --patterns scale:4 --one-pick-bends -o root-scale.gp5
uv run --locked --script $S generate --box root --patterns 3s:8t,6s:16s --tempo 70 -o root.gp5
uv run --locked --script $S generate --box b7 --patterns 1231,thirds --key E -o b7-E.gp5
uv run --locked --script $S generate --box 5 --patterns 3s:8t:stop=3,thirds:16:skip=2+5 -o 5-shape.gp5
```

Options: `--box b7|root|b3|4|5`; `--key E` (lowest placement with no open strings) or `--fret-offset N`;
`--patterns name[:rhythm][:stop=N][:skip=N[+N...]],...` (one section per pattern, in that order, each
with its own marker) with rhythms `1 2 4 8 16 4t 8t 16t 16s` (t = triplet, 16s = sextuplet) and the
descent options `stop` and `skip` (see "Changing the way down" below) -- a pattern may appear more than
once, e.g. `3s:8t,3s:16s`, and its markers then name the rhythm ("3s in eighth triplets", "3s in
sextuplets"); `--one-pick-bends` or `--bend-blue-notes` (see "Half-step bends" below); `--tempo`; `--title`; `--fingering` (writes the suggested
left-hand fingers; off by default because it adds numbers to the notation staff); `--force` to replace
an existing file; `--json` for a machine-readable report; `--pattern-file FILE` for patterns of your
own (see below).

### Half-step bends

- `--one-pick-bends` plays each half-step bend with **one pick**. Going up, you pick the lower note,
  and a tied note bends it up into the next scale note. Going down, you pick a pre-bend (it sounds
  the upper note), and a tied note releases it into the next one. Which two notes share a fret comes
  from the box's fingering. If the blue note's string holds D-D#-E on adjacent frets (fingers 1-2-3),
  the middle finger bends D# up to E and E's own fret is never played; otherwise the ring finger
  bends D up to D#. The index and little fingers never bend. Every scale note keeps its own beat.
  This needs every bent-to note next to the note it is bent from, no held bend picked again and no
  pre-bend right after a note on its own string. On the built-in boxes that is the plain `scale`
  pattern (e.g. `--patterns scale:4`). Any other pattern is refused, with the notes that cannot be
  played that way named.
- `--bend-blue-notes` writes every blue note as the fret below, bent up, and picks every note. In
  sequences that is a bend every few notes, each picked again.

### Patterns

N = number of notes in the box; groups are written with box indices, 0 = lowest note.

| pattern | up | down |
|---|---|---|
| `3s` | `[0,1,2] [1,2,3] ...` | `[N-1,N-2,N-3] ... [2,1,0]` |
| `4s` / `1234` | `[0,1,2,3] [1,2,3,4] ...` | `[N-1..N-4] ... [3,2,1,0]` |
| `1231` | `[0,1,2,0] [1,2,3,1] ...`, top group turned 1-2-3-2 | retrograde `1-3-2-1` down to `[0,2,1,0]` |
| `neighbor3` | pickup `[0]`, then `[1,0,1] [2,1,2] ...` | `... [1,0,1]`, lands on `[0]` |
| `upper-neighbor3` | `[0,1,0] [1,2,1] ...` | `... [0,1,0]` |
| `6s` | `[0..5] [1..6] ...` | reversed |
| `thirds` | `[0,2] [1,3] ...` | `[N-1,N-3] ... [2,0]` |
| `scale` | `0 1 2 ... N-1` | `N-2 ... 0` |

### Changing the way down: `stop` and `skip`

Every pattern is a chain of groups, numbered from the bottom of the box starting at 0: group N is the
group built on box note N (in 3s, group 3 is `[3,4,5]` going up and `[5,4,3]` coming down). Two options,
written after the rhythm, change the descent of one section without defining a new pattern:

- `stop=N` ends the descent at group N instead of the bottom group. The line then drops to the box's
  lowest note (a quarter note) to finish. Use it to work the upper part of the box on the way down, or
  to keep a long sequence short.
- `skip=N` leaves group N out of the descent (several: `skip=N+M`). Coming down, the line goes from
  the group above straight to the group below -- a jump that breaks the sequence's regular step, to
  vary a run you know by heart.

For example `--patterns 3s:8t:stop=3,thirds:16:skip=2+5` writes 3s in triplets that come down only
to group 3 (`... [6,5,4] [5,4,3]`, then `[0]`), then thirds in sixteenths without `[4,2]` and `[7,5]` on
the way down. Each section's marker names its options ("3s stop=3 (5 shape)"). `patterns --n <box
size>` lists every pattern's groups, and `--json` reports each section's groups as played
(`index_notation`). A group the descent does not have -- above the top of the box, below the `stop`, or
a top group that reads the same both ways (played once, on the way up) -- is refused, with the groups
the descent does play named. In Python: `Section(label, pattern, note=..., desc_stop=N,
desc_skip=(N, M))` (`skills/scale-sequences/scripts/scaleseq/exercise.py`).

## What is verified, and what is not

| | |
|---|---|
| **Checked against the box and pattern definitions** | every note is a box position and sounds the box's pitch; pitch classes are in the scale; each section plays the pattern's exact index order; bends exactly where the bend mode puts them (one pick per bend: ties, pre-bends and releases follow the bend pairs) |
| **Checked by arithmetic** | every bar adds up to its time signature; rhythm per role; rests only after the line; markers and double bars on the right bars |
| **Checked against two independent parsers** | the written file, read back by pyguitarpro and by alphaTab, equals the plan beat by beat (duration, tuplet, rest, string, fret, tie, bend type and points, sounding pitch incl. bend, bars, time signatures, markers, title, tempo) |
| **Checked in alphaTab's MIDI** | one note-on per pick at the right tick and key, held through its tied notes; every bend and release reaches its pitch within 1/6 of the note and holds it |
| **Checked in a render** | alphaTab's rendered score has a ½ bend label on exactly the notes that bend up or are pre-bent |
| **Not checked** | how it sounds (playback audio; the MIDI events are checked, not the sound); how a player's own re-saved copy looks; whether the suggested fingering suits your hand |

The test suite also regenerates small exercises written out by hand from the pattern definitions
(e.g. 4s on a 6-note box, string and fret for every note), and the one-pick-bend scale on each built-in
box written out by hand beat by beat (fret, tie, bend). It checks that the comparisons against a
reference catch a wrong fret, a wrong rhythm and a missing bar, and that the alphaTab MIDI check
catches a bend that ramps across the whole note.

## Scope / limitations

- Standard tuning, 6-string guitar, one track, 4/4 (a pickup gets a bar of its own).
- Five built-in boxes, all minor blues (A, transposable). Any other box needs an entry in
  `BOX_SPECS` (`skills/scale-sequences/scripts/scaleseq/boxes.py`); a box that is not a gap-free
  scale run is refused. The scales it knows are minor and major blues, minor and major pentatonic,
  natural minor and major; besides the built-in boxes, only a minor pentatonic box is covered by the
  tests.
- Bends: only half-step bends, only around the blue note (b5), only when the box has the fret below
  on the same string (otherwise the run stops with an error). With one pick per bend, only patterns
  where every bent-to note is next to the note it is bent from (on the built-in boxes, the plain
  scale), and only bends with the middle or ring finger.
- Every sequence ends on the box's lowest note (index 0), so the index pattern stays identical across
  boxes; on the b7, b3, 4 and 5 shapes that is not the root (G, C, D and E in A).
- The key signature is the root's major key (A minor blues: three sharps), as blues charts are
  usually printed.
- alphaTab-based players draw a default "f" dynamic at the first note; the file itself writes no
  dynamic (no note velocity).

## Comparing with an exercise you already have

If you have an exercise as reads of a page (a TAB read and a staff read in the flat JSON layout
described in `compare_reads` in `skills/scale-sequences/scripts/scaleseq/verify.py`),
`analyze --box <box> --reads DIR` names the library patterns that reproduce each section. Then
`generate --expect-reads DIR`, or `--expect-gp5 FILE` for an exercise you have as a `.gp5`, fails
unless the result is identical (against a `.gp5`, only the notes the run bends may differ). Prove a pattern on
the box the reference is in before transferring it to another box.

A section that differs from a library pattern only in its way down may need just `stop` or `skip`
(see "Changing the way down"); `analyze` matches the library patterns as they are, without options.
If no library pattern matches, define the one you need in a JSON pattern file of your own, kept next
to your reference rather than in the skill, and pass it with `--pattern-file` (to `generate`,
`analyze` and `patterns`):

```
{"132": {"shape": [0, 2, 1], "default_rhythm": "8t"}}
```

Each entry takes the fields of `Pattern` in `skills/scale-sequences/scripts/scaleseq/patterns.py`:
`shape` (required) and optionally `turn_last`, `repeat_top`, `desc_stop`, `desc_skip`, `pickup`,
`land`, `default_rhythm`, `about` and `aliases`, with lists for its tuple fields (`desc_stop` and
`desc_skip` are what `stop` and `skip` set; a section's option replaces the pattern's own value). A
name that is already in the library, an unknown field or a wrong type is refused. The patterns are
added for that run only; nothing is written into the skill.

## Copyright

The repository contains no third-party music: the boxes are scale positions, the patterns are
generic practice sequences, and every exercise is generated from them. If you check a pattern
against a transcription of a book you own, keep that transcription -- and what reproduces it: the
`--patterns` list with its rhythms and options and any pattern you defined for it (your
`--pattern-file`) -- outside the repository; `tests/private_reference.py` reads them from the directory
named in an environment variable for exactly that reason.

## Support

Questions and bug reports: [GitHub Issues](https://github.com/caoterry/scale-sequences/issues). A
failed run names each failed check; please paste that output.

## Development

```
npm ci --prefix skills/scale-sequences
uv run --locked --script tests/run_tests.py -q      # the test suite, with the same pinned versions as the script
SCALE_SEQUENCES_PRIVATE_FIXTURE=/path/to/private/fixture uv run --locked --script tests/private_reference.py
```

Without uv: `pip install -r requirements-dev.txt && python -m pytest`. Dependencies are exact pins
in each script's `# /// script` block, locked with `uv lock --script <file>`; `requirements*.txt`
repeat them for pip, and `tests/test_pins.py` fails on a stale lock or pins that disagree.

`tests/test_pins.py` (the pin and lockfile checks) needs Python 3.11+, because it reads TOML with
`tomllib`; on Python 3.10 pytest skips it. The rest of the suite runs on 3.10. With uv you can choose
the interpreter, which downloads it if needed:
`uv run --locked --python 3.12 --script tests/run_tests.py -q`.

`tests/private_reference.py` regenerates an exercise you keep outside the repository and compares it
note for note: the directory in `SCALE_SEQUENCES_PRIVATE_FIXTURE` holds the reads, the list of
sections (patterns and rhythms) that should reproduce them and, optionally, an earlier `.gp5` to match
byte for byte (layout in the script's docstring). Without the variable it does nothing.

## Changelog

- 0.3.0 -- all five A minor blues boxes (new: the 4 and 5 shapes); per-section descent options
  `stop=N` and `skip=N[+N...]` in `--patterns`.
- 0.2.0 -- half-step bends with one pick per bend (`--one-pick-bends`).
- 0.1.0 -- first release: verified `.gp5` scale-sequence exercises through the b7, root and b3 shapes.

## License

MIT -- see [LICENSE](LICENSE). alphaTab, installed by `npm ci`, is MPL-2.0.

---
Made by [Terry Cao](https://github.com/caoterry) · see also: [Fender Tone Master Pro cheat sheet](https://caoterry.github.io/tmp-atlas/) (every model measured)
