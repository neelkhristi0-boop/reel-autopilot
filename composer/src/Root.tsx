import React from "react";
import {Composition} from "remotion";
import {Reel, ReelProps} from "./Reel";

const demo: ReelProps = {
  words: [{word: "Demo", start: 0, end: 0.5}],
  beats: [{start: 0, scene: {type: "title", kicker: "DEMO", text: "Reel Autopilot"}}],
  audio: "",
  accent: "#3b82f6",
  handle: "@demo",
  duration: 2,
};

export const Root: React.FC = () => (
  <Composition
    id="Reel"
    component={Reel as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={60}
    defaultProps={demo as unknown as Record<string, unknown>}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(30, Math.ceil(Number((props as unknown as ReelProps).duration) * 30)),
    })}
  />
);
