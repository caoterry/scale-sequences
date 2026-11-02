---
name: scale-sequences
description: Generate verified Guitar Pro (.gp5) practice files of scale SEQUENCES (3s, 4s/1234, 1231, neighbour triplets, 6s, thirds, plain scale) played through a scale BOX/shape/position -- the five A minor blues shapes (b7, root, b3, 4 and 5) are built in and transpose to any key -- optionally with half-step bends on the blue notes (b5), including the plain scale with ONE pick per bend (bend up into the next note, pre-bend and release on the way down); a section's descent can stop early or leave groups out. Use when the user wants to practise a sequence in a box, transfer a sequence exercise to another box/shape/position or key, add half-step bends to a blues-scale exercise, or open such an exercise in a Guitar Pro / alphaTab player. Trigger on scale sequence/sequencing/box/shape/position/1234/half-step bend/blue note bend/one pick per bend/pre-bend/b7 shape/root shape/b3 shape/4 shape/5 shape.
---

# scale-sequences

Scripts build every note; nothing is typed by hand. A box's notes, sorted by pitch, are indexed
0..N-1 (0 = lowest note of the box). A pattern is a recipe over those indices, so the same recipe
runs on any box. Every file is checked (plan, read-back, alphaTab parse, MIDI and render) before it
is moved into place. If a check fails, no file is written.

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
    [--bend-blue-notes | --one-pick-bends] [--tempo 80] [--key A | --fret-offset N] \
    [--title T] [--subtitle S] [--plain-markers] [--fingering] [--force] [--json] \
    [--expect-reads DIR] [--expect-gp5 FILE] [--pattern-file FILE]
scaleseq_cli.py analyze --box root --reads DIR   # which library pattern reproduces a reference
```
`patterns` and `analyze` also take `--pattern-file FILE` (see "Transferring an exercise").
- `--box`: `b7`, `root`, `b3`, `4`, `5` (ids `blues-b7`, `blues-root`, `blues-b3`, `blues-4`,
  `blues-5`). `--key E` moves the box to the lowest placement with no open strings.
  `--fret-offset` sets the shift directly.
- `--patterns name[:rhythm][:stop=N][:skip=N[+N...]],...` (required): rhythms are
  `1 2 4 8 16 4t 8t 16t 16s` (t = triplet, 16s = sextuplet). Each pattern has a default rhythm. The
  options after the rhythm change that section's way down (see "Changing the way down" below), e.g.
  `3s:8t:stop=3`, `thirds:skip=2+5`. Each pattern becomes one section of the file, in
  the order given, labelled with its name. A pattern may be given more than once (e.g. `3s:8t,3s:16s`
  to practise two rhythms); its sections are then labelled with the rhythm too ("3s in eighth
  triplets", "3s in sextuplets"), plus "#1", "#2" if pattern and rhythm repeat. A section with options
  is labelled with them ("3s stop=3"). Pickup notes are eighths and landing notes quarters.
- `--one-pick-bends`: half-step bends with one pick per bend (see "Half-step bends" below). Use it
  for the plain scale (`--patterns scale:4`, one quarter per note). It works only where every
  bent-to note is next to the note it is bent from, no held bend would be picked again and no
  pre-bend comes right after a note on its own string (only a rest gives time to pre-bend). On the
  built-in boxes only `scale` qualifies; any other pattern stops with an error naming the notes.
- `--bend-blue-notes`: each b5 is written as the note one fret below on the same string, bent up
  half a step, and every note is picked. The box must contain that fret; otherwise the run stops
  with an error. Within sequences this puts a bend every few notes, each picked again.
- `--fingering`: writes the box's suggested left-hand fingers into the file. It is off by default
  because it adds numbers to the notation staff.
- `--expect-reads` / `--expect-gp5`: the run fails unless the result equals a reference
  (`--expect-gp5` accepts only the notes the run bends as differences: same string, bent, ending on
  the reference note's pitch).
- Output names: put the box, key and "half-step bends" (or "one-pick half-step bends") in the file
  name when the user does not give one (e.g. `A minor blues sequences - b3 shape, half-step
  bends.gp5`), next to where they work.
- The output is never overwritten without `--force`.

## Boxes (A minor blues; finger = suggested fingering)

Named after the scale degree of the lowest note on string 6.

| shape | frets | lowest note | string 6 .. 1 (fret/finger) |
|---|---|---|---|
| b7 | 2-6 | G | 6: 3/1 5/3 · 5: 3/1 5/3 6/4 · 4: 2/1 5/4 · 3: 2/1 5/4 · 2: 3/1 4/2 5/3 · 1: 3/1 5/3 |
| root | 5-8 | A | 6: 5/1 8/4 · 5: 5/1 6/2 7/3 · 4: 5/1 7/3 · 3: 5/1 7/3 8/4 · 2: 5/1 8/4 · 1: 5/1 8/4 |
| b3 | 7-11 | C | 6: 8/1 10/3 11/4 · 5: 7/1 10/4 · 4: 7/1 10/4 · 3: 7/1 8/2 9/3 · 2: 8/1 10/3 · 1: 8/1 10/3 11/4 |
| 4 | 9-13 | D | 6: 10/1 11/2 12/3 · 5: 10/1 12/3 · 4: 10/1 12/3 13/4 · 3: 9/1 12/4 · 2: 10/1 13/4 · 1: 10/1 11/2 12/3 |
| 5 | 12-16 | E | 6: 12/1 15/4 · 5: 12/1 15/4 · 4: 12/1 13/2 14/3 · 3: 12/1 14/3 · 2: 13/1 15/3 16/4 · 1: 12/1 15/4 |

One-pick bend frets (`Box.bend_pairs()`, from the fingering): root s5f6 D#->E (middle), s3f7 D->D#
(ring); b7 s5f5 D->D# (ring), s2f4 D#->E (middle); b3 s6f10 D->D# (ring), s3f8 D#->E (middle),
s1f10 D->D# (ring); 4 s6f11 D#->E (middle), s4f12 D->D# (ring), s1f11 D#->E (middle); 5 s4f13 D#->E
(middle), s2f15 D->D# (ring).

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

### Changing the way down (`stop`, `skip`)
Groups are numbered from the bottom of the box, from 0: group N is `G(N)`, the group built on box note
N (in 3s, group 3 is [3,4,5] up and [5,4,3] down). Per section, after the rhythm:
- `stop=N`: the descent ends at group N instead of the bottom group; the line then lands on index 0
  (a quarter). Musically: the way down stays in the upper part of the box, or a long sequence is kept
  short.
- `skip=N` / `skip=N+M`: the descent leaves those groups out; coming down, the line jumps from the group
  above each one to the group below it, breaking the sequence's regular step.
A group the descent does not have (above the top, below `stop`, or a palindromic top group, which is
played once on the way up) is refused with the groups it does play named. `stop` and `skip` may leave
the descent no group at all (the line goes up, then lands). To find N, run `patterns --n <box size>`
(box sizes: `boxes`) or read the section's `index_notation` from `--json`. Python API:
`Section(label, pattern, note=..., desc_stop=N, desc_skip=(N, M))`; they replace a pattern-file
pattern's own `desc_stop` / `desc_skip`.

### Transferring an exercise the user has as a file or reads
What reproduces a user's reference -- the `--patterns` list with its rhythms and options, and any
pattern defined for it -- is the user's recipe. It lives in the user's own files, never in this
skill: do not add it to `scripts/scaleseq/patterns.py` or anywhere in this skill's directory or
repository.
1. Run `analyze --box <box it is in> --reads DIR` (flat `tab_read.json`). It lists the library
   patterns that reproduce each section exactly. For a `.gp5`, read its (string, fret) per note with
   pyguitarpro and map them to box indices with `Box.index_of_sf()` the same way.
2. If every section matches, the recipe is just the `--patterns` list. A section that differs from a
   library pattern only in its way down may need just `stop`/`skip` (`analyze` does not try options;
   prove them with `--expect-reads`). If a section needs a pattern the library lacks, write it into
   a pattern file in the user's own folder, next to their reference (for example
   `<their folder>/patterns.json`), and pass `--pattern-file <that file>`:
   `{"<new name>": {"shape": [0, 2, 1], "default_rhythm": "8t"}}` -- any `Pattern` field
   (`shape` required; `turn_last`, `repeat_top`, `desc_stop`, `desc_skip`, `pickup`, `land`,
   `default_rhythm`, `about`, `aliases`; lists for the tuple fields). The name must not be a library
   pattern's. `analyze --pattern-file` then lists it too. Prove the recipe with
   `generate --box <same box> [--pattern-file F] --patterns ... --expect-reads DIR` (or `--expect-gp5`)
   before using it on another box. Never use a pattern on a new box unless it reproduces the reference
   exactly.
3. Run `generate --box <new box>` with the same pattern file, patterns, rhythms and options. Tell the user the
   command line, so they can keep it with their reference (e.g. in a note or script in that folder).
The reference itself (e.g. reads of a method book page) also stays where it is: never copy it into
this skill's directory or repository.

## Musical choices the scripts make (tell the user when relevant)
- **End on the lowest box note (index 0).** On the root box this is the root. On other boxes it is
  the box's lowest note (b7 box: G, b3 box: C, 4 box: D, 5 box: E). This keeps the index pattern
  identical. Resolving to A would mean leaving the box or leaping (in the b3 box, A is index 5).
- **Half-step bends, one pick per bend** (`--one-pick-bends`, for the plain scale). Each blue note
  (D# in A) is bent in one pair, chosen from the box's fingering. If its string holds D-D#-E on
  adjacent frets (fingers 1-2-3), the middle finger bends D# up to E, and E's own fret is never
  played. Otherwise the ring finger bends D up to D#, and D#'s own fret is never played. The index and
  little fingers never bend (a box that would need them is refused). Going up: pick the lower
  note, then a tied note bends it up into the upper one. Going down: pick a pre-bend (it sounds the
  upper note), then a tied note releases it into the lower one. At the top of the b3 box (D-D# on
  string 1) one pick carries both: pick D, bend up to D#, release back to D (at the top of the 4
  box, D#-E: pick D#, bend up to E, release back to D#). Every scale note keeps its own beat; only
  the picks change.
- **Half-step bends, every note picked** (`--bend-blue-notes`). Every b5 gets its own pick attack:
  pick the 4th (D) one fret below and bend it up ½. A neighbouring D on the same fret is a separate
  unbent note, so "D# D D#" is bend, release silently, pick D, bend again. In the root box the bends
  are string 5 fret 5 (index finger) and string 3 fret 7 (ring finger). This is not how half-step
  bends are usually played in a line; prefer `--one-pick-bends` where it applies.
- Files use 4/4 with the pickup in its own bar (n/8). Markers name each section, with a double bar
  at each section's end, and the key signature is the root's major key (A = 3 sharps).

## Checks (all deterministic; any failure exits 1 and writes no file)
- box: pitch classes, gap-free ascending scale run, fingers.
- plan: every bar sums to its time signature. Every note is a box position (or the bend source of a
  blue note), its pitch at the end of the beat equals the box note, and its pitch class is in the
  scale. Each section's index stream equals `pattern.stream(N)`. The rhythm per role (pickup, line,
  landing) matches. Rests appear only after the line. Markers and double bars are on the right bars.
  Bends, per mode: none; or exactly the blue notes, each picked; or, with `--one-pick-bends`, checked
  from the bend pairs and the rules rather than by re-running the planner: two adjacent notes of a
  pair are one picked note (tied bend up, or pre-bend and tied release), a pair's upper note never
  on its own fret, every tie continues the note before it on the same fret and pitch, every pre-bend
  released and never right after a note on its own string, no bend picked again (across sections
  too), nothing bent elsewhere or with the index or little finger. Every note's finger is the box's
  finger for that fret.
- read-back (pyguitarpro): the file equals the plan beat by beat, including ties and each bend's GP
  type and points. Voice 2 is one *empty* full-bar beat.
- alphaTab: its own parse equals the plan, including bars, time signatures, markers, double bars,
  rest/duration/tuplet per beat, string/fret, tie, bend type and points (kept as written, not
  simplified), and the pitch at the end of each note. Its MIDI (as its player generates it) has one
  note-on per pick, at the pick's tick and the fret's key, held to the end of its last tied note. Note
  by note (tied notes included), the pitch bend starts at the planned value (a pre-bend is set before
  its note-on), reaches the target within 1/6 of the note's length, and holds it to the note's end. The render check
  renders the score in Node and confirms a ½ label on exactly the notes that bend up or are pre-bent
  (releases have none; matched by alphaTab beat id).
- Not checked: playback audio (the MIDI events are checked, not the sound), and how a player's own
  saved copy looks after it re-exports the file. Do not play audio to check.
- Preview: `node "${CLAUDE_SKILL_DIR}/scripts/alphatab_check.mjs" "${CLAUDE_SKILL_DIR}/node_modules/@coderline/alphatab/dist/alphaTab.mjs" file.gp5 --html preview.html`
  writes a standalone page of alphaTab's render. Serve it from localhost to look at it.

## GP5 conventions (alphaTab-safe)
Every bar's unused voice 2 holds one beat with status **empty**. A zero-beat voice crashes alphaTab,
and a rest-status filler draws a stray rest in every bar. No note velocity is written. alphaTab
still draws its default "f" at the first note; that mark comes from the player, not the file. The
half-step bends, in pyguitarpro points (position 0-12, quarter tones; the file stores 50 = one
semitone): bend up `BendType.bend` (0,0) (1,0) (2,2) (12,2); pre-bend `BendType.prebend` (0,2) (12,2);
release `BendType.prebendRelease` (0,2) (1,2) (2,0) (12,0) on a tied note. A bend that moves has exactly
4 points whose two middle values differ: alphaTab 1.8.3 turns a 2-4 point bend that only rises or
only falls into a slow ramp across the whole note unless its two middle values differ, its GP7 writer
drops bends of more than 4 points, and a middle value of 1 quarter tone draws a stray "¼" label. A note that is not picked (it continues the one before) is a
GP tie note.

## Hand-over
Report the file path, box, key, bars, notes, picks, bends and every check line from the run. Tell the user
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
that reproduces it: the `--patterns` list with its rhythms and options and any pattern defined for
it stay in the user's own files (a pattern file passed with `--pattern-file`, a note or script next to the
reference) and are never added to this skill or committed. The private regression test reads them from
a directory named in an environment variable for the same reason.

## Version
Version 0.3.0: all five A minor blues boxes (the 4 and 5 shapes are new); per-section descent options
`stop=N` and `skip=N[+N...]` in `--patterns`.
