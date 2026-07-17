// Internal compartments as ATP pools, plus ATP particles flowing outward from the
// cytosol (where metabolism produces energy) to the nucleoid and membrane zone.
// Particle count tracks the cytosolic energy pool: low ATP → fewer sparks.

import { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import type { ObjectId } from "../inspect";
import { FlowParticles } from "./FlowParticles";
import { COMPARTMENT_OFFSET, radiusForMass } from "./geometry";

interface EnergyProps {
  frame: FrameData;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function Energy({ frame, selected, onSelect }: EnergyProps) {
  const comps = frame.compartments;
  if (!comps) return null;
  const cellR = radiusForMass(frame.mass);
  const source = comps.cytosol?.energy ?? 0;
  // ATP spark count saturates with the cytosolic energy pool.
  const active = Math.round(40 * (source / (source + 12)));

  return (
    <group>
      {Object.entries(comps).map(([name, v]) => {
        const off = COMPARTMENT_OFFSET[name] ?? [0, 0, 0];
        const hsl = new THREE.Color().setHSL(0.55, 0.7, Math.min(0.7, 0.25 + v.energy / 60));
        const color = v.stressed ? "#fb7185" : `#${hsl.getHexString()}`;
        const r = (name === "cytosol" ? 0.3 : 0.2) * cellR;
        const sel = selected === `energy.${name}`;
        return (
          <mesh
            key={name}
            position={[off[0] * cellR, off[1] * cellR, off[2] * cellR]}
            onClick={(e: ThreeEvent<MouseEvent>) => {
              e.stopPropagation();
              onSelect(`energy.${name}`);
            }}
          >
            <sphereGeometry args={[r, 24, 24]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={(v.stressed ? 0.7 : 0.3) + (sel ? 0.5 : 0)}
              transparent
              opacity={0.85}
            />
          </mesh>
        );
      })}

      {/* ATP flowing out of the cytosol to the consumers. */}
      <FlowParticles
        max={40}
        active={active}
        color="#67e8f9"
        size={0.05}
        speed={0.55}
        place={(dir, phase, _i, out) => {
          const start = 0.15 * cellR;
          const end = 0.75 * cellR;
          out.copy(dir).multiplyScalar(start + (end - start) * phase);
        }}
      />
    </group>
  );
}
