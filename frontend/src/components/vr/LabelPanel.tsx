// A floating text panel rendered as a canvas texture on a billboarded plane.
// Works in the normal 3D viewer and in immersive VR (no HTML overlay, no drei).

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Panel } from "./labels";

function makeTexture(panel: Panel): { texture: THREE.CanvasTexture; aspect: number } {
  const W = 512;
  const pad = 26;
  const lineH = 40;
  const H = pad * 2 + 44 + panel.lines.length * lineH;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "rgba(14, 22, 40, 0.88)";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(96, 165, 250, 0.6)";
  ctx.lineWidth = 3;
  ctx.strokeRect(2, 2, W - 4, H - 4);

  ctx.fillStyle = "#c4b5fd";
  ctx.font = "bold 30px system-ui, sans-serif";
  ctx.fillText(panel.title, pad, pad + 30);

  ctx.fillStyle = "#e6edf7";
  ctx.font = "26px system-ui, sans-serif";
  panel.lines.forEach((line, i) => {
    ctx.fillText(line, pad, pad + 44 + (i + 1) * lineH - 8);
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return { texture, aspect: W / H };
}

interface LabelPanelProps {
  panel: Panel;
  position: [number, number, number];
  width?: number;
}

export function LabelPanel({ panel, position, width = 1.1 }: LabelPanelProps) {
  const ref = useRef<THREE.Group>(null);
  const { texture, aspect } = useMemo(
    () => makeTexture(panel),
    // rebuild when the visible text changes
    [panel.title, panel.lines.join("\n")],
  );
  // Billboard: always face the active camera (works for the VR headset too).
  useFrame(({ camera }) => {
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  const h = width / aspect;
  return (
    <group ref={ref} position={position}>
      <mesh>
        <planeGeometry args={[width, h]} />
        <meshBasicMaterial map={texture} transparent toneMapped={false} />
      </mesh>
    </group>
  );
}
