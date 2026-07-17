// The genome: a coiled chromosome (torus + knot) with a replication fork that travels
// along it as replication proceeds, a growing daughter strand behind it, blinking
// transcription foci whose number tracks mRNA output, and a pink flash on mutation.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ObjectId } from "../inspect";
import type { CellVisual } from "./biomap";
import { useDrugFx } from "./drugVisual";
import { useHoverHandlers } from "./interact";
import { dnaDoubleHelixRing } from "./shapes";

const CH_R = 0.42; // chromosome ring radius (fraction of nucleoid scale)
const FOCI = 8;

interface Props {
  visual: CellVisual;
  mutating: boolean;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function Genome({ visual, mutating, selected, onSelect }: Props) {
  const group = useRef<THREE.Group>(null);
  const chromMat = useRef<THREE.MeshStandardMaterial>(null);
  const forkRef = useRef<THREE.Mesh>(null);
  const daughterRef = useRef<THREE.Mesh>(null);
  const fociRef = useRef<THREE.InstancedMesh>(null);
  const unwindRef = useRef<THREE.Group>(null);
  const mutBeadRef = useRef<THREE.Mesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const flash = useRef(0);
  const mutProp = useRef(2); // >1 = inactive; 0→1 as a mutation propagates along the DNA
  const hover = useHoverHandlers("nucleoid");
  const forkHover = useHoverHandlers("fork");
  const mutHover = useHoverHandlers("mutation");
  const fx = useDrugFx(); // DNA inhibitor: fork freezes + DNA glow decreases

  const progress = visual.replicationProgress;
  // The genome is the visual centrepiece — scaled to fill the cell's core generously.
  const nucleoidR = visual.radius * 1.05;

  useEffect(() => {
    if (mutating) {
      flash.current = 1;
      mutProp.current = 0; // start a mutation wave travelling around the chromosome
    }
  }, [mutating]);

  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    g.scale.setScalar(nucleoidR);
    // A DNA-replication inhibitor freezes the genome's machinery: rotation stalls.
    const freeze = fx.forkFreeze;
    g.rotation.y += delta * 0.35 * (1 - freeze);
    g.rotation.x = 0.5;
    flash.current = Math.max(0, flash.current - delta * 1.5);
    const t = state.clock.elapsedTime;

    if (chromMat.current) {
      const sel = selected === "nucleoid" ? 0.5 : 0;
      // The double helix is the glowing cyan hero of the scene; it flushes pink on a
      // mutation event, then returns to electric blue. Its glow dims under a DNA/RNA
      // inhibitor (dnaGlowDown).
      chromMat.current.emissiveIntensity = (0.7 + sel + flash.current * 1.8) * (1 - 0.7 * fx.dnaGlowDown);
      chromMat.current.color.setHex(flash.current > 0.1 ? 0xf472b6 : 0x38bdf8);
      chromMat.current.emissive.setHex(flash.current > 0.1 ? 0xf472b6 : 0x22d3ee);
    }

    const theta = progress * Math.PI * 2;
    const forkActive = visual.replicating || (progress > 0.001 && progress < 0.999);
    const fork = forkRef.current;
    if (fork) {
      fork.position.set(Math.cos(theta) * CH_R, Math.sin(theta) * CH_R, 0);
      fork.visible = forkActive;
      // A large, brightly-pulsing replisome so replication is unmistakably dramatic — but
      // its pulse freezes (goes still) when a replication inhibitor stalls the fork.
      fork.scale.setScalar(0.12 * (0.75 + 0.35 * Math.sin(t * 6) * (1 - freeze)));
    }
    if (daughterRef.current) daughterRef.current.visible = progress > 0.01;

    // Replication fork machinery: unwinds parental DNA ahead of it. The two opened
    // strands splay tangentially at the fork and pulse as the helicase works.
    const unwind = unwindRef.current;
    if (unwind) {
      unwind.visible = forkActive;
      if (forkActive) {
        unwind.position.set(Math.cos(theta) * CH_R, Math.sin(theta) * CH_R, 0);
        unwind.rotation.z = theta;
        const open = 0.5 + 0.5 * Math.sin(t * 8); // helicase working
        unwind.scale.set(0.085, 0.07 + 0.05 * open, 0.085);
      }
    }

    // Mutation propagation: a bright lesion travels around the chromosome after a
    // mutation event, then fades — the mutation "spreading" along the DNA.
    const bead = mutBeadRef.current;
    if (bead) {
      mutProp.current = Math.min(2, mutProp.current + delta * 0.7);
      const active = mutProp.current <= 1;
      bead.visible = active;
      if (active) {
        const a = mutProp.current * Math.PI * 2;
        bead.position.set(Math.cos(a) * CH_R, Math.sin(a) * CH_R, 0.04);
        const fade = 1 - mutProp.current;
        bead.scale.setScalar(0.06 * (0.6 + 0.4 * Math.sin(t * 20)) * (0.4 + 0.6 * fade));
      }
    }

    // Transcription foci: `transcriptionFoci` active genes blink around the ring.
    const foci = fociRef.current;
    if (foci) {
      const n = Math.min(FOCI, visual.transcriptionFoci);
      for (let i = 0; i < n; i++) {
        const a = (i / FOCI) * Math.PI * 2;
        dummy.position.set(Math.cos(a) * CH_R, Math.sin(a) * CH_R, 0.03);
        const blink = 0.4 + 0.6 * Math.abs(Math.sin(t * 2.5 + i * 1.7));
        dummy.scale.setScalar(0.05 * blink);
        dummy.updateMatrix();
        foci.setMatrixAt(i, dummy.matrix);
      }
      foci.count = n;
      foci.instanceMatrix.needsUpdate = true;
    }
  });

  return (
    <group ref={group}>
      {/* Chromosome ring (clickable). */}
      <mesh
        {...hover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("nucleoid");
        }}
      >
        <torusGeometry args={[CH_R, 0.03, 16, 160]} />
        <meshStandardMaterial ref={chromMat} color="#38bdf8" emissive="#22d3ee" emissiveIntensity={0.7} roughness={0.35} metalness={0.1} toneMapped={false} />
      </mesh>
      {/* The double-helix hero: two sugar-phosphate strands + base-pair rungs wound
          around the circular chromosome — the glowing cyan centrepiece of the scene. */}
      <mesh>
        <primitive object={dnaDoubleHelixRing(CH_R)} attach="geometry" />
        <meshStandardMaterial color="#7dd3fc" emissive="#38bdf8" emissiveIntensity={0.9} roughness={0.3} metalness={0.15} toneMapped={false} />
      </mesh>
      {/* Chromosome domains — supercoiled looped sub-domains of the folded genome. Six
          plectonemic loops of varied handedness give the nucleoid real folded depth,
          rendered in a deeper blue so they read as folded DNA behind the bright helix. */}
      {[
        { pos: [CH_R * 0.55, CH_R * 0.35, 0.05], s: 0.36, p: 3, q: 5 },
        { pos: [-CH_R * 0.5, -CH_R * 0.42, -0.05], s: 0.32, p: 2, q: 5 },
        { pos: [CH_R * 0.1, -CH_R * 0.6, 0.04], s: 0.28, p: 3, q: 4 },
        { pos: [-CH_R * 0.62, CH_R * 0.3, 0.06], s: 0.3, p: 2, q: 7 },
        { pos: [CH_R * 0.5, -CH_R * 0.28, -0.07], s: 0.26, p: 3, q: 7 },
        { pos: [-CH_R * 0.12, CH_R * 0.62, -0.04], s: 0.29, p: 4, q: 3 },
      ].map((d, i) => (
        <mesh key={i} position={d.pos as [number, number, number]} scale={d.s} rotation={[i * 0.7, i * 1.1, 0]}>
          <torusKnotGeometry args={[0.5, 0.05, 80, 8, d.p, d.q]} />
          <meshStandardMaterial color="#3b82f6" emissive="#2563eb" emissiveIntensity={0.35} roughness={0.5} metalness={0.1} toneMapped={false} />
        </mesh>
      ))}
      {/* Daughter strand grows with replication progress. */}
      <mesh ref={daughterRef} position={[0, 0, 0.06]} visible={false}>
        <torusGeometry args={[CH_R, 0.055, 16, 96, Math.max(0.001, progress) * Math.PI * 2]} />
        <meshStandardMaterial color="#a5f3fc" emissive="#67e8f9" emissiveIntensity={1.1} toneMapped={false} />
      </mesh>
      {/* Replication fork. */}
      <mesh
        ref={forkRef}
        visible={false}
        {...forkHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("fork");
        }}
      >
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial color="#ffffff" emissive="#7dd3fc" emissiveIntensity={2.2} toneMapped={false} />
      </mesh>
      {/* Unwound parental strands opening ahead of the fork (helicase). */}
      <group ref={unwindRef} visible={false}>
        <mesh position={[0, 0.7, 0]} rotation={[0, 0, 0.5]}>
          <cylinderGeometry args={[0.12, 0.12, 1.4, 6]} />
          <meshStandardMaterial color="#a5f3fc" emissive="#38bdf8" emissiveIntensity={0.9} toneMapped={false} />
        </mesh>
        <mesh position={[0, 0.7, 0]} rotation={[0, 0, -0.5]}>
          <cylinderGeometry args={[0.12, 0.12, 1.4, 6]} />
          <meshStandardMaterial color="#a5f3fc" emissive="#38bdf8" emissiveIntensity={0.9} toneMapped={false} />
        </mesh>
      </group>
      {/* Mutation lesion propagating around the chromosome. */}
      <mesh
        ref={mutBeadRef}
        visible={false}
        {...mutHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("mutation");
        }}
      >
        <sphereGeometry args={[1, 10, 10]} />
        <meshStandardMaterial color="#fda4af" emissive="#f43f5e" emissiveIntensity={2.0} toneMapped={false} />
      </mesh>
      {/* Transcription foci. */}
      <instancedMesh ref={fociRef} args={[undefined, undefined, FOCI]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshStandardMaterial color="#67e8f9" emissive="#22d3ee" emissiveIntensity={1.3} toneMapped={false} />
      </instancedMesh>
    </group>
  );
}
