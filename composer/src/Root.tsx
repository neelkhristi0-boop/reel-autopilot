import React from "react";
import {Composition} from "remotion";
import {Reel, ReelProps} from "./Reel";
import {Clip, ClipProps} from "./Clip";

const demo: ReelProps = {
  words: [{word: "Demo", start: 0, end: 0.5}],
  beats: [{start: 0, scene: {type: "title", kicker: "DEMO", text: "Reel Autopilot"}}],
  audio: "",
  accent: "#3b82f6",
  handle: "@demo",
  duration: 2,
};

const dur = ({props}: {props: Record<string, unknown>}) => ({
  durationInFrames: Math.max(30, Math.ceil(Number(props.duration) * 30)),
});

export const Root: React.FC = () => (
  <>
  <Composition
    id="Clip"
    component={Clip as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={60}
    defaultProps={{video: "", words: [], title: "Demo", accent: "#3b82f6", handle: "@demo", duration: 2} as unknown as Record<string, unknown>}
    calculateMetadata={dur}
  />
  <Composition
    id="Reel"
    component={Reel as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={60}
    defaultProps={demo as unknown as Record<string, unknown>}
    calculateMetadata={dur}
  />
  </>
);
