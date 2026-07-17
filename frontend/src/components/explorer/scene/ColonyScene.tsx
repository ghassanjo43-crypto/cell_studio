// The colony view: every living/dead cell in the population rendered as an instanced
// sphere, positioned in a deterministic phyllotaxis packing, sized by biomass and
// coloured by clone (lineage root). A translucent disc beneath the colony shows the
// remaining shared glucose (resource competition). Click a cell to inspect it.
//
// Everything is bound to the population summary in the current frame — the same
// scene renders in the browser and in VR.

import { ThreeEvent } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { cellRadius, colonyPosition, lineageColor } from "../colony";
import { useHover } from "../cell/interact";
import type { ObjectId } from "../inspect";

const MAX_CELLS = 300;

interface ColonySceneProps {
  frame: FrameData;
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
}

export function ColonyScene({ frame, selected, onSelect }: ColonySceneProps) {
  const pop = frame.population;
  const onHover = useHover();
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);

  const cells = pop?.cells ?? [];

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const n = Math.min(cells.length, MAX_CELLS);
    for (let i = 0; i < n; i++) {
      const c = cells[i];
      const [x, y] = colonyPosition(i);
      dummy.position.set(x, y, 0);
      dummy.scale.setScalar(cellRadius(c.mass) * (c.alive ? 1 : 0.7));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      color.set(lineageColor(c.root, c.alive));
      mesh.setColorAt(i, color);
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [cells, dummy, color]);

  // Selection ring around the inspected cell.
  const selectedIndex = useMemo(() => {
    if (!selected || !selected.startsWith("cell.")) return -1;
    const id = Number(selected.slice("cell.".length));
    return cells.findIndex((c) => c.id === id);
  }, [selected, cells]);

  // Medium disc radius/colour from remaining glucose.
  const discR = Math.max(1.5, Math.sqrt(cells.length) * 0.42 + 1);
  const medium = pop?.medium_glucose ?? 0;
  const mediumOpacity = 0.05 + 0.25 * (medium / (medium + 40));

  return (
    <group>
      {/* Shared medium (remaining glucose) beneath the colony. */}
      <mesh position={[0, 0, -0.4]}>
        <circleGeometry args={[discR, 48]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={mediumOpacity} side={THREE.DoubleSide} />
      </mesh>

      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, MAX_CELLS]}
        frustumCulled={false}
        onPointerMove={(e) => {
          e.stopPropagation();
          if (e.instanceId != null && e.instanceId < cells.length) {
            onHover(`cell.${cells[e.instanceId].id}`, e.nativeEvent.clientX, e.nativeEvent.clientY);
          }
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHover(null);
        }}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          if (e.instanceId != null && e.instanceId < cells.length) {
            onSelect(`cell.${cells[e.instanceId].id}`);
          }
        }}
      >
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial roughness={0.5} metalness={0.05} />
      </instancedMesh>

      {selectedIndex >= 0 && (
        <mesh
          position={[colonyPosition(selectedIndex)[0], colonyPosition(selectedIndex)[1], 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <torusGeometry args={[cellRadius(cells[selectedIndex].mass) * 1.6, 0.03, 10, 32]} />
          <meshStandardMaterial color="#e0f2fe" emissive="#60a5fa" emissiveIntensity={1.2} toneMapped={false} />
        </mesh>
      )}
    </group>
  );
}
