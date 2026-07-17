// Extracellular nutrients: glucose molecules streaming in toward the membrane
// transporters (all scenarios), and — for spatial scenarios — the radial
// concentration gradient rendered as coloured shells (depleted near the surface).

import { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { transportActivity } from "../inspect";
import type { ObjectId } from "../inspect";
import { useHoverHandlers } from "../cell/interact";
import { FlowParticles } from "./FlowParticles";
import { radiusForMass } from "./geometry";

/** Glucose molecules drifting from the medium toward the membrane (uptake). */
export function GlucoseFlow({ frame }: { frame: FrameData }) {
  const cellR = radiusForMass(frame.mass);
  const conc = frame.nutrients?.glc?.surface ?? frame.env_glucose;
  const act = THREE.MathUtils.clamp(transportActivity(frame), 0.3, 2.2);
  // Saturating count, scaled by how hard the transporters are working.
  const active = Math.round(46 * (conc / (conc + 6)) * (act / 1.4));

  return (
    <FlowParticles
      max={46}
      active={active}
      color="#fbbf24"
      size={0.05}
      speed={0.35}
      place={(dir, phase, _i, out) => {
        const start = cellR + 1.4;
        const end = cellR + 0.03;
        out.copy(dir).multiplyScalar(start + (end - start) * phase);
      }}
    />
  );
}

/** Radial glucose gradient shells for spatial scenarios. */
export function NutrientField({
  frame,
  onSelect,
}: {
  frame: FrameData;
  onSelect: (id: ObjectId) => void;
}) {
  const hover = useHoverHandlers("nutrients");
  if (!frame.field_glc || frame.field_glc.length === 0) return null;
  const cellR = radiusForMass(frame.mass);
  const maxC = Math.max(...frame.field_glc, 1e-6);
  const step = 0.5;
  return (
    <group
      {...hover}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        onSelect("nutrients");
      }}
    >
      {frame.field_glc.map((c, i) => {
        const frac = c / maxC;
        // Concentration ramp: blue (depleted) → cyan → yellow (abundant).
        const color = new THREE.Color().setHSL(0.6 - 0.45 * frac, 0.75, 0.55);
        return (
          <mesh key={i}>
            <sphereGeometry args={[cellR + 0.3 + i * step, 24, 24]} />
            <meshBasicMaterial color={color} wireframe transparent opacity={0.05 + 0.25 * frac} />
          </mesh>
        );
      })}
    </group>
  );
}
