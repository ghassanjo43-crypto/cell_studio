// The genome as a coiled chromosome (torus). A bright replication fork travels
// around it as replication progresses, and a second "daughter" strand grows behind
// the fork. Mutation events flash the chromosome briefly.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import type { ObjectId } from "../inspect";
import { radiusForMass } from "./geometry";

const CHROM_R = 0.42; // torus radius as a fraction of cell radius

interface NucleoidProps {
  frame: FrameData;
  mutating: boolean;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function Nucleoid({ frame, mutating, selected, onSelect }: NucleoidProps) {
  const groupRef = useRef<THREE.Group>(null);
  const chromRef = useRef<THREE.MeshStandardMaterial>(null);
  const forkRef = useRef<THREE.Mesh>(null);
  const daughterRef = useRef<THREE.Mesh>(null);
  const flash = useRef(0);

  const progress = THREE.MathUtils.clamp(frame.replication?.progress ?? 0, 0, 1);
  const replicating = frame.replication?.replicating ?? false;

  useEffect(() => {
    if (mutating) flash.current = 1;
  }, [mutating]);

  useFrame((state, delta) => {
    const group = groupRef.current;
    if (!group) return;
    const cellR = radiusForMass(frame.mass);
    group.scale.setScalar(cellR);
    group.rotation.y += delta * 0.4;
    group.rotation.x = 0.5;

    flash.current = Math.max(0, flash.current - delta * 1.5);

    if (chromRef.current) {
      const sel = selected === "nucleoid" ? 0.4 : 0;
      chromRef.current.emissiveIntensity = 0.25 + sel + flash.current * 1.5;
      chromRef.current.color.setHex(flash.current > 0.1 ? 0xf472b6 : 0xa78bfa);
    }

    // Fork bead rides around the chromosome ring at angle = progress.
    const fork = forkRef.current;
    if (fork) {
      const theta = progress * Math.PI * 2;
      fork.position.set(Math.cos(theta) * CHROM_R, Math.sin(theta) * CHROM_R, 0);
      fork.visible = replicating || (progress > 0.001 && progress < 0.999);
      const pulse = 0.6 + 0.4 * Math.sin(state.clock.elapsedTime * 6);
      fork.scale.setScalar(0.08 * pulse);
    }
    // Newly synthesised daughter strand grows behind the fork.
    if (daughterRef.current) {
      daughterRef.current.visible = progress > 0.01;
    }
  });

  return (
    <group ref={groupRef}>
      <mesh
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("nucleoid");
        }}
      >
        <torusGeometry args={[CHROM_R, 0.05, 16, 80]} />
        <meshStandardMaterial ref={chromRef} color="#a78bfa" emissive="#a78bfa" emissiveIntensity={0.25} toneMapped={false} />
      </mesh>
      {/* Daughter strand: partial torus that grows with replication progress. */}
      <mesh ref={daughterRef} position={[0, 0, 0.06]} visible={false}>
        <torusGeometry args={[CHROM_R, 0.035, 12, 64, Math.max(0.001, progress) * Math.PI * 2]} />
        <meshStandardMaterial color="#c4b5fd" emissive="#c4b5fd" emissiveIntensity={0.6} toneMapped={false} />
      </mesh>
      {/* Replication fork. */}
      <mesh ref={forkRef} visible={false}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial color="#fde68a" emissive="#fbbf24" emissiveIntensity={1.4} toneMapped={false} />
      </mesh>
    </group>
  );
}
