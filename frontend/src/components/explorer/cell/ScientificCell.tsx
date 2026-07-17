// The Scientific Cell renderer: composes the biologically-inspired systems (bilayer
// membrane + proteins, coiled genome with replication/transcription, molecular
// traffic, signalling propagation, compartment organelles, division) into one scene.
// Everything is driven by `buildCellVisual(frame)` — the biology→graphics mapping.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import type { ObjectId } from "../inspect";
import { COMPARTMENT_OFFSET, spherePoints } from "../scene/geometry";
import { NutrientField } from "../scene/Nutrients";
import { buildCellVisual } from "./biomap";
import { Callouts } from "./CalloutLabels";
import { makeCytoplasmMaterial } from "./cytoplasmMaterial";
import { DivisionAnim } from "./DivisionAnim";
import { DrugMolecules } from "./DrugMolecules";
import { DrugResponse } from "./DrugResponse";
import { buildDrugVisual, DrugFxProvider } from "./drugVisual";
import { Genome } from "./Genome";
import { radialGlowTexture } from "./glow";
import { InstancedField } from "./InstancedField";
import { useHover, useHoverHandlers } from "./interact";
import { LodProvider } from "./lod";
import { MembraneBilayer } from "./MembraneBilayer";
import { Molecules } from "./Molecules";
import { SignallingSystem } from "./SignallingSystem";

interface Props {
  frame: FrameData;
  metabolicActivity: number;
  activeTypes: Set<string>;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
  densityScale?: number;
  cinematic?: boolean;
}

function CompartmentOrganelles({
  frame, radius, selected, onSelect,
}: {
  frame: FrameData;
  radius: number;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}) {
  const onHover = useHover();
  const entries = Object.entries(frame.compartments ?? {});
  // The single highest-energy compartment is rendered as a warm, glowing "power plant"
  // — the sole warm counterpoint to the cool interior. This is driven entirely by the
  // measured compartment.energy (no invented organelle): the hottest ATP pool glows
  // orange with rising embers and casts a warm light; the rest stay cool blue.
  const hottest = entries.reduce<string | null>(
    (best, [name, v]) => (best === null || v.energy > (frame.compartments![best]?.energy ?? -Infinity) ? name : best),
    null,
  );
  if (entries.length === 0) return null;
  return (
    <group>
      {entries.map(([name, v]) => {
        const off = COMPARTMENT_OFFSET[name] ?? [0, 0, 0];
        const isHot = name === hottest && v.energy > 0 && !v.stressed;
        const hue = Math.min(0.7, 0.25 + v.energy / 60);
        const color = v.stressed ? "#fb7185" : isHot ? "#fb923c" : `hsl(210, 70%, ${Math.round(hue * 100)}%)`;
        const emissive = v.stressed ? "#fb7185" : isHot ? "#f97316" : color;
        const r = ((name === "cytosol" ? 0.3 : 0.2) * (isHot ? 1.25 : 1)) * radius;
        const sel = selected === `energy.${name}`;
        const id: ObjectId = `energy.${name}`;
        const pos: [number, number, number] = [off[0] * radius, off[1] * radius, off[2] * radius];
        return (
          <group key={name} position={pos}>
            <mesh
              onPointerOver={(e) => {
                e.stopPropagation();
                onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY);
              }}
              onPointerMove={(e) => {
                e.stopPropagation();
                onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY);
              }}
              onPointerOut={(e) => {
                e.stopPropagation();
                onHover(null);
              }}
              onClick={(e: ThreeEvent<MouseEvent>) => {
                e.stopPropagation();
                onSelect(id);
              }}
            >
              <sphereGeometry args={[r, 24, 24]} />
              <meshStandardMaterial
                color={color}
                emissive={emissive}
                emissiveIntensity={(v.stressed ? 0.7 : isHot ? 0.9 : 0.3) + (sel ? 0.5 : 0)}
                roughness={0.5}
                transparent
                opacity={isHot ? 0.9 : 0.8}
                toneMapped={!isHot}
              />
            </mesh>
            {isHot ? (
              <>
                {/* Warm rim light emanating from the energetic compartment. */}
                <pointLight intensity={4 + v.energy * 0.25} distance={radius * 3.2} color="#ffb066" />
                {/* Rising embers — energy sparks off the hot ATP pool (∝ energy). */}
                <InstancedField
                  max={40}
                  count={Math.round(Math.min(34, 8 + v.energy))}
                  color="#ffb066"
                  size={0.028}
                  speed={0.5}
                  diffusion={0.03}
                  glow
                  fade
                  place={(dir, phase, _i, out) => {
                    out.copy(dir).multiplyScalar(r * (0.7 + 0.9 * phase));
                    out.y += phase * r * 1.6; // embers drift upward
                  }}
                />
              </>
            ) : null}
          </group>
        );
      })}
    </group>
  );
}

// Cytoplasm as a translucent, depth-graded volume (shader) plus an invisible picker
// sphere so it stays clickable/hoverable as "cytosol".
function Cytoplasm({
  radius, activity, hover, onClick,
}: {
  radius: number;
  activity: number;
  hover: ReturnType<typeof useHoverHandlers>;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}) {
  // Multiple nested density layers (coarse outer → finer inner + a dense core) → the
  // cytoplasm reads as a thick, layered, light-scattering hydrogel rather than one thin
  // tinted shell. Opacities are raised so the interior is opaque enough that you never
  // look through a clear window of empty air.
  const layers = useMemo(
    () => [
      makeCytoplasmMaterial({ scale: 2.6, seed: 0, opacity: 0.3 }),
      makeCytoplasmMaterial({ scale: 4.4, seed: 13.7, opacity: 0.24 }),
      makeCytoplasmMaterial({ scale: 7.0, seed: 41.2, opacity: 0.19 }),
      makeCytoplasmMaterial({ scale: 10.5, seed: 71.9, opacity: 0.15 }),
    ],
    [],
  );
  useEffect(() => () => layers.forEach((m) => m.dispose()), [layers]);
  useFrame((state) => {
    for (const m of layers) {
      m.uniforms.uTime.value = state.clock.elapsedTime;
      m.uniforms.uActivity.value = activity;
    }
  });
  const scales = [0.94, 0.78, 0.62, 0.44];
  return (
    <>
      {layers.map((m, i) => (
        <mesh key={i} scale={radius * scales[i]} renderOrder={i}>
          <sphereGeometry args={[1, 48, 48]} />
          <primitive object={m} attach="material" />
        </mesh>
      ))}
      {/* Invisible front-face picker (BackSide volume above isn't reliable to click). */}
      <mesh scale={radius * 0.9} {...hover} onClick={onClick}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial visible={false} />
      </mesh>
    </>
  );
}

// Cinematic light haze / soft god-ray glow — a billboarded additive sprite that reads
// as a volumetric light source behind the cell. Cinematic-only; combines with bloom.
function LightHaze({ radius }: { radius: number }) {
  const tex = useMemo(() => radialGlowTexture(), []);
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ camera }) => {
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });
  return (
    <mesh ref={ref} position={[-radius * 1.1, radius * 1.3, -radius * 1.4]} renderOrder={-1}>
      <planeGeometry args={[radius * 5, radius * 5]} />
      <meshBasicMaterial
        map={tex}
        color="#bfe3ff"
        transparent
        opacity={0.32}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
  );
}

// Exterior context: faint, out-of-focus neighbouring cells + extracellular matrix in
// the distance. Revealed only when the camera is *inside* looking out through the
// membrane (so the establishing shot stays clean), and swallowed by the atmospheric
// fog — a subtle, scientifically-plausible environment hint, never a data claim.
function Exterior({ radius }: { radius: number }) {
  const dirs = useMemo(() => spherePoints(7), []);
  const mat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#16283f", emissive: "#1e3a5f", emissiveIntensity: 0.18,
        roughness: 0.95, transparent: true, opacity: 0, depthWrite: false,
      }),
    [],
  );
  useEffect(() => () => mat.dispose(), [mat]);
  useFrame(({ camera }) => {
    // Only visible when the camera is inside the cell looking out (else it would
    // clutter the establishing shot). Fog then dissolves it into the distance.
    const inside = THREE.MathUtils.clamp(1 - (camera.position.length() - radius) / (radius * 1.6), 0, 1);
    mat.opacity = 0.26 * inside;
  });
  return (
    <group>
      {dirs.map((d, i) => {
        const dist = radius * (4.5 + (i % 3) * 1.6);
        const s = radius * (2.4 + ((i * 0.618) % 1) * 2.2);
        return (
          <mesh key={i} position={[d.x * dist, d.y * dist * 0.7, d.z * dist]} scale={s} renderOrder={-5}>
            <icosahedronGeometry args={[1, 2]} />
            <primitive object={mat} attach="material" />
          </mesh>
        );
      })}
    </group>
  );
}

export function ScientificCell({
  frame, metabolicActivity, activeTypes, selected, onSelect, densityScale = 1, cinematic = false,
}: Props) {
  const visual = useMemo(() => buildCellVisual(frame, metabolicActivity), [frame, metabolicActivity]);
  const cytosolHover = useHoverHandlers("cytosol");
  // Drug visual-response state — maps active-drug channels + affected biology into the
  // renderer's response (leakage, ATP dimming, fork freeze, ROS, …). Broadcast via context.
  const drugFx = useMemo(() => buildDrugVisual(frame), [frame]);

  return (
    <DrugFxProvider value={drugFx}>
    <LodProvider densityScale={densityScale}>
      {/* Extracellular nutrient gradient (spatial scenario). */}
      <NutrientField frame={frame} onSelect={onSelect} />

      {/* Cinematic light haze behind the cell (soft god-ray glow). */}
      {cinematic ? <LightHaze radius={visual.radius} /> : null}
      {/* Faint exterior context (neighbour cells / matrix) seen through the membrane. */}
      {cinematic ? <Exterior radius={visual.radius} /> : null}

      {/* Cytoplasm — translucent, depth-graded volume (clickable). */}
      <Cytoplasm
        radius={visual.radius}
        activity={metabolicActivity}
        hover={cytosolHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("cytosol");
        }}
      />

      <MembraneBilayer visual={visual} selected={selected} onSelect={onSelect} />
      <Molecules visual={visual} cinematic={cinematic} onSelect={onSelect} />
      {/* Drug molecules (Drug Interaction Studio) — only when the frame reports drugs. */}
      <DrugMolecules frame={frame} radius={visual.radius} />
      {/* Drug response — additive effects (leakage, flashes, ROS, glucose build-up, sparks). */}
      <DrugResponse fx={drugFx} radius={visual.radius} />
      <CompartmentOrganelles frame={frame} radius={visual.radius} selected={selected} onSelect={onSelect} />
      <Genome visual={visual} mutating={activeTypes.has("mutation")} selected={selected} onSelect={onSelect} />
      <SignallingSystem visual={visual} selected={selected} onSelect={onSelect} />
      <DivisionAnim visual={visual} dividing={activeTypes.has("division")} onSelect={onSelect} />
      {cinematic ? <Callouts frame={frame} /> : null}
    </LodProvider>
    </DrugFxProvider>
  );
}
