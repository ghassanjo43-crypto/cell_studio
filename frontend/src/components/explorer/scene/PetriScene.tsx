// The Digital Petri Dish, rendered in 3D. The floor is a smooth nutrient/metric
// surface (a subdivided plane displaced by the selected field), and the cells are
// instanced on top with a biofilm height that grows with local density — so colony
// mounds, nutrient-limited valleys, and advancing fronts all read as relief. Cells
// are coloured by clone (lineage) with brightness = ATP energy, so active fronts glow
// and starved cores go dim. LOD + the quality density factor keep thousands of cells
// smooth; the same scene renders in the browser and in VR.

import { ThreeEvent, useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData, HeatmapMetric } from "../../../api/types";
import { cloneColorRGB, DISH_WORLD, gridToWorld, heatmapTexture } from "../petri";
import { useHover, useHoverHandlers } from "../cell/interact";
import type { ObjectId } from "../inspect";

const MAX_CELLS = 4000;
const FLOOR_HEIGHT = 0.9; // world units of relief for the metric surface
const BIOFILM = 0.35; // extra height cells stack above the floor with density
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

interface PetriSceneProps {
  frame: FrameData;
  metric: HeatmapMetric;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
  densityScale?: number;
}

export function PetriScene({ frame, metric, selected, onSelect, densityScale = 1 }: PetriSceneProps) {
  const petri = frame.petri!;
  const [rows, cols] = petri.hm_size;
  const [gridH, gridW] = petri.grid;
  const cells = petri.cells;

  const meshRef = useRef<THREE.InstancedMesh>(null);
  const floorRef = useRef<THREE.Mesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);
  const floorHover = useHoverHandlers("petri");
  const onHover = useHover();

  // Which field drives the floor height (clone mode → show density topography).
  const heightField = metric === "clone" ? petri.heatmaps.population : petri.heatmaps[metric];
  const density = petri.heatmaps.population;
  const maxHeight = Math.max(1e-6, ...heightField);
  const maxDensity = Math.max(1e-6, ...density);
  const maxEnergy = Math.max(1e-6, ...cells.energy);

  const heightAt = (x: number, y: number, field: number[], max: number) => {
    const c = clamp(Math.floor((x / gridW) * cols), 0, cols - 1);
    const r = clamp(Math.floor((y / gridH) * rows), 0, rows - 1);
    return field[r * cols + c] / max;
  };

  // Floor: subdivided plane coloured by the metric, displaced by the height field.
  const floorGeo = useMemo(() => new THREE.PlaneGeometry(DISH_WORLD, DISH_WORLD, cols - 1, rows - 1), [cols, rows]);
  const texture = useMemo(() => {
    const { data } = heatmapTexture(petri, metric);
    const tex = new THREE.DataTexture(new Uint8Array(data), cols, rows, THREE.RGBAFormat);
    tex.flipY = true;
    const filter = metric === "clone" ? THREE.NearestFilter : THREE.LinearFilter;
    tex.magFilter = filter;
    tex.minFilter = filter;
    tex.needsUpdate = true;
    return tex;
  }, [petri, metric, cols, rows]);
  useLayoutEffect(() => () => texture.dispose(), [texture]);

  useLayoutEffect(() => {
    const pos = floorGeo.attributes.position;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const idx = j * cols + i;
        pos.setZ(idx, (heightField[idx] / maxHeight) * FLOOR_HEIGHT);
      }
    }
    pos.needsUpdate = true;
    floorGeo.computeVertexNormals();
  }, [floorGeo, heightField, maxHeight, rows, cols]);

  // Cells: position (with biofilm height) + colour (clone × energy brightness).
  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const cellR = (DISH_WORLD / Math.max(gridW, gridH)) * 0.7;
    const n = Math.min(cells.count, MAX_CELLS);
    for (let i = 0; i < n; i++) {
      const [wx, wy] = gridToWorld(cells.x[i], cells.y[i], gridW, gridH);
      const floorZ = heightAt(cells.x[i], cells.y[i], heightField, maxHeight) * FLOOR_HEIGHT;
      const biofilm = heightAt(cells.x[i], cells.y[i], density, maxDensity) * BIOFILM;
      const jitter = ((i * 2654435761) % 1000) / 1000 * 0.05;
      dummy.position.set(wx, wy, floorZ + biofilm + jitter + cellR);
      dummy.scale.setScalar(cellR);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      const [r, g, b] = cloneColorRGB(cells.clone[i]);
      const bright = 0.35 + 0.65 * (cells.energy[i] / maxEnergy); // fronts glow, cores dim
      color.setRGB((r / 255) * bright * 1.3, (g / 255) * bright * 1.3, (b / 255) * bright * 1.3);
      mesh.setColorAt(i, color);
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [cells, gridW, gridH, heightField, density, maxHeight, maxDensity, maxEnergy, dummy, color]);

  // LOD: thin the visible cells with camera distance × the quality density factor.
  useFrame(({ camera }) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const d = camera.position.length();
    const lod = clamp((16 - d) / 11, 0.18, 1);
    mesh.count = Math.min(cells.count, MAX_CELLS, Math.max(0, Math.round(cells.count * lod * densityScale)));
  });

  const selectedIndex = useMemo(() => {
    if (!selected || !selected.startsWith("petricell.")) return -1;
    const id = Number(selected.slice("petricell.".length));
    return id >= 0 && id < cells.count ? id : -1;
  }, [selected, cells.count]);

  return (
    <group>
      {/* Nutrient / metric surface (the dish floor). */}
      <mesh
        ref={floorRef}
        geometry={floorGeo}
        {...floorHover}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect("petri");
        }}
      >
        <meshStandardMaterial map={texture} roughness={0.85} metalness={0.05} side={THREE.DoubleSide} />
      </mesh>

      {/* Cells. */}
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, MAX_CELLS]}
        frustumCulled={false}
        onPointerMove={(e) => {
          e.stopPropagation();
          if (e.instanceId != null && e.instanceId < cells.count) {
            onHover(`petricell.${e.instanceId}`, e.nativeEvent.clientX, e.nativeEvent.clientY);
          }
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHover(null);
        }}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          if (e.instanceId != null && e.instanceId < cells.count) {
            onSelect(`petricell.${e.instanceId}`);
          }
        }}
      >
        <sphereGeometry args={[1, 12, 12]} />
        <meshStandardMaterial roughness={0.5} metalness={0.05} toneMapped={false} />
      </instancedMesh>

      {selectedIndex >= 0 && (
        <mesh
          position={[
            gridToWorld(cells.x[selectedIndex], cells.y[selectedIndex], gridW, gridH)[0],
            gridToWorld(cells.x[selectedIndex], cells.y[selectedIndex], gridW, gridH)[1],
            heightAt(cells.x[selectedIndex], cells.y[selectedIndex], heightField, maxHeight) * FLOOR_HEIGHT + 0.3,
          ]}
        >
          <ringGeometry args={[0.12, 0.2, 20]} />
          <meshBasicMaterial color="#e0f2fe" transparent toneMapped={false} />
        </mesh>
      )}
    </group>
  );
}
