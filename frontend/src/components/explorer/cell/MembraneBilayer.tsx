// The membrane as a phospholipid bilayer: two leaflets of instanced lipid heads in
// constant thermal motion, with embedded transport proteins, channels and receptors.
// Data-driven: opacity/lipid-density = integrity, damage patches ∝ (1-integrity),
// green repair shimmer while membrane synthesis is up-regulated, transporter pulse ∝
// transport activity, channel aperture ∝ permeability, receptor glow ∝ starvation.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ObjectId } from "../inspect";
import { spherePoints } from "../scene/geometry";
import type { CellVisual } from "./biomap";
import { useDrugFx } from "./drugVisual";
import { makeFresnelMaterial } from "./fresnelMaterial";
import { useHoverHandlers } from "./interact";
import { useLod } from "./lod";
import { applyMembraneUndulation } from "./membraneUndulation";
import { channelGeometry, proteinGeometry, receptorGeometry } from "./shapes";

const LIPIDS = 300;

// A small deterministic hash → stable per-lipid randomness (irregular spacing, thickness
// and head size), so the bilayer reads as living soft matter rather than an even lattice.
function hash1(i: number, salt: number): number {
  const s = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

// Perturb an even Fibonacci lattice so lipids sit at irregular spacing (with occasional
// local bunching) instead of a mathematically perfect grid.
function jitterPoints(pts: THREE.Vector3[], amp: number, salt: number): THREE.Vector3[] {
  return pts.map((p, i) => {
    const t = new THREE.Vector3(hash1(i, salt) - 0.5, hash1(i, salt + 5) - 0.5, hash1(i, salt + 9) - 0.5);
    return p.clone().addScaledVector(t, amp).normalize();
  });
}

// Cluster `n` points into a few membrane "islands" (protein complexes cluster in the
// bilayer rather than spreading evenly).
function islandPoints(n: number, islands: number, spread: number, salt: number): THREE.Vector3[] {
  const centers = spherePoints(islands);
  const out: THREE.Vector3[] = [];
  for (let i = 0; i < n; i++) {
    const c = centers[i % islands];
    const off = new THREE.Vector3(hash1(i, salt) - 0.5, hash1(i, salt + 3) - 0.5, hash1(i, salt + 7) - 0.5);
    out.push(c.clone().addScaledVector(off, spread).normalize());
  }
  return out;
}

const OUTER = jitterPoints(spherePoints(LIPIDS), 0.09, 1);
const INNER = jitterPoints(spherePoints(LIPIDS), 0.09, 2);
// Per-lipid thickness offset (low-frequency membrane thickness variation) + head-size
// variation, precomputed once so they are stable across frames.
const LIPID_THICK = Array.from({ length: LIPIDS }, (_, i) => (hash1(i, 21) - 0.5) * 0.06);
const LIPID_SIZE = Array.from({ length: LIPIDS }, (_, i) => 0.72 + hash1(i, 33) * 0.7);
const DAMAGE_DIRS = spherePoints(18);
// Embedded proteins cluster into a few tight islands (dense patches with bare membrane
// between) rather than spreading evenly — natural protein islands emerge.
const TRANSPORTERS = islandPoints(16, 3, 0.16, 11);
const CHANNELS = islandPoints(12, 2, 0.18, 17);
const RECEPTORS = islandPoints(10, 2, 0.15, 23);

interface Props {
  visual: CellVisual;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

// Membrane undulation matching membraneUndulation.ts / fresnelMaterial.ts so the lipid
// heads ride the same living, multi-octave wave as the shells they sit in.
function membraneWob(p: THREE.Vector3, t: number, amp: number, ripple: number): number {
  const w1 = Math.sin(p.x * 6.0 + t * 1.3) * Math.sin(p.y * 5.0 + t * 1.1) * Math.sin(p.z * 6.0 + t * 0.9);
  const w2 = Math.sin(p.x * 14.0 - t * 2.1) * Math.sin(p.y * 13.0 + t * 1.7) * Math.sin(p.z * 15.0 - t * 1.9);
  const w3 = Math.sin(p.x * 27.0 + t * 3.4) * Math.sin(p.z * 24.0 - t * 2.9);
  return w1 * amp + w2 * amp * 0.45 + w3 * (amp * 0.25 + ripple);
}

export function MembraneBilayer({ visual, selected, onSelect }: Props) {
  const group = useRef<THREE.Group>(null);
  const repairMat = useRef<THREE.MeshBasicMaterial>(null);
  const lipidRef = useRef<THREE.InstancedMesh>(null);
  const transRef = useRef<THREE.InstancedMesh>(null);
  const chanRef = useRef<THREE.InstancedMesh>(null);
  const recRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const lod = useLod();
  const repair = useRef(0);
  const fresnel = useMemo(() => makeFresnelMaterial(visual.color), [visual.color]);
  const fx = useDrugFx(); // membrane disruptor: extra irregularity; transport inhibitor: transporter slow
  const membraneHover = useHoverHandlers("membrane");
  const transportHover = useHoverHandlers("transport");
  const channelHover = useHoverHandlers("channel");
  const receptorHover = useHoverHandlers("receptor");
  const lipidHover = useHoverHandlers("lipid");

  // Undulating PBR materials for the outer leaflet and the inner surrounding wall.
  const outerMat = useMemo(
    () => new THREE.MeshStandardMaterial({ transparent: true, roughness: 0.45, metalness: 0.05, depthWrite: false, color: new THREE.Color(visual.color) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const wallMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: new THREE.Color(visual.color), roughness: 0.9, metalness: 0.04, transparent: true, opacity: 0.24, side: THREE.BackSide, depthWrite: false }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const setOuterUndu = useMemo(() => applyMembraneUndulation(outerMat), [outerMat]);
  const setWallUndu = useMemo(() => applyMembraneUndulation(wallMat), [wallMat]);

  useEffect(() => {
    if (visual.membraneRepair > 1.05) repair.current = 1;
  }, [visual.membraneRepair]);

  useEffect(() => () => {
    fresnel.dispose();
    outerMat.dispose();
    wallMat.dispose();
  }, [fresnel, outerMat, wallMat]);

  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    const s = g.scale.x + (visual.radius - g.scale.x) * Math.min(1, delta * 6);
    g.scale.setScalar(s);
    g.rotation.y += delta * 0.08;
    const t = state.clock.elapsedTime;

    // Tension: a healthy membrane is tight (small amp); it slackens as integrity drops
    // and during a repair pulse. Ripple = fast active-transport shimmer ∝ transport.
    // A healthy membrane already breathes visibly (raised base amplitude), slackening
    // further as integrity drops and during a repair pulse — so it never reads as a
    // perfect, rigid sphere.
    const amp = 0.022 + (1 - Math.max(0.1, visual.integrity)) * 0.05 + repair.current * 0.022
      + fx.membraneDamage * 0.03; // a disruptor/oxidative drug makes the surface more irregular
    const ripple = 0.005 + Math.max(0, visual.transportActivity - 1) * 0.013;
    fresnel.uniforms.uTime.value = t;
    fresnel.uniforms.uAmp.value = amp;
    fresnel.uniforms.uRipple.value = ripple;
    setOuterUndu(t, amp, ripple);
    setWallUndu(t, amp, ripple);

    // Proximity: 0 far away (establishing shot) → 1 up-close / inside. As we approach,
    // the bright silhouette (Fresnel rim + the front leaflet's edge) is faded out so the
    // membrane stops reading as a hard glowing *circle* and instead becomes a wall that
    // dissolves into the fog — the single biggest cue that removes the "sphere" feeling.
    const camDist = state.camera.position.length();
    const proximity = THREE.MathUtils.clamp(1 - (camDist - visual.radius) / (visual.radius * 2.2), 0, 1);

    outerMat.color.lerp(new THREE.Color(visual.color), Math.min(1, delta * 4));
    outerMat.opacity = (0.16 + 0.4 * Math.max(0.1, visual.integrity)) * (1 - 0.7 * proximity);
    const sel = selected === "membrane" ? 0.25 : 0;
    outerMat.emissive.setRGB(sel * 0.4, sel, sel * 1.4);
    wallMat.color.lerp(new THREE.Color(visual.color), Math.min(1, delta * 4));

    repair.current = Math.max(0, repair.current - delta * 0.8);
    if (repairMat.current) repairMat.current.opacity = repair.current * 0.45;

    // Fresnel rim — view-dependent membrane edge glow; suppressed as we move inside.
    fresnel.uniforms.uColor.value.set(visual.color);
    fresnel.uniforms.uOpacity.value = (0.3 + 0.4 * visual.integrity) * (1 - 0.9 * proximity);
    fresnel.uniforms.uIntensity.value = (1.0 + (selected === "membrane" ? 0.7 : 0)) * (1 - 0.85 * proximity);

    // Lipid heads ride the membrane wave (thermal motion); density falls with damage.
    const lm = lipidRef.current;
    if (lm) {
      const n = Math.min(LIPIDS * 2, Math.round(LIPIDS * 2 * lod.current * (0.45 + 0.55 * visual.integrity)));
      for (let i = 0; i < n; i++) {
        const outer = i < LIPIDS;
        const li = outer ? i : i - LIPIDS;
        const p = outer ? OUTER[i] : INNER[li];
        // Wider gap between the leaflets so the bilayer reads as two distinct rows of
        // heads, plus a per-lipid low-frequency thickness offset so the membrane's
        // thickness gently varies (living soft matter, not a constant-radius shell).
        const base = (outer ? 1.0 : 0.86) + LIPID_THICK[li];
        // Lipid-raft domains: a low-frequency field over the sphere makes heads bunch
        // into denser patches (ordered domains) separated by thinner regions.
        const dom = 0.5 + 0.5 * Math.abs(Math.sin(p.x * 3.1 + p.y * 2.7 + p.z * 3.3 + 0.6 * Math.sin(t * 0.2)));
        const wave = membraneWob(p, t, amp, ripple) + 0.006 * Math.sin(t * 3 + i);
        dummy.position.copy(p).multiplyScalar(base + wave + 0.012 * dom); // rafts sit proud
        // Clustering tightens on a healthy membrane and within a raft domain; per-lipid
        // size variation so the heads are irregular, not a uniform bead-set.
        const cluster = 0.07 * LIPID_SIZE[li] * (0.6 + 0.7 * dom) * (0.65 + 0.35 * visual.integrity);
        dummy.scale.setScalar(cluster);
        dummy.updateMatrix();
        lm.setMatrixAt(i, dummy.matrix);
      }
      lm.count = n;
      lm.instanceMatrix.needsUpdate = true;
    }

    // Transport proteins pulse with import activity.
    const tr = transRef.current;
    if (tr) {
      const act = visual.transportActivity;
      // Transporter animation slows when a transport inhibitor blocks uptake.
      const pulse = 0.7 + 0.3 * Math.sin(t * 3.5 * (1 - fx.transportBlock));
      for (let i = 0; i < TRANSPORTERS.length; i++) {
        dummy.position.copy(TRANSPORTERS[i]);
        dummy.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), TRANSPORTERS[i]);
        dummy.scale.setScalar((0.085 + 0.05 * act) * pulse);
        dummy.updateMatrix();
        tr.setMatrixAt(i, dummy.matrix);
      }
      tr.instanceMatrix.needsUpdate = true;
      (tr.material as THREE.MeshStandardMaterial).emissiveIntensity =
        (selected === "transport" ? 0.9 : 0.45) + 0.4 * (act - 1);
    }

    // Channels: aperture (vertical scale) tracks permeability.
    const ch = chanRef.current;
    if (ch) {
      for (let i = 0; i < CHANNELS.length; i++) {
        const dir = CHANNELS[i];
        dummy.position.copy(dir);
        dummy.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        dummy.scale.set(0.055, 0.06 + 0.08 * visual.permeability, 0.055);
        dummy.updateMatrix();
        ch.setMatrixAt(i, dummy.matrix);
      }
      ch.instanceMatrix.needsUpdate = true;
    }

    // Receptors glow with the starvation signal (if any).
    const rc = recRef.current;
    if (rc) {
      const starv = visual.signalling?.starvation ?? 0;
      for (let i = 0; i < RECEPTORS.length; i++) {
        dummy.position.copy(RECEPTORS[i]).multiplyScalar(1.0);
        dummy.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), RECEPTORS[i]);
        dummy.scale.setScalar(0.08);
        dummy.updateMatrix();
        rc.setMatrixAt(i, dummy.matrix);
      }
      rc.instanceMatrix.needsUpdate = true;
      (rc.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.3 + 1.4 * starv;
    }
  });

  const damageCount = Math.round((1 - visual.integrity) * DAMAGE_DIRS.length);

  return (
    <group ref={group}>
      {/* Inner membrane wall — only visible from inside the cell (the surrounding wall). */}
      <mesh scale={0.965} renderOrder={1}>
        <sphereGeometry args={[1, 48, 48]} />
        <primitive object={wallMat} attach="material" />
      </mesh>
      {/* Inner leaflet — gives the bilayer thickness. */}
      <mesh scale={0.9} renderOrder={2}>
        <sphereGeometry args={[1, 40, 40]} />
        <meshBasicMaterial color={visual.color} transparent opacity={0.06} side={THREE.BackSide} depthWrite={false} />
      </mesh>
      {/* Outer leaflet (clickable membrane body). Drawn after interior traffic so the
          membrane composites over the cytoplasm molecules. */}
      <mesh
        renderOrder={3}
        {...membraneHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("membrane");
        }}
      >
        <sphereGeometry args={[1, 64, 64]} />
        <primitive object={outerMat} attach="material" />
      </mesh>
      {/* Repair shimmer. */}
      <mesh scale={1.03} renderOrder={4}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial ref={repairMat} color="#4ade80" transparent opacity={0} depthWrite={false} />
      </mesh>
      {/* Fresnel rim — the translucent membrane edge glow (outermost). */}
      <mesh scale={1.05} renderOrder={5}>
        <sphereGeometry args={[1, 48, 48]} />
        <primitive object={fresnel} attach="material" />
      </mesh>

      {/* Phospholipid heads (both leaflets). */}
      <instancedMesh
        ref={lipidRef}
        args={[undefined, undefined, LIPIDS * 2]}
        frustumCulled={false}
        {...lipidHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("lipid");
        }}
      >
        <sphereGeometry args={[1, 10, 10]} />
        <meshStandardMaterial color="#d8b4fe" emissive="#a855f7" emissiveIntensity={0.14} roughness={0.32} metalness={0.15} transparent opacity={0.9} />
      </instancedMesh>

      {/* Transport proteins. */}
      <instancedMesh
        ref={transRef}
        args={[undefined, undefined, TRANSPORTERS.length]}
        {...transportHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("transport");
        }}
      >
        <primitive object={proteinGeometry()} attach="geometry" />
        <meshStandardMaterial color="#22d3ee" emissive="#0891b2" emissiveIntensity={0.4} roughness={0.55} metalness={0.05} toneMapped={false} />
      </instancedMesh>

      {/* Channels (oligomeric pore barrel — subunits around a central lumen). */}
      <instancedMesh
        ref={chanRef}
        args={[undefined, undefined, CHANNELS.length]}
        {...channelHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("channel");
        }}
      >
        <primitive object={channelGeometry()} attach="geometry" />
        <meshStandardMaterial color="#60a5fa" emissive="#3b82f6" emissiveIntensity={0.3} roughness={0.6} metalness={0.04} toneMapped={false} />
      </instancedMesh>

      {/* Receptors (domed head on a stalk). */}
      <instancedMesh
        ref={recRef}
        args={[undefined, undefined, RECEPTORS.length]}
        {...receptorHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("receptor");
        }}
      >
        <primitive object={receptorGeometry()} attach="geometry" />
        <meshStandardMaterial color="#f9a8d4" emissive="#ec4899" emissiveIntensity={0.28} roughness={0.62} metalness={0.03} toneMapped={false} />
      </instancedMesh>

      {/* Damage patches. */}
      {DAMAGE_DIRS.slice(0, damageCount).map((d, i) => (
        <mesh key={i} position={[d.x, d.y, d.z]} scale={0.08}>
          <sphereGeometry args={[1, 8, 8]} />
          <meshStandardMaterial color="#fb7185" emissive="#7f1d1d" emissiveIntensity={0.5} />
        </mesh>
      ))}
    </group>
  );
}
