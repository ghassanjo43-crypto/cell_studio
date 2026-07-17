// A reusable, LOD-aware instanced particle field. The number of *visible* particles
// is `count` (from real simulation data) scaled by the shared LOD factor; each
// particle's position comes from a caller-supplied `place` function of its stable
// seed direction and an animation phase. Used for ribosomes, ATP, metabolites,
// vesicles and molecular flows — all data-driven, GPU-instanced.

import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef, type ReactNode } from "react";
import * as THREE from "three";
import { useDrugFx } from "./drugVisual";
import type { ObjectId } from "../inspect";
import { useHoverHandlers } from "./interact";
import { useLod } from "./lod";

export interface InstancedFieldProps {
  max: number;
  count: number; // data-driven target (pre-LOD)
  color: string;
  size?: number;
  speed?: number;
  emissive?: number;
  fade?: boolean; // fade in/out along the animation phase
  roughness?: number;
  metalness?: number;
  transparent?: boolean;
  opacity?: number;
  spin?: boolean; // gently tumble each instance (for protein-like shapes)
  diffusion?: number; // Brownian jitter amplitude (per-class diffusion coefficient)
  pulse?: number; // per-instance scale throb amplitude (e.g. ribosome translation cycles)
  soft?: number; // per-instance non-uniform deformation amplitude (organic softness)
  aspect?: boolean; // per-instance static aspect ratio (distinct protein conformations)
  glow?: boolean; // self-luminous (unlit, bloom-fed) — for energetic species (ATP, foci).
  //   Off (default) → the field is scene-lit and tone-mapped, so it reads as a matte,
  //   hydrated macromolecule with SSAO contact shadows rather than a neon particle.
  geometry?: ReactNode; // custom instance geometry (defaults to a small sphere)
  hoverId?: ObjectId; // if set, hovering any instance raises this structure's tooltip
  onSelect?: (id: ObjectId) => void; // if set, clicking opens the inspector for hoverId
  place: (dir: THREE.Vector3, phase: number, i: number, out: THREE.Vector3) => void;
}

function useSeeds(max: number) {
  return useMemo(() => {
    const dirs: THREE.Vector3[] = [];
    const phases: number[] = [];
    const freqs: number[] = []; // per-instance timescale → de-synchronised motion
    const aspects: THREE.Vector3[] = []; // per-instance non-uniform proportions
    for (let i = 0; i < max; i++) {
      const v = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1);
      if (v.lengthSq() < 1e-6) v.set(1, 0, 0);
      dirs.push(v.normalize());
      phases.push(Math.random());
      freqs.push(0.65 + Math.random() * 0.7); // 0.65–1.35× base rate
      // Each instance gets its own aspect ratio (elongated / squat / lopsided) so even
      // instances sharing one geometry read as distinct conformations.
      aspects.push(new THREE.Vector3(0.78 + Math.random() * 0.5, 0.78 + Math.random() * 0.5, 0.78 + Math.random() * 0.5));
    }
    return { dirs, phases, freqs, aspects };
  }, [max]);
}

export function InstancedField({
  max, count, color, size = 0.05, speed = 0.4, emissive = 0.7, fade = false,
  roughness = 0.5, metalness = 0, transparent = false, opacity = 1, spin = false,
  diffusion = 0, pulse = 0, soft = 0, aspect = false, glow = false, geometry, hoverId, onSelect, place,
}: InstancedFieldProps) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const { dirs, phases, freqs, aspects } = useSeeds(max);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const lod = useLod();
  // Global molecular-motion multiplier (an ATP-synthesis inhibitor slows everything).
  const fx = useDrugFx();
  // Hover handlers (always called to satisfy the hooks rule; only attached below when
  // this field represents a hoverable class).
  const hover = useHoverHandlers(hoverId ?? "cytosol");

  useFrame((state) => {
    const mesh = ref.current;
    if (!mesh) return;
    const t = state.clock.elapsedTime;
    const n = Math.max(0, Math.min(max, Math.round(count * lod.current)));
    for (let i = 0; i < n; i++) {
      // Per-instance timescale so each molecule keeps its own clock — the field never
      // reads as one synchronised animation.
      const fr = freqs[i] * fx.motion; // global slowdown under ATP depletion
      const phase = (t * speed * fr + phases[i]) % 1;
      place(dirs[i], phase, i, tmp);
      // Personality: a slow per-instance envelope that has each molecule spend part of
      // its time drifting and part nearly still (independent random pauses / docking) —
      // so the field never moves as one synchronised mass. `move` ramps 0→1, gating the
      // Brownian walk and rotation; when it lurches back up the molecule accelerates.
      const g = Math.sin(t * (0.28 + 0.4 * fr) + i * 2.399);
      const move = g > -0.15 ? Math.min(1, (g + 0.15) / 0.5) : 0;
      // Brownian thermal motion: a bounded, per-instance quasi-random walk at that
      // instance's own frequency (independent jitter, not a shared wave), gated by `move`.
      if (diffusion) {
        const tf = t * fr;
        const d = diffusion * (0.25 + 0.75 * move);
        tmp.x += Math.sin(tf * 1.7 + i * 12.9) * d;
        tmp.y += Math.sin(tf * 1.3 + i * 7.3) * d;
        tmp.z += Math.sin(tf * 2.1 + i * 4.1) * d;
      }
      dummy.position.copy(tmp);
      const rw = 0.06 * Math.sin(t * 0.9 * fr + i * 3.1); // subtle idle rotational wobble
      if (spin) dummy.rotation.set(phase * 6.28 + i + rw, i * 1.3 + rw, phase * 3.14);
      else if (soft) dummy.rotation.set(t * 0.15 * fr * (0.3 + 0.7 * move) + i, t * 0.1 * fr + i * 1.3, rw); // drift-rotate, pausing with `move`
      let s = fade ? size * (0.5 + 0.5 * Math.sin(phase * Math.PI)) : size;
      if (pulse) s *= 1 + pulse * Math.sin(t * 4 * fr + i * 1.7); // translation/working throb
      // Per-instance static aspect ratio (distinct conformations for one geometry).
      const ax = aspect ? aspects[i].x : 1;
      const ay = aspect ? aspects[i].y : 1;
      const az = aspect ? aspects[i].z : 1;
      if (soft) {
        // Non-uniform per-axis breathing at the instance's own frequency, on top of its
        // static aspect → no two instances of the same geometry ever look identical.
        dummy.scale.set(
          s * ax * (1 + soft * Math.sin(t * 1.3 * fr + i * 1.7)),
          s * ay * (1 + soft * Math.sin(t * 1.1 * fr + i * 2.9)),
          s * az * (1 + soft * Math.sin(t * 1.7 * fr + i * 0.7)),
        );
      } else if (aspect) {
        dummy.scale.set(s * ax, s * ay, s * az);
      } else {
        dummy.scale.setScalar(s);
      }
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={ref}
      args={[undefined, undefined, max]}
      frustumCulled={false}
      {...(hoverId ? hover : {})}
      onClick={
        hoverId && onSelect
          ? (e: ThreeEvent<MouseEvent>) => {
              e.stopPropagation();
              onSelect(hoverId);
            }
          : undefined
      }
    >
      {geometry ?? <sphereGeometry args={[1, 8, 8]} />}
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={emissive}
        roughness={roughness}
        metalness={metalness}
        transparent={transparent}
        opacity={opacity}
        toneMapped={!glow}
      />
    </instancedMesh>
  );
}
