// The shared 3D scene: the cell membrane, internal compartments, the extracellular
// nutrient gradient, and floating info panels. Rendered identically in the normal
// browser viewer and inside an immersive VR session.

import { useFrame, useThree } from "@react-three/fiber";
import { useXR } from "@react-three/xr";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { FrameData } from "../../api/types";
import { statusColor } from "../theme";
import { buildPanels } from "./labels";
import { LabelPanel } from "./LabelPanel";

function radiusForMass(mass: number): number {
  return 0.6 + Math.cbrt(Math.max(mass, 0)) * 0.7;
}

/** Mouse orbit/zoom in the browser; disabled in VR (the headset drives the camera). */
function OrbitController() {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const inXR = useXR((s) => !!s.session);
  const ref = useRef<OrbitControls | null>(null);

  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = true;
    controls.minDistance = 2;
    controls.maxDistance = 20;
    ref.current = controls;
    return () => controls.dispose();
  }, [camera, gl]);

  useFrame(() => {
    if (ref.current) {
      ref.current.enabled = !inXR;
      ref.current.update();
    }
  });
  return null;
}

function Membrane({ frame }: { frame: FrameData | null }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial>(null);
  const pulseRef = useRef(0);
  const prevDivisions = useRef(frame?.divisions ?? 0);

  const mass = frame?.mass ?? 0.001;
  const status = frame?.status ?? null;
  const integrity = frame?.membrane_integrity ?? 1;
  const divisions = frame?.divisions ?? 0;

  useEffect(() => {
    if (divisions > prevDivisions.current) pulseRef.current = 1;
    prevDivisions.current = divisions;
  }, [divisions]);

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    const material = materialRef.current;
    if (!mesh || !material) return;
    mesh.rotation.y += delta * 0.25;
    pulseRef.current = Math.max(0, pulseRef.current - delta * 1.6);
    const target = radiusForMass(mass) * (1 + pulseRef.current * 0.35);
    const s = mesh.scale.x + (target - mesh.scale.x) * Math.min(1, delta * 6);
    mesh.scale.setScalar(s);
    material.color.lerp(new THREE.Color(statusColor(status)), Math.min(1, delta * 4));
    material.emissive.setRGB(pulseRef.current * 0.3, pulseRef.current * 0.3, pulseRef.current * 0.3);
    material.opacity = 0.32 + 0.55 * Math.max(0.12, integrity);
  });

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1, 48, 48]} />
      <meshStandardMaterial
        ref={materialRef}
        transparent
        roughness={0.35}
        metalness={0.1}
        color={statusColor(status)}
      />
    </mesh>
  );
}

const COMPARTMENT_OFFSET: Record<string, [number, number, number]> = {
  nucleoid: [0.0, 0.0, 0.0],
  membrane_zone: [0.35, 0.25, 0.1],
  cytosol: [-0.3, -0.2, -0.1],
};

function Compartments({ frame }: { frame: FrameData | null }) {
  if (!frame?.compartments) return null;
  const cellR = radiusForMass(frame.mass);
  return (
    <group>
      {Object.entries(frame.compartments).map(([name, v]) => {
        const off = COMPARTMENT_OFFSET[name] ?? [0, 0, 0];
        const energyColor = new THREE.Color().setHSL(0.58, 0.7, Math.min(0.7, 0.25 + v.energy / 60));
        const color = v.stressed ? "#fb7185" : `#${energyColor.getHexString()}`;
        const r = name === "cytosol" ? 0.28 : 0.2;
        return (
          <mesh key={name} position={[off[0] * cellR, off[1] * cellR, off[2] * cellR]}>
            <sphereGeometry args={[r * cellR, 24, 24]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={v.stressed ? 0.6 : 0.25}
              transparent
              opacity={0.85}
            />
          </mesh>
        );
      })}
    </group>
  );
}

function NutrientGradient({ frame }: { frame: FrameData | null }) {
  if (!frame?.field_glc || frame.field_glc.length === 0) return null;
  const cellR = radiusForMass(frame.mass);
  const maxC = Math.max(...frame.field_glc, 1e-6);
  const step = 0.45;
  return (
    <group>
      {frame.field_glc.map((c, i) => (
        <mesh key={i}>
          <sphereGeometry args={[cellR + 0.3 + i * step, 20, 20]} />
          <meshBasicMaterial
            color="#fbbf24"
            wireframe
            transparent
            opacity={0.04 + 0.22 * (c / maxC)}
          />
        </mesh>
      ))}
    </group>
  );
}

export function CellScene({ frame }: { frame: FrameData | null }) {
  const panels = useMemo(() => buildPanels(frame), [frame]);
  // Lay the panels out around the cell.
  const positions: [number, number, number][] = [
    [2.2, 0.9, 0],
    [-2.2, 0.9, 0],
    [2.2, -0.9, 0],
    [-2.2, -0.9, 0],
  ];

  return (
    <group>
      <ambientLight intensity={0.6} />
      <pointLight position={[5, 5, 5]} intensity={40} />
      <pointLight position={[-5, -3, 2]} intensity={12} color="#88aaff" />

      <Membrane frame={frame} />
      <Compartments frame={frame} />
      <NutrientGradient frame={frame} />

      {panels.map((panel, i) => (
        <LabelPanel key={panel.title} panel={panel} position={positions[i % positions.length]} />
      ))}

      <OrbitController />
    </group>
  );
}
