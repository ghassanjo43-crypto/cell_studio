// Drug-molecule visualisation for the Drug Interaction Studio. Purely data-driven: it
// renders molecules ONLY for the drugs the current frame reports active, and each drug's
// particles accumulate at the structure it targets (DNA inhibitors hug the genome,
// membrane drugs sit in the membrane, transport inhibitors dock at the surface, …). The
// count tracks how strongly the drug is acting; motion is Brownian, docking to the target.
// Reuses the existing instanced-field renderer — no new rendering system.

import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { dockFor, drugParticleCount } from "./drugViz";
import { InstancedField } from "./InstancedField";

export function DrugMolecules({ frame, radius }: { frame: FrameData; radius: number }) {
  const drugs = frame.drugs;
  if (!drugs || drugs.length === 0) return null;
  const R = radius;

  return (
    <group>
      {drugs.map((drug, di) => {
        const dock = dockFor(drug.viz);
        const count = drugParticleCount(drug);
        return (
          <InstancedField
            key={`${drug.id}-${di}`}
            max={64}
            count={count}
            color={drug.color}
            size={0.045}
            speed={0.18}
            emissive={1.1}
            diffusion={0.03}
            soft={0.18}
            glow
            place={(dir: THREE.Vector3, phase: number, i: number, out: THREE.Vector3) => {
              const p = dir.clone();
              if (dock.ring) {
                p.y *= 0.4;
                if (p.lengthSq() < 1e-4) p.set(1, 0, 0);
                p.normalize();
              }
              // Accumulate at (and just inside) the dock radius — the drug has arrived
              // at its target and is binding, not wandering through open cytoplasm.
              const rr = R * (dock.radius - dock.spread * ((i * 0.61803) % 1));
              const wob = 1 + 0.02 * Math.sin(phase * 6.28 + i * 0.7);
              out.copy(p).multiplyScalar(rr * wob);
            }}
          />
        );
      })}
    </group>
  );
}
