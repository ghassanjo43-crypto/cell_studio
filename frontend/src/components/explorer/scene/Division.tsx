// The division furrow: once the chromosome has finished replicating, a constriction
// ring forms at the cell equator and tightens. When a division event fires, the ring
// flares briefly to mark the daughter cells separating.

import { useFrame } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { radiusForMass } from "./geometry";

interface DivisionProps {
  frame: FrameData;
  dividing: boolean; // a division event is active at the current timeline position
}

export function Division({ frame, dividing }: DivisionProps) {
  const ringRef = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshStandardMaterial>(null);
  const flare = useRef(0);
  const pinch = useRef(0);

  const ready = (frame.replication?.complete ?? false) && frame.alive;

  useEffect(() => {
    if (dividing) flare.current = 1;
  }, [dividing]);

  useFrame((_, delta) => {
    const ring = ringRef.current;
    if (!ring) return;
    const cellR = radiusForMass(frame.mass);
    // Ease the pinch in while ready, out otherwise.
    const target = ready ? 1 : 0;
    pinch.current += (target - pinch.current) * Math.min(1, delta * 2);
    flare.current = Math.max(0, flare.current - delta * 1.4);

    const visible = pinch.current > 0.02 || flare.current > 0.02;
    ring.visible = visible;
    if (!visible) return;

    // Constriction: the ring's radius shrinks as the furrow deepens.
    const constrict = 1 - 0.35 * pinch.current + 0.4 * flare.current;
    ring.scale.set(cellR * constrict, cellR * constrict, cellR * constrict);
    ring.rotation.x = Math.PI / 2;
    if (ringMat.current) {
      ringMat.current.opacity = Math.min(1, 0.4 * pinch.current + flare.current);
      ringMat.current.emissiveIntensity = 0.4 + 1.6 * flare.current;
    }
  });

  return (
    <mesh ref={ringRef} visible={false}>
      <torusGeometry args={[1.0, 0.05, 12, 48]} />
      <meshStandardMaterial ref={ringMat} color="#4ade80" emissive="#4ade80" emissiveIntensity={0.4} transparent opacity={0} toneMapped={false} />
    </mesh>
  );
}
