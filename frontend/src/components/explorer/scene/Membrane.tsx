// The membrane: a translucent phospholipid bilayer whose colour tracks lifecycle
// status and whose opacity tracks integrity. Damage patches appear as integrity
// falls; a green repair glow pulses while the membrane phenotype is up-regulated.
// Transport proteins stud the surface and pulse with transport activity.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { statusColor } from "../../theme";
import { transportActivity } from "../inspect";
import type { ObjectId } from "../inspect";
import { radiusForMass, spherePoints } from "./geometry";

const TRANSPORTER_DIRS = spherePoints(22);
const DAMAGE_DIRS = spherePoints(16);

interface MembraneProps {
  frame: FrameData;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function Membrane({ frame, selected, onSelect }: MembraneProps) {
  const groupRef = useRef<THREE.Group>(null);
  const outerRef = useRef<THREE.MeshStandardMaterial>(null);
  const repairRef = useRef<THREE.MeshBasicMaterial>(null);
  const transRef = useRef<THREE.InstancedMesh>(null);
  const prevIntegrity = useRef(frame.membrane_integrity);
  const repairPulse = useRef(0);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const integrity = frame.membrane_integrity;
  const status = frame.status ?? null;

  // A rising integrity means active repair — flash the repair glow.
  useEffect(() => {
    if (integrity > prevIntegrity.current + 1e-4) repairPulse.current = 1;
    prevIntegrity.current = integrity;
  }, [integrity]);

  useFrame((state, delta) => {
    const group = groupRef.current;
    if (!group) return;
    const r = radiusForMass(frame.mass);
    const s = group.scale.x + (r - group.scale.x) * Math.min(1, delta * 6);
    group.scale.setScalar(s);
    group.rotation.y += delta * 0.12;

    if (outerRef.current) {
      outerRef.current.color.lerp(new THREE.Color(statusColor(status)), Math.min(1, delta * 4));
      outerRef.current.opacity = 0.2 + 0.45 * Math.max(0.1, integrity);
      const sel = selected === "membrane";
      outerRef.current.emissive.setRGB(sel ? 0.15 : 0, sel ? 0.25 : 0, sel ? 0.4 : 0);
    }

    repairPulse.current = Math.max(0, repairPulse.current - delta * 1.2);
    if (repairRef.current) repairRef.current.opacity = repairPulse.current * 0.5;

    // Transporters pulse with import activity.
    const mesh = transRef.current;
    if (mesh) {
      const act = THREE.MathUtils.clamp(transportActivity(frame), 0.3, 2.2);
      const pulse = 0.7 + 0.3 * Math.sin(state.clock.elapsedTime * 3);
      for (let i = 0; i < TRANSPORTER_DIRS.length; i++) {
        dummy.position.copy(TRANSPORTER_DIRS[i]).multiplyScalar(1.0);
        dummy.scale.setScalar((0.05 + 0.03 * act) * pulse);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
      const tsel = selected === "transport";
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.emissiveIntensity = (tsel ? 0.9 : 0.4) + 0.4 * (act - 1);
    }
  });

  // Damage patches: more of them as integrity falls.
  const damageCount = Math.round((1 - integrity) * DAMAGE_DIRS.length);

  return (
    <group ref={groupRef}>
      {/* Outer bilayer leaflet — clickable membrane body. */}
      <mesh
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("membrane");
        }}
      >
        <sphereGeometry args={[1, 48, 48]} />
        <meshStandardMaterial ref={outerRef} transparent roughness={0.4} metalness={0.05} color={statusColor(status)} depthWrite={false} />
      </mesh>
      {/* Inner leaflet — thin, gives the bilayer a sense of thickness. */}
      <mesh scale={0.94}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color={statusColor(status)} transparent opacity={0.08} side={THREE.BackSide} />
      </mesh>
      {/* Repair glow. */}
      <mesh scale={1.02}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial ref={repairRef} color="#4ade80" transparent opacity={0} depthWrite={false} />
      </mesh>
      {/* Transport proteins. */}
      <instancedMesh
        ref={transRef}
        args={[undefined, undefined, TRANSPORTER_DIRS.length]}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("transport");
        }}
      >
        <sphereGeometry args={[1, 10, 10]} />
        <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={0.4} toneMapped={false} />
      </instancedMesh>
      {/* Damage patches. */}
      {DAMAGE_DIRS.slice(0, damageCount).map((d, i) => (
        <mesh key={i} position={[d.x, d.y, d.z]} scale={0.09}>
          <sphereGeometry args={[1, 8, 8]} />
          <meshStandardMaterial color="#fb7185" emissive="#7f1d1d" emissiveIntensity={0.5} />
        </mesh>
      ))}
    </group>
  );
}
