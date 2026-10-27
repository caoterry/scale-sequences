# SPDX-License-Identifier: MIT
"""Write a plan to .gp5 with the conventions alphaTab (and players built on it) need:

- every bar has GP5's two voices; the unused voice 2 holds ONE beat with status *empty*, the bar's
  full length. A zero-beat voice crashes alphaTab; a *rest*-status filler draws a stray rest in
  every bar.
- no note velocity is written (alphaTab draws a dynamic mark for any explicit one).
- half-step bend = GP BendType.bend, points (0,0) (3,2) (12,2) in pyguitarpro units
  (position 0-12, value in quarter tones; file stores 50 = one semitone), i.e. pick the lower note
  and bend it up a half step early in the note, then hold.
"""

from __future__ import annotations

import guitarpro as gp
from guitarpro import models as m

from .theory import MAJOR_KEY_SHARPS, STANDARD_TUNING

_KEYSIG: dict[tuple[int, int], m.KeySignature] = {ks.value: ks for ks in m.KeySignature}
_FINGER = {1: m.Fingering.index, 2: m.Fingering.middle, 3: m.Fingering.annular, 4: m.Fingering.little}


def half_step_bend() -> m.BendEffect:
    return m.BendEffect(type=m.BendType.bend, value=50,
                        points=[m.BendPoint(0, 0), m.BendPoint(3, 2), m.BendPoint(12, 2)])


def _duration(b: dict) -> m.Duration:
    d = m.Duration(value=b["value"])
    if b["tuplet"] != [1, 1]:
        d.tuplet = m.Tuplet(enters=b["tuplet"][0], times=b["tuplet"][1])
    return d


def write_gp5(plan: list[dict], out: str, *, title: str, subtitle: str = "", tempo: int = 80,
              root_pc: int = 9, fingering: bool = False, instrument: int = 25) -> None:
    song = m.Song()
    song.title = title
    song.subtitle = subtitle
    song.tempo = tempo
    song.measureHeaders = []
    keysig = _KEYSIG[(MAJOR_KEY_SHARPS[root_pc], 0)]
    for k, bar in enumerate(plan):
        hdr = m.MeasureHeader(number=k + 1)
        num, den = bar["ts"]
        hdr.timeSignature = m.TimeSignature(numerator=num, denominator=m.Duration(value=den))
        hdr.keySignature = keysig
        if bar["marker"]:
            hdr.marker = m.Marker(title=bar["marker"])
        if bar["double_bar"]:
            hdr.hasDoubleBar = True
        song.measureHeaders.append(hdr)

    track = m.Track(song, number=1)
    track.name = "Guitar"
    track.strings = [m.GuitarString(n, v) for n, v in sorted(STANDARD_TUNING.items())]
    track.channel.instrument = instrument
    track.measures = []
    for hdr, bar in zip(song.measureHeaders, plan):
        meas = m.Measure(track, hdr)
        meas.voices = []
        v = m.Voice(meas)
        v.beats = []
        for b in bar["beats"]:
            beat = m.Beat(v)
            beat.duration = _duration(b)
            if b["rest"]:
                beat.status = m.BeatStatus.rest
            else:
                beat.status = m.BeatStatus.normal
                note = m.Note(beat, value=b["fret"], string=b["string"], type=m.NoteType.normal)
                if b["bend"]:
                    assert b["bend"] == 2, "only half-step bends are supported"
                    note.effect.bend = half_step_bend()
                if fingering:
                    note.effect.leftHandFinger = _FINGER[b["finger"]]
                beat.notes.append(note)
            v.beats.append(beat)
        meas.voices.append(v)
        num, den = bar["ts"]
        for _ in range(m.Measure.maxVoices - 1):
            v2 = m.Voice(meas)
            fb = m.Beat(v2)
            fb.duration = m.Duration.fromTime(num * m.Duration(value=den).time)
            fb.status = m.BeatStatus.empty
            v2.beats = [fb]
            meas.voices.append(v2)
        track.measures.append(meas)
    song.tracks = [track]
    gp.write(song, out, version=(5, 1, 0))


def read_plan_shape(path: str) -> dict:
    """Parse a .gp5 back into the plan's terms (for read-back checks)."""
    song = gp.parse(path)
    tr = song.tracks[0]
    bars = []
    for meas in tr.measures:
        h = meas.header
        beats = []
        for b in meas.voices[0].beats:
            t = b.duration.tuplet
            d = {"rest": b.status == m.BeatStatus.rest, "value": b.duration.value,
                 "tuplet": [t.enters, t.times], "status": b.status.name, "notes": []}
            for n in b.notes:
                bend = n.effect.bend
                d["notes"].append({"string": n.string, "fret": n.value,
                                   "bend": max((p.value for p in bend.points), default=0) if bend else 0,
                                   "bend_type": bend.type.name if bend else None,
                                   "finger": n.effect.leftHandFinger.value,
                                   "velocity": n.velocity})
            beats.append(d)
        others = [[(b.status.name, b.duration.time) for b in v.beats] for v in meas.voices[1:]]
        bars.append({"ts": [h.timeSignature.numerator, h.timeSignature.denominator.value],
                     "marker": h.marker.title if h.marker else None, "double_bar": h.hasDoubleBar,
                     "beats": beats, "other_voices": others,
                     "bar_time": h.timeSignature.numerator * m.Duration(value=h.timeSignature.denominator.value).time})
    return {"title": song.title, "subtitle": song.subtitle, "tempo": song.tempo,
            "strings": [(s.number, s.value) for s in tr.strings], "bars": bars}
