// Assembles the immersive Cell Explorer scene. The single cell is rendered by the
// Scientific Cell renderer (biologically-inspired, fully data-driven); colonies and
// the Petri dish have their own scenes. Rendered identically in browser and VR.
//
// Memoised so hover-only state in the parent doesn't re-render the 3D scene.

import { useFrame, useThree } from "@react-three/fiber";
import { useXR } from "@react-three/xr";
import { memo, useEffect, useMemo } from "react";
import * as THREE from "three";
import type { FrameData, HeatmapMetric } from "../../api/types";
import { HoverProvider, type HoverFn } from "./cell/interact";
import { ScientificCell } from "./cell/ScientificCell";
import type { ObjectId } from "./inspect";
import { ColonyScene } from "./scene/ColonyScene";
import { Controls, type FocusRequest } from "./scene/Controls";
import { InspectPanelVR } from "./scene/InspectPanelVR";
import { PetriScene } from "./scene/PetriScene";

// Atmospheric depth — distance-adaptive exponential fog. Far away (the establishing
// shot) the interior stays crisp; as the camera moves inside, the haze thickens so the
// crowded cytoplasm dissolves with depth and you cannot see clear across the cell. This
// is a depth cue (like DoF), not biology — it never alters any measured value.
function AtmosphereController({
  enabled, cinematic, color,
}: {
  enabled: boolean;
  cinematic: boolean;
  color: string;
}) {
  const scene = useThree((s) => s.scene);
  const inXR = useXR((s) => !!s.session);
  const fog = useMemo(() => new THREE.FogExp2(color, 0.03), [color]);
  useEffect(() => {
    if (enabled) scene.fog = fog;
    return () => {
      if (scene.fog === fog) scene.fog = null;
    };
  }, [scene, enabled, fog]);
  useFrame(({ camera }) => {
    if (!enabled) return;
    const d = camera.position.length();
    // Ramp the haze up sooner and much denser as the camera closes in, so the far side
    // of the cell dissolves entirely — you get strong atmospheric perspective (near
    // crisp, far gone) and can never see the whole enclosure at once. Softened in VR,
    // where dense fog is uncomfortable and the headset already conveys depth.
    const inside = THREE.MathUtils.clamp(1 - (d - 1.2) / 4.5, 0, 1);
    const peak = inXR ? (cinematic ? 0.22 : 0.14) : cinematic ? 0.62 : 0.42;
    const target = 0.03 + inside * peak;
    fog.density += (target - fog.density) * 0.08; // eased so haze never pops
  });
  return null;
}

// Dynamic field of view — widens as the camera moves inside the cell so the interior
// curves away like an architectural space (immersive wide-angle) instead of reading as
// a small ball at a fixed narrow FOV. VR-safe: the headset owns its own projection, so
// this never touches the camera in an XR session.
function FovController({ enabled }: { enabled: boolean }) {
  const camera = useThree((s) => s.camera);
  const inXR = useXR((s) => !!s.session);
  useFrame((_, delta) => {
    const cam = camera as THREE.PerspectiveCamera;
    if (inXR || !cam.isPerspectiveCamera) return;
    const d = cam.position.length();
    const inside = THREE.MathUtils.clamp(1 - (d - 1.2) / 4, 0, 1);
    // Single cell: 52° establishing → ~68° deep inside (immersive wide-angle). Other
    // scenes (petri / colony) keep the original 45°.
    const target = enabled ? 52 + inside * 16 : 45;
    if (Math.abs(cam.fov - target) > 0.02) {
      cam.fov += (target - cam.fov) * Math.min(1, delta * 2.2);
      cam.updateProjectionMatrix();
    }
  });
  return null;
}

// Dynamic exposure — gently brightens the scene as metabolism rises, so an active,
// energetic cell reads brighter than a dormant one. Driven by a real variable
// (metabolicActivity); eased so it never flickers. VR-safe (a renderer setting).
function ExposureController({ activity, enabled }: { activity: number; enabled: boolean }) {
  const gl = useThree((s) => s.gl);
  useFrame((_, delta) => {
    const target = enabled ? 0.95 + activity * 0.22 : 1.05;
    gl.toneMappingExposure += (target - gl.toneMappingExposure) * Math.min(1, delta * 2);
  });
  return null;
}

interface CellExplorerSceneProps {
  frame: FrameData | null;
  activeTypes: Set<string>;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
  onHover: HoverFn;
  explore: boolean;
  heatmapMetric: HeatmapMetric;
  metabolicActivity: number;
  densityScale: number;
  focus: FocusRequest | null;
  cinematic: boolean;
}

export const CellExplorerScene = memo(function CellExplorerScene({
  frame, activeTypes, selected, onSelect, onHover, explore, heatmapMetric, metabolicActivity, densityScale, focus, cinematic,
}: CellExplorerSceneProps) {
  const isSingleCell = !!frame && !frame.population && !frame.petri;
  return (
    <HoverProvider value={onHover}>
      <group>
        {/* Soft, even scientific lighting in the manner of a Nature/Cell illustration:
            a hemisphere sky/ground bounce (indirect multi-bounce approximation) + a warm
            key and a cool fill (warm/cool separation for form) at gentle intensities. The
            old saturated high-intensity blue/purple point lights are replaced so the matte,
            scene-lit molecules read as hydrated protein under studio light — not neon under
            a rave rig. */}
        {/* Moody, cinematic illustration lighting: a dark indigo base so the emissive
            heroes (cyan DNA, magenta membrane, the warm high-energy compartment) glow out
            of the gloom and bloom catches them, rather than a flat studio wash. Cool key +
            cool rim carve form in blue; the sole warmth is the metabolic core / compartment. */}
        <ambientLight intensity={cinematic ? 0.26 : 0.34} />
        <hemisphereLight args={["#c7d2fe", "#05060f", 0.55]} />
        {/* Cool key from upper right. */}
        <directionalLight position={[6, 7, 5]} intensity={1.7} color="#e0e7ff" />
        {/* Cool fill from the lower left — shapes the shadow side in blue. */}
        <pointLight position={[-6, -4, 2]} intensity={6} color="#93b4f0" />
        {/* Cool back-rim to separate the cell from the dark indigo field. */}
        <pointLight position={[0, 0, -8]} intensity={5} color="#7aa2e8" />
        {/* Faint warm underlight — a hint of cytoplasmic bounce (the main warmth comes
            from the high-energy compartment accent). */}
        <pointLight position={[3, -6, 3]} intensity={2.2} color="#ffbf8f" />
        {/* Warm metabolic core light (intensity ∝ metabolic activity) + cool back-rim.
            The core always glows a little so the cell reads as energetic; it flares as
            metabolism rises. */}
        {isSingleCell ? (
          <pointLight position={[0, 0, 0]} intensity={2 + metabolicActivity * 7} distance={6} color="#67e8f9" />
        ) : null}
        {cinematic && isSingleCell ? (
          <pointLight position={[-3, 4, -4]} intensity={10} distance={14} color="#bfe3ff" />
        ) : null}

        <AtmosphereController enabled={isSingleCell} cinematic={cinematic} color="#0b0a2a" />
        <ExposureController activity={metabolicActivity} enabled={isSingleCell} />
        <FovController enabled={isSingleCell} />

        {frame && frame.petri && (
          <PetriScene frame={frame} metric={heatmapMetric} selected={selected} onSelect={onSelect} densityScale={densityScale} />
        )}

        {frame && frame.population && <ColonyScene frame={frame} selected={selected} onSelect={onSelect} />}

        {isSingleCell && frame && (
          <ScientificCell
            frame={frame}
            metabolicActivity={metabolicActivity}
            activeTypes={activeTypes}
            selected={selected}
            onSelect={onSelect}
            densityScale={densityScale}
            cinematic={cinematic}
          />
        )}

        {frame && <InspectPanelVR frame={frame} selected={selected} />}

        <Controls explore={explore} focus={focus} cinematic={cinematic && isSingleCell} />
      </group>
    </HoverProvider>
  );
});
