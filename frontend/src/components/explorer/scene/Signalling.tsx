// Signalling pathways: tubes running from membrane receptors inward to the
// nucleoid. They glow with the starvation signal, and in survival mode a bead of
// signalling molecules travels inward along each pathway to activate gene response.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import type { ObjectId } from "../inspect";
import { radiusForMass, spherePoints } from "./geometry";

const PATHWAYS = 6;
const DIRS = spherePoints(PATHWAYS);

interface SignallingProps {
  frame: FrameData;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function Signalling({ frame, selected, onSelect }: SignallingProps) {
  const sig = frame.signalling;
  const beadsRef = useRef<(THREE.Mesh | null)[]>([]);
  const tubeMatsRef = useRef<(THREE.MeshStandardMaterial | null)[]>([]);

  const cellR = radiusForMass(frame.mass);
  const curves = useMemo(() => {
    return DIRS.map((dir) => {
      const start = dir.clone().multiplyScalar(cellR * 0.98);
      // Bend the pathway with a perpendicular control point.
      const perp = new THREE.Vector3(-dir.y, dir.x, dir.z * 0.5).normalize().multiplyScalar(cellR * 0.3);
      const control = dir.clone().multiplyScalar(cellR * 0.45).add(perp);
      const end = new THREE.Vector3(0, 0, 0);
      return new THREE.QuadraticBezierCurve3(start, control, end);
    });
  }, [cellR]);

  useFrame((state) => {
    const starv = sig?.signals.starvation ?? 0;
    const survival = sig?.survival ?? false;
    tubeMatsRef.current.forEach((m) => {
      if (m) m.emissiveIntensity = 0.15 + 1.4 * starv + (selected === "signalling" ? 0.5 : 0);
    });
    const t = (state.clock.elapsedTime * 0.5) % 1;
    beadsRef.current.forEach((bead, i) => {
      if (!bead) return;
      bead.visible = survival;
      if (survival) {
        const p = curves[i].getPoint(t);
        bead.position.copy(p);
      }
    });
  });

  if (!sig) return null;

  return (
    <group
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
                tubeMatsRef.current[i] = m;
              }}
              color="#f472b6"
              emissive="#ec4899"
              emissiveIntensity={0.15}
              transparent
              opacity={0.75}
              toneMapped={false}
            />
          </mesh>
          {/* Receptor at the membrane end. */}
          <mesh position={curve.getPoint(0)} scale={0.06}>
            <sphereGeometry args={[1, 10, 10]} />
            <meshStandardMaterial color="#f9a8d4" emissive="#ec4899" emissiveIntensity={0.6} toneMapped={false} />
          </mesh>
          {/* Signalling-molecule bead (survival mode only). */}
          <mesh
            ref={(m) => {
              beadsRef.current[i] = m;
            }}
            visible={false}
            scale={0.05}
          >
            <sphereGeometry args={[1, 10, 10]} />
            <meshStandardMaterial color="#fbcfe8" emissive="#f472b6" emissiveIntensity={1.6} toneMapped={false} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
