#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// alphatab_check.mjs -- load a .gp5 with alphaTab (the engine woodshed and many web players use)
// and print, as JSON, what alphaTab itself parsed: bars, time signatures, markers, every beat
// (rest/empty, duration, tuplet) and note (GP string number, fret, tie, bend type and points, pitch
// at the end of the note incl. bend), and the MIDI alphaTab's player generates from it (note-ons,
// note-offs and per-note pitch bends in half steps, by tick).
// With --render it also renders the score (default notation + tab) to SVG in Node and reports which
// beats carry a bend label ("½", "full", ...), by alphaTab's own beat ids.
//
// With --html OUT.html (implies --render) it also writes a standalone preview page of that render
// (music font embedded) for eyeballing.
//
// usage: node alphatab_check.mjs <alphaTab.mjs> <file.gp5> [--render] [--html OUT.html]
// Exits 1 (message on stderr) if alphaTab throws, or if its MIDI does not set exactly one pitch-bend
// range. alphaTab's own warnings go to stderr (e.g. "Unsupported bend type detected, fallback to custom"
// for every 4-point bend, which is what keeps that bend's shape).

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const [atPath, file, ...rest] = process.argv.slice(2);
const htmlOut = rest.includes("--html") ? rest[rest.indexOf("--html") + 1] : null;
const doRender = rest.includes("--render") || htmlOut !== null;
const at = await import(pathToFileURL(atPath).href);

let score;
const settings = new at.Settings();
try {
  score = at.importer.ScoreLoader.loadScoreFromBytes(new Uint8Array(readFileSync(file)), settings);
} catch (e) {
  console.error(`ALPHATAB FAILED to load ${file}: ${e && e.stack ? e.stack : e}`);
  process.exit(1);
}

const tr = score.tracks[0];
const staff = tr.staves[0];
const nStrings = staff.tuning.length;
const beatWhere = new Map();
const bars = staff.bars.map((bar, bi) => ({
  voices: bar.voices.map((v, vi) => v.beats.map((b, k) => {
    beatWhere.set(b.id, [bi, vi, k]);
    return {
      id: b.id, isEmpty: b.isEmpty, isRest: b.isRest, duration: b.duration,
      tuplet: [b.tupletNumerator, b.tupletDenominator],
      notes: b.notes.map((n) => {
        const points = n.hasBend ? n.bendPoints.map((p) => [p.offset, p.value]) : [];  // offset 0-60, quarter tones
        const maxBend = points.length ? Math.max(...points.map((p) => p[1])) : 0;
        return {
          string: nStrings - n.string + 1, fret: n.fret, realValue: n.realValue,
          tie: n.isTieDestination, bendType: n.bendType, bendPoints: points, maxBendQuarterTones: maxBend,
          soundingEnd: n.realValue + (points.length ? points[points.length - 1][1] : 0) / 2,
          velocity: n.dynamics,
        };
      }),
    };
  })),
}));

const out = {
  version: at.meta ? at.meta.version : undefined,
  title: score.title, subtitle: score.subTitle, tempo: score.tempo,
  tracks: score.tracks.length,
  masterBars: score.masterBars.map((mb) => ({
    ts: [mb.timeSignatureNumerator, mb.timeSignatureDenominator],
    marker: mb.section ? mb.section.text : null, doubleBar: mb.isDoubleBar,
  })),
  bars,
  midi: midiDump(),
};

// The MIDI alphaTab's player plays (AlphaSynthMidiFileHandler in its default per-note-bend mode).
// Pitch bends are converted to half steps with the bend range alphaTab itself sets (RPN 0 data entry).
function midiDump() {
  const midi = new at.midi.MidiFile();
  new at.midi.MidiFileGenerator(score, settings, new at.midi.AlphaSynthMidiFileHandler(midi)).generate();
  const T = at.midi.MidiEventType;
  const ranges = new Set(midi.events.filter((e) => e.type === T.ControlChange
    && e.controller === at.midi.ControllerType.DataEntryCoarse).map((e) => e.value));
  if (ranges.size !== 1) {
    console.error(`ALPHATAB MIDI: expected one pitch-bend range, got ${[...ranges]}`);
    process.exit(1);
  }
  const [range] = ranges;
  const names = { [T.NoteOn]: "NoteOn", [T.NoteOff]: "NoteOff", [T.PerNotePitchBend]: "NoteBend", [T.PitchBend]: "PitchBend" };
  const events = midi.events.filter((e) => e.type in names).map((e) => ({
    type: names[e.type], tick: e.tick, channel: e.channel, key: e.type === T.PitchBend ? null : e.noteKey,
    semitones: e.type === T.PerNotePitchBend ? (e.value - 2 ** 31) / (2 ** 31 / range)
      : e.type === T.PitchBend ? (e.value - 8192) / (8192 / range) : null,
  }));
  return { division: midi.division, bendRangeSemitones: range, events };
}

if (doRender) {
  settings.core.engine = "svg";
  settings.core.enableLazyLoading = false;
  const r = new at.rendering.ScoreRenderer(settings);
  r.width = 1300;
  const chunks = [];
  let err = null;
  const placed = [];
  r.partialRenderFinished.on((e) => {
    chunks.push(e.renderResult);
    placed.push({ x: e.x, y: e.y, w: e.width, h: e.height, svg: e.renderResult });
  });
  r.error.on((e) => { err = e; });
  r.renderScore(score, [0]);
  if (err) {
    console.error(`ALPHATAB RENDER FAILED: ${err}`);
    process.exit(1);
  }
  const svg = chunks.join("\n");
  // Walk <g ...> / </g> to find the enclosing beat group (class="b<id>") of each bend label.
  const labels = [];
  const stack = [];
  const re = /<g\b([^>]*)>|<\/g>|<text\b[^>]*>([^<]*)<\/text>/g;
  let mt;
  while ((mt = re.exec(svg))) {
    if (mt[0].startsWith("</g")) stack.pop();
    else if (mt[0].startsWith("<g")) {
      const cls = /class="([^"]*)"/.exec(mt[1] || "");
      stack.push(cls ? cls[1] : "");
    } else {
      const text = mt[2].trim();
      if (text === "full" || /^\d*(½|¼|¾)$/.test(text)) {  // alphaTab's bend amount labels
        const g = [...stack].reverse().find((c) => /^b\d+$/.test(c));
        const id = g ? Number(g.slice(1)) : null;
        labels.push({ text, beatId: id, where: id !== null ? beatWhere.get(id) || null : null });
      }
    }
  }
  out.render = { svgBytes: svg.length, chunks: chunks.length, bendLabels: labels };
  if (htmlOut) {
    const font = readFileSync(join(dirname(atPath), "font", "Bravura.woff2")).toString("base64");
    const size = settings.display.resources.engravingSettings.musicFontSize;
    const W = Math.max(...placed.map((p) => p.x + p.w)), H = Math.max(...placed.map((p) => p.y + p.h));
    const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
    writeFileSync(htmlOut, `<!doctype html><html><head><meta charset="utf-8"><title>${esc(score.title)}</title>
<style>@font-face{font-family:'alphaTab';src:url(data:font/woff2;base64,${font}) format('woff2');}
body{margin:16px;background:#fff;color:#000;font-family:Arial,sans-serif}
.at-surface .at{font-family:'alphaTab';line-height:1;font-size:${size}px;overflow:visible!important}
.at-surface{position:relative;width:${W}px;height:${H}px}.at-surface>div{position:absolute}</style></head>
<body><div class="at-surface at">${placed.map((p) => `<div style="left:${p.x}px;top:${p.y}px;width:${p.w}px;height:${p.h}px">${p.svg}</div>`).join("\n")}</div></body></html>`);
    out.render.html = htmlOut;
  }
}

console.log(JSON.stringify(out));
