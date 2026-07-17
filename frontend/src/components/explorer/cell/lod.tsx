// Level-of-detail: one shared detail factor (0.25..1) updated each frame from the
// camera distance. Instanced systems read it to scale their particle counts, so the
// scene stays smooth when zoomed out (and full-detail when you fly in). No re-renders.

import { useFrame } from "@react-three/fiber";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import * as THREE from "three";

export interface LodRef {
  current: number;
}

const LodContext = createContext<LodRef>({ current: 1 });

export function useLod(): LodRef {
  return useContext(LodContext);
}

function LodController({ lodRef, densityScale }: { lodRef: LodRef; densityScale: number }) {
  useFrame(({ camera }) => {
    const d = camera.position.length();
    // near (d<=4) → 1.0 full detail; far (d>=16) → 0.25. Scaled by the quality tier's
    // particle density so lower tiers draw fewer molecules.
    const distance = THREE.MathUtils.clamp(1 - ((d - 4) / 12) * 0.75, 0.25, 1);
    lodRef.current = distance * densityScale;
  });
  return null;
}

export function LodProvider({ children, densityScale = 1 }: { children: ReactNode; densityScale?: number }) {
  const ref = useMemo<LodRef>(() => ({ current: densityScale }), [densityScale]);
  return (
    <LodContext.Provider value={ref}>
      {children}
      <LodController lodRef={ref} densityScale={densityScale} />
    </LodContext.Provider>
  );
}
