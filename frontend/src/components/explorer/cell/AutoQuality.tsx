// Auto quality: measures the frame rate inside the render loop and steps the quality
// tier up/down to keep things smooth. Only active while the user selects "auto".

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { nextAutoQuality, type Quality } from "./quality";

interface Props {
  enabled: boolean;
  tier: Quality;
  onTier: (q: Quality) => void;
}

export function AutoQuality({ enabled, tier, onTier }: Props) {
  const acc = useRef({ frames: 0, time: 0, cooldown: 99 });

  useFrame((_, delta) => {
    if (!enabled) return;
    const a = acc.current;
    a.frames += 1;
    a.time += delta;
    a.cooldown += delta;
    if (a.time >= 1) {
      const fps = a.frames / a.time;
      a.frames = 0;
      a.time = 0;
      if (a.cooldown > 1.5) {
        const next = nextAutoQuality(tier, fps);
        if (next !== tier) {
          a.cooldown = 0;
          onTier(next);
        }
      }
    }
  });

  return null;
}
