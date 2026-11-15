// Word Reel engine, data-driven version. The voice is the clock:
// every scene starts on the first word of its beat, captions follow word times.
import React from "react";
import {AbsoluteFill, Audio, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

export type Word = {word: string; start: number; end: number};
export type Scene =
  | {type: "title"; kicker?: string; text: string}
  | {type: "number"; value: number; prefix?: string; suffix?: string; label: string}
  | {type: "compare"; a: {label: string; value: number}; b: {label: string; value: number}; unit?: string}
  | {type: "list"; heading?: string; items: string[]}
  | {type: "statement"; text: string; highlight?: string}
  | {type: "timeline"; points: {label: string; text: string}[]};
export type Beat = {start: number; scene: Scene; key?: string; image?: string | null};
export type ReelProps = {words: Word[]; beats: Beat[]; audio: string; accent: string; handle: string; duration: number};

const W = 1080;
const FONT = "Inter, 'Noto Sans Devanagari', 'Noto Sans', 'Noto Color Emoji', sans-serif";
const fit = (s: string, big: number, small: number, at = 12, to = 70) =>
  Math.round(interpolate(s.length, [at, to], [big, small], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}));
const fmt = (n: number) => (Math.abs(n) >= 1000 ? Math.round(n).toLocaleString("en-IN") : Number.isInteger(n) ? String(n) : n.toFixed(1));

const anim = (v: number, r: number) => (Number.isInteger(v) ? Math.round(v * r) : v * r); // whole numbers count up in whole steps

// t = seconds since the beat started, len = beat length in seconds
type SP = {t: number; len: number; accent: string};
const useIn = (t: number, delay = 0, snappy = true) => {
  const {fps} = useVideoConfig();
  return spring({frame: (t - delay) * fps, fps, config: snappy ? {damping: 200, stiffness: 180} : {damping: 14}});
};

const Title: React.FC<SP & {s: Extract<Scene, {type: "title"}>}> = ({t, accent, s}) => {
  const p = useIn(t), u = useIn(t, 0.25);
  return (
    <div style={{textAlign: "center", width: 900}}>
      {s.kicker && <div style={{fontSize: 40, fontWeight: 700, letterSpacing: 8, color: accent, opacity: p, marginBottom: 28}}>{s.kicker.toUpperCase()}</div>}
      <div style={{fontSize: fit(s.text, 150, 84, 8, 48), fontWeight: 800, lineHeight: 1.08, letterSpacing: -2, transform: `translateY(${(1 - p) * 40}px)`, opacity: p}}>{s.text}</div>
      <div style={{height: 10, width: 420 * u, background: accent, margin: "44px auto 0", borderRadius: 5}} />
    </div>
  );
};

const NumberScene: React.FC<SP & {s: Extract<Scene, {type: "number"}>}> = ({t, len, accent, s}) => {
  const p = useIn(t);
  const r = Math.min(1, Math.max(0, t / Math.min(1.2, len * 0.6)));
  const eased = 1 - Math.pow(1 - r, 3);
  const txt = `${s.prefix ?? ""}${fmt(anim(s.value, eased))}${s.suffix ?? ""}`;
  return (
    <div style={{textAlign: "center", width: 960}}>
      <div style={{fontSize: fit(txt, 300, 150, 4, 12), fontWeight: 800, letterSpacing: -6, color: accent, transform: `scale(${0.8 + 0.2 * p})`, opacity: p, fontVariantNumeric: "tabular-nums"}}>{txt}</div>
      <div style={{height: 6, width: 700 * eased, background: "#fff", opacity: 0.25, margin: "10px auto 34px", borderRadius: 3}} />
      <div style={{fontSize: fit(s.label, 62, 44, 14, 60), fontWeight: 600, opacity: 0.85 * p, lineHeight: 1.2}}>{s.label}</div>
    </div>
  );
};

const Compare: React.FC<SP & {s: Extract<Scene, {type: "compare"}>}> = ({t, len, accent, s}) => {
  const max = Math.max(Math.abs(s.a.value), Math.abs(s.b.value)) || 1;
  const bars = [{...s.a, color: "#6b7280", delay: 0}, {...s.b, color: accent, delay: Math.min(0.9, len * 0.4)}];
  return (
    <div style={{display: "flex", gap: 90, alignItems: "flex-end", height: 820}}>
      {bars.map((b, i) => {
        const g = useIn(t, b.delay, false);
        const h = Math.max(24, 560 * (Math.abs(b.value) / max)) * Math.min(1, g);
        return (
          <div key={i} style={{width: 330, textAlign: "center", opacity: Math.min(1, g * 2)}}>
            <div style={{fontSize: 84, fontWeight: 800, color: b.color === "#6b7280" ? "#fff" : b.color, fontVariantNumeric: "tabular-nums"}}>{fmt(anim(b.value, Math.min(1, g)))}{s.unit ?? ""}</div>
            <div style={{height: h, background: b.color, borderRadius: "18px 18px 0 0", marginTop: 16}} />
            <div style={{fontSize: fit(b.label, 50, 36, 8, 30), fontWeight: 600, marginTop: 22, lineHeight: 1.15, height: 120}}>{b.label}</div>
          </div>
        );
      })}
    </div>
  );
};

const List: React.FC<SP & {s: Extract<Scene, {type: "list"}>}> = ({t, len, accent, s}) => {
  const items = s.items.slice(0, 4);
  const step = Math.max(0.5, (len * 0.85) / items.length);
  return (
    <div style={{width: 900}}>
      {s.heading && <div style={{fontSize: 46, fontWeight: 700, letterSpacing: 4, color: accent, marginBottom: 40, opacity: useIn(t)}}>{s.heading.toUpperCase()}</div>}
      {items.map((it, i) => {
        const p = useIn(t, i * step);
        const live = t >= i * step && t < (i + 1) * step;
        return (
          <div key={i} style={{display: "flex", gap: 30, alignItems: "center", marginBottom: 34, opacity: p, transform: `translateX(${(1 - p) * -60}px)`}}>
            <div style={{flex: "0 0 96px", height: 96, borderRadius: 20, background: live ? accent : "rgba(255,255,255,.1)", border: `3px solid ${accent}`, fontSize: 52, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center"}}>{i + 1}</div>
            <div style={{fontSize: fit(it, 80, 54, 14, 50), fontWeight: 700, lineHeight: 1.15}}>{it}</div>
          </div>
        );
      })}
    </div>
  );
};

const Statement: React.FC<SP & {s: Extract<Scene, {type: "statement"}>}> = ({t, accent, s}) => {
  const p = useIn(t), h = useIn(t, 0.35);
  const hi = (s.highlight ?? "").trim();
  const i = hi ? s.text.toLowerCase().indexOf(hi.toLowerCase()) : -1;
  const parts = i < 0 ? [s.text, "", ""] : [s.text.slice(0, i), s.text.slice(i, i + hi.length), s.text.slice(i + hi.length)];
  return (
    <div style={{width: 900, borderLeft: `12px solid ${accent}`, paddingLeft: 44, opacity: p, transform: `translateY(${(1 - p) * 30}px)`}}>
      <div style={{fontSize: fit(s.text, 104, 62, 20, 110), fontWeight: 700, lineHeight: 1.18, letterSpacing: -1}}>
        {parts[0]}
        {parts[1] && <span style={{color: "#fff", background: accent, padding: "0 14px", borderRadius: 10, boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone", opacity: 0.35 + 0.65 * h}}>{parts[1]}</span>}
        {parts[2]}
      </div>
    </div>
  );
};

const Timeline: React.FC<SP & {s: Extract<Scene, {type: "timeline"}>}> = ({t, len, accent, s}) => {
  const pts = s.points.slice(0, 4);
  const step = Math.max(0.5, (len * 0.85) / pts.length);
  const line = Math.min(1, t / Math.max(0.6, step * (pts.length - 1) + 0.4));
  return (
    <div style={{width: 880, position: "relative", paddingLeft: 90}}>
      <div style={{position: "absolute", left: 30, top: 20, width: 8, borderRadius: 4, background: accent, height: `calc(${line * 100}% - 40px)`}} />
      {pts.map((pt, i) => {
        const p = useIn(t, i * step);
        return (
          <div key={i} style={{marginBottom: 46, opacity: p, transform: `translateY(${(1 - p) * 24}px)`, position: "relative"}}>
            <div style={{position: "absolute", left: -80, top: 10, width: 48, height: 48, borderRadius: 24, background: "#000", border: `8px solid ${accent}`, boxSizing: "border-box"}} />
            <div style={{fontSize: 86, fontWeight: 800, color: accent, lineHeight: 1}}>{pt.label}</div>
            <div style={{fontSize: fit(pt.text, 62, 46, 16, 60), fontWeight: 600, lineHeight: 1.2, marginTop: 8, opacity: 0.9}}>{pt.text}</div>
          </div>
        );
      })}
    </div>
  );
};

// A real photo for the beat: sharp in a window, a blurred copy of itself behind, always slowly moving.
const PHOTO_TOP = 330, PHOTO_H = 920;
const Photo: React.FC<{src: string; t: number; len: number; flip: boolean; dim: number; label?: string; accent: string}> = ({src, t, len, flip, dim, label, accent}) => {
  const r = Math.min(1, t / Math.max(len, 2.5));
  const fade = Math.min(1, t / 0.18);
  const lp = useIn(t, 0.15);
  return (
    <AbsoluteFill style={{opacity: fade}}>
      <Img src={staticFile(src.replace(".jpg", "_bg.jpg"))} style={{position: "absolute", width: "100%", height: "100%", objectFit: "cover"}} />
      <div style={{position: "absolute", top: PHOTO_TOP, left: 0, width: W, height: PHOTO_H, overflow: "hidden"}}>
        <Img src={staticFile(src)} style={{width: "100%", height: "100%", objectFit: "cover", transform: `scale(${1.05 + 0.1 * r}) translateX(${(flip ? -1 : 1) * (r - 0.5) * 36}px)`}} />
        <div style={{position: "absolute", inset: 0, background: dim ? `rgba(0,0,0,${dim})` : "linear-gradient(180deg, rgba(0,0,0,.25) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 55%, rgba(0,0,0,.85) 100%)"}} />
        {label ? (
          <div style={{position: "absolute", left: 50, right: 50, bottom: 46, fontSize: fit(label, 84, 54, 14, 70), fontWeight: 800, lineHeight: 1.12, letterSpacing: -1, opacity: lp, transform: `translateY(${(1 - lp) * 24}px)`, textShadow: "0 3px 18px rgba(0,0,0,.8)"}}>
            <div style={{width: 110 * lp, height: 9, background: accent, borderRadius: 5, marginBottom: 20}} />
            {label}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const SceneView: React.FC<SP & {scene: Scene}> = ({scene, ...sp}) => {
  switch (scene.type) {
    case "number": return <NumberScene {...sp} s={scene} />;
    case "compare": return <Compare {...sp} s={scene} />;
    case "list": return <List {...sp} s={scene} />;
    case "statement": return <Statement {...sp} s={scene} />;
    case "timeline": return <Timeline {...sp} s={scene} />;
    default: return <Title {...sp} s={scene as Extract<Scene, {type: "title"}>} />;
  }
};

const norm = (s: string) => s.toLowerCase().replace(/[\s.,!?;:"'“”‘’()।-]/g, "");

const Captions: React.FC<{words: Word[]; beats: Beat[]; accent: string; t: number}> = ({words, beats, accent, t}) => {
  if (!words.length) return null;
  const beatStarts = new Set(beats.map((b) => b.start));
  const keyIdx = new Set<number>();
  beats.forEach((b, bi) => {
    if (!b.key) return;
    const end = bi + 1 < beats.length ? beats[bi + 1].start : words.length;
    for (let i = b.start; i < end; i++) if (norm(words[i].word) === norm(b.key)) { keyIdx.add(i); break; }
  });
  const phrases: number[][] = [[]];
  words.forEach((w, i) => {
    const cur = phrases[phrases.length - 1];
    if (cur.length && (beatStarts.has(i) || cur.length === 3 || /[.,?!।]$/.test(words[i - 1].word))) phrases.push([i]);
    else cur.push(i);
  });
  let cur = 0;
  words.forEach((w, i) => { if (w.start <= t) cur = i; });
  const phrase = phrases.find((p) => p.includes(cur)) ?? [];
  return (
    <div style={{position: "absolute", top: 190, width: W, textAlign: "center", textShadow: "0 2px 12px rgba(0,0,0,.9)", fontSize: 68, letterSpacing: -1, lineHeight: 1.3, padding: "0 50px", boxSizing: "border-box"}}>
      {phrase.filter((i) => i <= cur).map((i) => {
        const boxed = keyIdx.has(i);
        return (
          <span key={i} style={{display: "inline-block", margin: "0 9px", padding: "2px 12px", color: i === cur || boxed ? "#fff" : "#8c8c8c", fontWeight: i === cur || boxed ? 700 : 500, outline: boxed ? `3px solid ${accent}` : "none", background: boxed ? `${accent}30` : "none"}}>
            {words[i].word}
          </span>
        );
      })}
    </div>
  );
};

export const Reel: React.FC<ReelProps> = ({words, beats, audio, accent, handle, duration}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const starts = beats.map((b, i) => (i === 0 ? 0 : words[Math.min(b.start, words.length - 1)]?.start ?? 0));
  const idx = starts.reduce((a, s, i) => (t >= s ? i : a), 0);
  const bt = t - starts[idx];
  const len = (idx + 1 < starts.length ? starts[idx + 1] : duration) - starts[idx];
  const drift = 1 + 0.035 * Math.min(1, bt / 6); // nothing ever holds still
  const sc = beats[idx].scene;
  const img = beats[idx].image || null;
  const textOnly = sc.type === "title" || sc.type === "statement"; // with a photo these become a label on the picture
  const label = sc.type === "title" || sc.type === "statement" ? sc.text : "";
  return (
    <AbsoluteFill style={{background: "#000", color: "#fff", fontFamily: FONT}}>
      <AbsoluteFill style={{opacity: 0.1, backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "90px 90px", backgroundPosition: `0 ${-(frame * 0.4) % 90}px`}} />
      {img ? <Photo key={`p${idx}`} src={img} t={bt} len={len} flip={idx % 2 === 1} dim={textOnly ? 0 : 0.62} label={textOnly ? label : undefined} accent={accent} /> : null}
      {img && textOnly ? null : (
        <div style={{position: "absolute", top: img ? PHOTO_TOP : 400, left: 0, width: W, height: img ? PHOTO_H : 1000, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${img ? 0.86 * drift : drift})`}}>
          <SceneView key={idx} scene={beats[idx].scene} t={bt} len={len} accent={accent} />
        </div>
      )}
      <Captions words={words} beats={beats} accent={accent} t={t} />
      <div style={{position: "absolute", top: 1430, width: W, textAlign: "center", fontSize: 34, fontWeight: 600, letterSpacing: 3, opacity: 0.45}}>{handle}</div>
      <div style={{position: "absolute", top: 0, left: 0, height: 8, width: W * Math.min(1, t / duration), background: accent}} />
      {audio ? <Audio src={staticFile(audio)} /> : null}
    </AbsoluteFill>
  );
};
