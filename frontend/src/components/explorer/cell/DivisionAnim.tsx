// Cell division, animated from engine state. When replication completes the cell
// becomes "ready" and a constriction furrow forms at the equator. On a division
// event the furrow deepens (cytokinesis), the chromatids separate, and two daughter
// outlines pinch apart before the cycle resets.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { ObjectId } from "../inspect";
import type { CellVisual } from "./biomap";
import { useHoverHandlers } from "./interact";

interface Props {
  visual: CellVisual;
  dividing: boolean;
  onSelect?: (id: ObjectId) => void;
}

export function DivisionAnim({ visual, dividing, onSelect }: Props) {
  const furrowHover = useHoverHandlers("division");
  const ring = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshStandardMaterial>(null);
  const dLeft = useRef<THREE.Mesh>(null);
  const dRight = useRef<THREE.Mesh>(null);
  const cLeft = useRef<THREE.Mesh>(null);
  const cRight = useRef<THREE.Mesh>(null);
  const anim = useRef(0); // 1 at the division event → decays to 0
  const pinch = useRef(0);

  const ready = visual.replicationComplete && visual.metabolicActivity >= 0; // ready = replicated & alive

  useEffect(() => {
    if (dividing) anim.current = 1;
  }, [dividing]);

  useFrame((_, delta) => {
    const R = visual.radius;
    anim.current = Math.max(0, anim.current - delta * 0.7);
    const a = anim.current; // 1 → 0 over the cytokinesis
    const sep = 1 - a; // 0 → 1 as daughters separate
    const target = ready && visual.replicationComplete ? 1 : 0;
    pinch.current += (target - pinch.current) * Math.min(1, delta * 2);

    // Constriction furrow.
    const r = ring.current;
    if (r) {
      const visible = pinch.current > 0.02 || a > 0.02;
      r.visible = visible;
      if (visible) {
        const constrict = 1 - 0.35 * pinch.current - (a > 0.02 ? 0.55 * sep : 0);
        r.scale.set(R * constrict, R * constrict, R * constrict);
        r.rotation.x = Math.PI / 2;
        if (ringMat.current) {
          ringMat.current.opacity = Math.min(1, 0.4 * pinch.current + a);
          ringMat.current.emissiveIntensity = 0.4 + 1.6 * a;
        }
      }
    }

    // Daughter outlines + chromatids separating during the event.
    const off = R * 1.25 * sep;
    for (const [mesh, dirn] of [
      [dLeft.current, -1],
      [dRight.current, 1],
    ] as const) {
      if (!mesh) continue;
      mesh.visible = a > 0.02;
      if (mesh.visible) {
        mesh.position.x = dirn * off;
        mesh.scale.setScalar(R * 0.85);
        (mesh.material as THREE.MeshBasicMaterial).opacity = a * 0.4;
      }
    }
    for (const [mesh, dirn] of [
      [cLeft.current, -1],
      [cRight.current, 1],
    ] as const) {
      if (!mesh) continue;
      mesh.visible = a > 0.02;
      if (mesh.visible) mesh.position.x = dirn * off * 0.6;
    }
  });

  return (
    <group>
      <mesh
        ref={ring}
        visible={false}
        {...furrowHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect?.("division");
        }}
      >
        <torusGeometry args={[1.0, 0.05, 12, 48]} />
        <meshStandardMaterial ref={ringMat} color="#4ade80" emissive="#4ade80" emissiveIntensity={0.4} transparent opacity={0} toneMapped={false} />
      </mesh>

      <mesh ref={dLeft} visible={false}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial color="#4ade80" wireframe transparent opacity={0} />
      </mesh>
      <mesh ref={dRight} visible={false}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial color="#4ade80" wireframe transparent opacity={0} />
      </mesh>

      <mesh ref={cLeft} visible={false} scale={0.09}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial color="#c4b5fd" emissive="#a78bfa" emissiveIntensity={1.2} toneMapped={false} />
      </mesh>
      <mesh ref={cRight} visible={false} scale={0.09}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial color="#c4b5fd" emissive="#a78bfa" emissiveIntensity={1.2} toneMapped={false} />
      </mesh>
    </group>
  );
}
