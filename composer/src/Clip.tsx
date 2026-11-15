// Clipping mode: a pre-cut 1080x1920 video with a hook title and word-by-word captions.
import React from "react";
import {AbsoluteFill, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import type {Word} from "./Reel";

export type ClipProps = {video: string; words: Word[]; title: string; accent: string; handle: string; duration: number};
const FONT = "Inter, 'Noto Sans Devanagari', 'Noto Sans', 'Noto Color Emoji', sans-serif";
const STROKE = "0 0 14px rgba(0,0,0,.9), 0 4px 0 #000, 4px 0 0 #000, -4px 0 0 #000, 0 -4px 0 #000";

export const Clip: React.FC<ClipProps> = ({video, words, title, accent, handle, duration}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  // phrases of up to 3 words, broken at pauses and sentence ends
  const phrases: number[][] = [[]];
  words.forEach((w, i) => {
    const cur = phrases[phrases.length - 1];
    if (cur.length && (cur.length === 3 || /[.,?!।]$/.test(words[i - 1].word) || w.start - words[i - 1].end > 0.45)) phrases.push([i]);
    else cur.push(i);
  });
  let cur = -1;
  words.forEach((w, i) => { if (w.start <= t) cur = i; });
  const phrase = cur < 0 || t > words[cur].end + 0.6 ? [] : phrases.find((p) => p.includes(cur)) ?? [];
  const pop = phrase.length ? spring({frame: frame - words[phrase[0]].start * fps, fps, config: {damping: 14, stiffness: 220}}) : 0;
  const tin = spring({frame, fps, config: {damping: 200}});
  return (
    <AbsoluteFill style={{background: "#000", fontFamily: FONT, color: "#fff"}}>
      <OffthreadVideo src={staticFile(video)} />
      {title ? (
        <div style={{position: "absolute", top: 170, left: 60, right: 60, textAlign: "center", opacity: tin, transform: `translateY(${(1 - tin) * -30}px)`}}>
          <span style={{background: "rgba(0,0,0,.72)", borderBottom: `8px solid ${accent}`, padding: "14px 26px", fontSize: 58, fontWeight: 800, lineHeight: 1.5, letterSpacing: -1, boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone"}}>{title}</span>
        </div>
      ) : null}
      <div style={{position: "absolute", top: 1230, left: 50, right: 50, textAlign: "center", fontSize: 84, fontWeight: 800, lineHeight: 1.2, letterSpacing: -1, textShadow: STROKE, transform: `scale(${0.9 + 0.1 * pop})`}}>
        {phrase.map((i) => (
          <span key={i} style={{display: "inline-block", margin: "0 12px", color: i === cur ? accent : "#fff", opacity: i <= cur ? 1 : 0.55}}>{words[i].word}</span>
        ))}
      </div>
      <div style={{position: "absolute", top: 1440, width: 1080, textAlign: "center", fontSize: 34, fontWeight: 600, letterSpacing: 3, opacity: 0.6, textShadow: STROKE}}>{handle}</div>
      <div style={{position: "absolute", top: 0, left: 0, height: 8, width: 1080 * Math.min(1, t / duration), background: accent}} />
    </AbsoluteFill>
  );
};
