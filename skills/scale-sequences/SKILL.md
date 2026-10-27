---
name: scale-sequences
description: Generate verified Guitar Pro (.gp5) practice files of scale SEQUENCES (3s, 4s/1234, 1231, neighbour triplets, 6s, thirds, plain scale) played through a scale BOX/shape/position -- the A minor blues b7, root and b3 shapes are built in and transpose to any key -- optionally with every blue note (b5) played as a half-step bend. Use when the user wants to practise a sequence in a box, transfer a sequence exercise to another box/shape/position or key, add half-step bends to a blues-scale exercise, or open such an exercise in a Guitar Pro / alphaTab player. Trigger on scale sequence/sequencing/box/shape/position/1234/half-step bend/blue note bend/b7 shape/root shape/b3 shape.
---

# scale-sequences

Scripts build every note; nothing is typed by hand. A box's notes, sorted by pitch, are indexed
0..N-1 (0 = lowest note of the box). A pattern is a recipe over those indices, so the same recipe
runs on any box. Every file is checked (plan, read-back, alphaTab parse and render) before it is
moved into place. If a check fails, no file is written.

`${CLAUDE_SKILL_DIR}` is this skill's directory. Python runs through `uv run --locked --script`
(dependency `pyguitarpro==0.11` pinned inline and locked in `scripts/scaleseq_cli.py.lock`; the script
re-execs itself with `python -I`). If uv reports that the lockfile is missing or out of date, stop and
tell the user -- do not drop `--locked` or re-lock.

## Setup (once per machine)
`test -d "${CLAUDE_SKILL_DIR}/node_modules/@coderline/alphatab" || npm ci --prefix "${CLAUDE_SKILL_DIR}" --no-audit --no-fund`
(needs `uv` and `node`; if either is missing, tell the user how to install it and stop). The alphaTab
check uses `$ALPHATAB_MJS` if set, else the skill's own `node_modules` (alphaTab 1.8.3).

## Commands

Run every command as `uv run --locked --script "${CLAUDE_SKILL_DIR}/scripts/scaleseq_cli.py" <command> ...`:

```
scaleseq_cli.py boxes [--key C]          # box diagrams: scale degree / suggested finger per cell
scaleseq_cli.py patterns [--n 14]        # pattern library in index notation, rhythms
scaleseq_cli.py generate --box b7 --patterns 4s,3s:8t,1231:16 -o "<out>.gp5" \
    [--bend-blue-notes] [--tempo 80] [--key A | --fret-offset N] \
    [--title T] [--subtitle S] [--plain-markers] [--fingering] [--force] [--json] \
    [--expect-reads DIR] [--expect-gp5 FILE] [--pattern-file FILE]
scaleseq_cli.py analyze --box root --reads DIR   # which library pattern reproduces a reference
```
`patterns` and `analyze` also take `--pattern-file FILE` (see "Transferring an exercise").
- `--box`: `b7`, `root`, `b3` (ids `blues-b7`, `blues-root`, `blues-b3`). `--key E` moves the box to
  the lowest placement with no open strings. `--fret-offset` sets the shift directly.
- `--patterns name[:rhythm],...` (required): rhythms are `1 2 4 8 16 4t 8t 16t 16s` (t = triplet,
  16s = sextuplet). Each pattern has a default rhythm. Each pattern becomes one section of the file, in
  the order given, labelled with its name. A pattern may be given more than once (e.g. `3s:8t,3s:16s`
  to practise two rhythms); its sections are then labelled with the rhythm too ("3s in eighth
  triplets", "3s in sextuplets"), plus "#1", "#2" if pattern and rhythm repeat. Pickup notes are
  eighths and landing notes quarters.
- `--bend-blue-notes`: each b5 is written as the note one fret below on the same string, bent up
  half a step. The box must contain that fret; otherwise the run stops with an error.
- `--fingering`: writes the box's suggested left-hand fingers into the file. It is off by default
  because it adds numbers to the notation staff.
- `--expect-reads` / `--expect-gp5`: the run fails unless the result equals a reference
  (`--expect-gp5` accepts only bent blue notes as differences).
- Output names: put the box, key and "half-step bends" in the file name when the user does not give
  one (e.g. `A minor blues sequences - b3 shape, half-step bends.gp5`), next to where they work.
- The output is never overwritten without `--force`.

## Boxes (A minor blues; finger = suggested fingering)

Named after the scale degree of the lowest note on string 6.

| shape | frets | lowest note | string 6 .. 1 (fret/finger) |
|---|---|---|---|
| b7 | 2-6 | G | 6: 3/1 5/3 · 5: 3/1 5/3 6/4 · 4: 2/1 5/4 · 3: 2/1 5/4 · 2: 3/1 4/2 5/3 · 1: 3/1 5/3 |
| root | 5-8 | A | 6: 5/1 8/4 · 5: 5/1 6/2 7/3 · 4: 5/1 7/3 · 3: 5/1 7/3 8/4 · 2: 5/1 8/4 · 1: 5/1 8/4 |
| b3 | 7-11 | C | 6: 8/1 10/3 11/4 · 5: 7/1 10/4 · 4: 7/1 10/4 · 3: 7/1 8/2 9/3 · 2: 8/1 10/3 · 1: 8/1 10/3 11/4 |

To add a box, append it to `BOX_SPECS` in `scripts/scaleseq/boxes.py` in any key. `get_box` rejects
a box unless every pitch class is in the scale and the positions, sorted by pitch, form a strictly
ascending run with no skipped scale tone. Fingers must be 1-4 and ascend with the frets on each
string. Do not work around a rejected box. Re-read the diagram and fix the spec.

## Patterns (index notation, N = box size)

Ascent groups `G(i) = [i+o for o in shape]` for `i = 0..N-1-max(shape)`. The descent plays the
retrograde of those groups back down. A palindromic top group is not repeated. If the line does not
end on 0, a landing note `[0]` is added, then rests complete the bar.

| pattern | shape | notes |
|---|---|---|
| `neighbor3` | (1,0,1) | pickup [0]; lower-neighbour triplets [k,k-1,k]; lands on [0] (quarter) |
| `3s` | (0,1,2) | [i,i+1,i+2] up, [i+2,i+1,i] down |
| `4s` / `1234` | (0,1,2,3) | [i..i+3] up, [i+3..i] down |
| `1231` | (0,1,2,0) | top group turned 1-2-3-2, retrograde 1-3-2-1 down to [0,2,1,0] |
| `upper-neighbor3`, `6s`, `thirds`, `scale` | | see `patterns` |

### Transferring an exercise the user has as a file or reads
What reproduces a user's reference -- the `--patterns` list with its rhythms, and any pattern defined
for it -- is the user's recipe. It lives in the user's own files, never in this skill: do not add it
to `scripts/scaleseq/patterns.py` or anywhere in this skill's directory or repository.
1. Run `analyze --box <box it is in> --reads DIR` (flat `tab_read.json`). It lists the library
   patterns that reproduce each section exactly. For a `.gp5`, read its (string, fret) per note with
   pyguitarpro and map them to box indices with `Box.index_of_sf()` the same way.
2. If every section matches, the recipe is just the `--patterns` list. If a section needs a pattern
   the library lacks, write it into a pattern file in the user's own folder, next to their reference
   (for example `<their folder>/patterns.json`), and pass `--pattern-file <that file>`:
   `{"<new name>": {"shape": [0, 2, 1], "default_rhythm": "8t"}}` -- any `Pattern` field
   (`shape` required; `turn_last`, `repeat_top`, `desc_stop`, `desc_skip`, `pickup`, `land`,
   `default_rhythm`, `about`, `aliases`; lists for the tuple fields). The name must not be a library
   pattern's. `analyze --pattern-file` then lists it too. Prove the recipe with
   `generate --box <same box> [--pattern-file F] --patterns ... --expect-reads DIR` (or `--expect-gp5`)
   before using it on another box. Never use a pattern on a new box unless it reproduces the reference
   exactly.
3. Run `generate --box <new box>` with the same pattern file, patterns and rhythms. Tell the user the
   command line, so they can keep it with their reference (e.g. in a note or script in that folder).
The reference itself (e.g. reads of a method book page) also stays where it is: never copy it into
this skill's directory or repository.

## Musical choices the scripts make (tell the user when relevant)
- **End on the lowest box note (index 0).** On the root box this is the root. On other boxes it is
  the box's lowest note (b7 box: G, b3 box: C). This keeps the index pattern identical. Resolving to
  A would mean leaving the box or leaping (in the b3 box, A is index 5).
- **Half-step bends** use `--bend-blue-notes`. Every b5 (D# in A) gets its own pick attack: pick the
  4th (D) one fret below and bend it up ½. The note is written as GP "bend" (attack at D, rises to
  D#, holds). A neighbouring D on the same fret is a separate unbent note, so "D# D D#" is bend,
  release, pick D, bend again. No pre-bends and no bend-release inside one note, which keeps one
  attack per original note and the same rhythm. In the root box the bends are string 5 fret 5
  (index finger: pull toward the floor) and string 3 fret 7 (ring finger, backed up by the middle).
- Files use 4/4 with the pickup in its own bar (n/8). Markers name each section, with a double bar
  at each section's end, and the key signature is the root's major key (A = 3 sharps).

## Checks (all deterministic; any failure exits 1 and writes no file)
- box: pitch classes, gap-free ascending scale run, fingers.
- plan: every bar sums to its time signature. Every note is a box position (or the bend source of a
  blue note), its sounding pitch equals the box note, and its pitch class is in the scale. Bends are
  on exactly the blue notes when asked, and nowhere otherwise. Each section's index stream equals
  `pattern.stream(N)`. The rhythm per role (pickup, line, landing) matches. Rests appear only after
  the line. Markers and double bars are on the right bars.
- read-back (pyguitarpro): the file equals the plan beat by beat. Voice 2 is one *empty* full-bar
  beat.
- alphaTab: its own parse equals the plan, including bars, time signatures, markers, double bars,
  rest/duration/tuplet per beat, string/fret, and sounding pitch including the bend. The render
  check renders the score in Node and confirms a ½ label on exactly the bent notes (matched by
  alphaTab beat id).
- Not checked: playback audio, and how a player's own saved copy looks after it re-exports the file.
  Do not play audio to check.
- Preview: `node "${CLAUDE_SKILL_DIR}/scripts/alphatab_check.mjs" "${CLAUDE_SKILL_DIR}/node_modules/@coderline/alphatab/dist/alphaTab.mjs" file.gp5 --html preview.html`
  writes a standalone page of alphaTab's render. Serve it from localhost to look at it.

## GP5 conventions (alphaTab-safe)
Every bar's unused voice 2 holds one beat with status **empty**. A zero-beat voice crashes alphaTab,
and a rest-status filler draws a stray rest in every bar. No note velocity is written. alphaTab
still draws its default "f" at the first note; that mark comes from the player, not the file. The
half-step bend is `BendType.bend` with points (0,0) (3,2) (12,2): pyguitarpro quarter tones, which
the file stores as 50 = one semitone.

## Hand-over
Report the file path, box, key, bars, notes, bends and every check line from the run. Tell the user
the file opens in Guitar Pro or any alphaTab-based player; for example they can drag it onto
https://woodshed-web.fly.dev (free; plays, loops and slows down; no account needed to play).

## Opening the file in woodshed (only when the user asks)
The user can simply drag the `.gp5` onto https://woodshed-web.fly.dev. If they ask you to do it
with a browser tool:
1. Open https://woodshed-web.fly.dev in a new tab.
2. Load the file through the page's `input[type=file]` (accepts `.gp5`): find it with the browser
   tool's `find`/`read_page`, then upload the absolute path with its file-upload action. Wait until
   the score renders and check that the title and first bars are right.
3. Saving it to the user's library (the "Save a copy" button) needs the user to be signed in and is
   done only when they asked for it. Reopen the saved copy and confirm the bars, notes and bend labels
   survived.
4. Never sign in, create an account or type credentials. If the page shows the user signed out and a
   save was asked for, stop and ask them to sign in themselves.

## Copyright
This skill contains only generic machinery: boxes, generic pattern recipes and scripts. Exercises it
writes are generated from those recipes. When a user checks a pattern against a transcription of
material they own, the transcription stays outside the skill and repository, and so does everything
that reproduces it: the `--patterns` list with its rhythms and any pattern defined for it stay in the
user's own files (a pattern file passed with `--pattern-file`, a note or script next to the
reference) and are never added to this skill or committed. The private regression test reads them from
a directory named in an environment variable for the same reason.
