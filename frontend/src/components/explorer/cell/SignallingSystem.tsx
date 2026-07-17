// Signalling network: pathways run from membrane receptors inward to the nucleoid.
// Signal molecules propagate along them toward the genome; the tube glow and the
// number/speed of propagating pulses scale with the starvation signal, and survival
// mode visibly changes the behaviour (red, faster, more pulses).

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { ObjectId } from "../inspect";
import { spherePoints } from "../scene/geometry";
import type { CellVisual } from "./biomap";
import { useHoverHandlers } from "./interact";

const PATHWAYS = 6;
const MAX_BEADS = 3;
const DIRS = spherePoints(PATHWAYS);

interface Props {
  visual: CellVisual;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function SignallingSystem({ visual, selected, onSelect }: Props) {
  const sig = visual.signalling;
  const tubeMats = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const beadsRef = useRef<THREE.InstancedMesh>(null);
  const beadMat = useRef<THREE.MeshStandardMaterial>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const hover = useHoverHandlers("signalling");
  const R = visual.radius;

  const curves = useMemo(() => {
    return DIRS.map((dir) => {
      const start = dir.clone().multiplyScalar(R * 0.98);
      const perp = new THREE.Vector3(-dir.y, dir.x, dir.z * 0.5).normalize().multiplyScalar(R * 0.3);
      const control = dir.clone().multiplyScalar(R * 0.45).add(perp);
      return new THREE.QuadraticBezierCurve3(start, control, new THREE.Vector3(0, 0, 0));
    });
  }, [R]);

  useFrame((state) => {
    const starv = sig?.starvation ?? 0;
    const survival = sig?.survival ?? false;
    const t = state.clock.elapsedTime;
    const selGlow = selected === "signalling" ? 0.5 : 0;

    const col = new THREE.Color(survival ? "#ef4444" : "#ec4899");
    tubeMats.current.forEach((m) => {
      if (!m) return;
      m.emissiveIntensity = 0.12 + 1.4 * starv + selGlow;
      m.color.copy(col);
      m.emissive.copy(col);
    });

    // Propagating signal molecules: more + faster with starvation, most in survival.
    const beadsPer = survival ? MAX_BEADS : starv > 0.5 ? 2 : starv > 0.15 ? 1 : 0;
    const speed = 0.4 + 0.7 * starv + (survival ? 0.5 : 0);
    const mesh = beadsRef.current;
    if (mesh) {
      let idx = 0;
      for (let p = 0; p < PATHWAYS; p++) {
        for (let b = 0; b < beadsPer; b++) {
          const phase = (t * speed + b / MAX_BEADS + p * 0.13) % 1;
          const pt = curves[p].getPoint(phase);
          dummy.position.copy(pt);
          dummy.scale.setScalar(0.05);
          dummy.updateMatrix();
          mesh.setMatrixAt(idx++, dummy.matrix);
        }
      }
      mesh.count = idx;
      mesh.instanceMatrix.needsUpdate = true;
      if (beadMat.current) {
        beadMat.current.color.copy(col);
        beadMat.current.emissive.copy(col);
      }
    }
  });

  if (!sig) return null;

  return (
    <group
      {...hover}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        onSelect("signalling");
      }}
    >
      {curves.map((curve, i) => (
        <group key={i}>
          <mesh>
            <tubeGeometry args={[curve, 40, 0.014, 8, false]} />
            <meshStandardMaterial
              ref={(m) => {
                tubeMats.current[i] = m;
              }}
              color="#ec4899"
              emissive="#ec4899"
              emissiveIntensity={0.12}
              transparent
              opacity={0.7}
              toneMapped={false}
            />
          </mesh>
          {/* Receptor at the membrane end. */}
          <mesh position={curve.getPoint(0)} scale={0.06}>
            <sphereGeometry args={[1, 10, 10]} />
            <meshStandardMaterial color="#f9a8d4" emissive="#ec4899" emissiveIntensity={0.6} toneMapped={false} />
          </mesh>
        </group>
      ))}

      {/* Propagating signal molecules. */}
      <instancedMesh ref={beadsRef} args={[undefined, undefined, PATHWAYS * MAX_BEADS]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshStandardMaterial ref={beadMat} color="#fbcfe8" emissive="#f472b6" emissiveIntensity={1.6} toneMapped={false} />
      </instancedMesh>
    </group>
  );
}
