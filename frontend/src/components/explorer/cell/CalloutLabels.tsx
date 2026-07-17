// Reference-style callout labels: a billboarded name card with a thin leader line to
// the structure it points at. Only shown in Cinematic Mode. Data-driven — the set of
// labels comes from calloutTargets(frame), so absent structures get no label.

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { FrameData } from "../../../api/types";
import { calloutTargets } from "./callouts";

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// Category accent colour, derived from the callout id (no change to the pure targets).
function accentFor(id: string): string {
  if (id.includes("membrane")) return "#7dd3fc";
  if (id.includes("transport")) return "#22d3ee";
  if (id.includes("channel")) return "#60a5fa";
  if (id.includes("ribosome")) return "#e2e8f0";
  if (id.includes("nucleoid") || id.includes("genome")) return "#f472b6";
  if (id.includes("atp")) return "#67e8f9";
  if (id.includes("signal")) return "#a78bfa";
  if (id.includes("nutrient")) return "#fbbf24";
  return "#94a3b8"; // cytoplasm / default
}

function labelTexture(text: string, accent: string): { tex: THREE.CanvasTexture; aspect: number } {
  const S = 2; // supersample for crisp text
  const fs = 34 * S;
  const pad = 16 * S;
  const bar = 6 * S; // accent bar width
  const measure = document.createElement("canvas").getContext("2d")!;
  measure.font = `600 ${fs}px system-ui, sans-serif`;
  const w = Math.ceil(measure.measureText(text).width) + pad * 2 + bar;
  const h = fs + pad * 2;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  g.font = `600 ${fs}px system-ui, sans-serif`;
  // Card.
  g.fillStyle = "rgba(8,13,26,0.88)";
  roundRect(g, S, S, w - 2 * S, h - 2 * S, 10 * S);
  g.fill();
  g.strokeStyle = accent;
  g.globalAlpha = 0.7;
  g.lineWidth = 2 * S;
  roundRect(g, S, S, w - 2 * S, h - 2 * S, 10 * S);
  g.stroke();
  g.globalAlpha = 1;
  // Accent bar on the left.
  g.fillStyle = accent;
  roundRect(g, S * 3, S * 5, bar, h - S * 10, bar / 2);
  g.fill();
  // Text with a soft shadow for contrast against bright molecules.
  g.textBaseline = "middle";
  g.shadowColor = "rgba(0,0,0,0.9)";
  g.shadowBlur = 4 * S;
  g.fillStyle = "#f1f5fb";
  g.fillText(text, pad + bar, h / 2 + S);
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return { tex, aspect: w / h };
}

function CalloutItem({ id, label, anchor }: { id: string; label: string; anchor: [number, number, number] }) {
  const billboard = useRef<THREE.Group>(null);
  const accent = useMemo(() => accentFor(id), [id]);
  const { tex, aspect } = useMemo(() => labelTexture(label, accent), [label, accent]);
  const a = useMemo(() => new THREE.Vector3(...anchor), [anchor]);
  const labelPos = useMemo(() => {
    const dir = a.lengthSq() > 1e-4 ? a.clone().normalize() : new THREE.Vector3(0.5, 0.8, 0).normalize();
    return a.clone().add(dir.multiplyScalar(0.9)).add(new THREE.Vector3(0, 0.18, 0));
  }, [a]);
  const line = useMemo(() => {
    const d = a.clone().sub(labelPos);
    const len = Math.max(0.001, d.length());
    return {
      mid: labelPos.clone().add(d.clone().multiplyScalar(0.5)),
      quat: new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().normalize()),
      len,
    };
  }, [a, labelPos]);

  useFrame(({ camera }) => {
    const b = billboard.current;
    if (!b) return;
    b.quaternion.copy(camera.quaternion);
    // Keep labels at roughly constant on-screen size (readable when inside or zoomed out).
    const dist = camera.position.distanceTo(labelPos);
    b.scale.setScalar(THREE.MathUtils.clamp(dist * 0.14, 0.5, 3.2));
  });

  const w = 0.9;
  const h = w / aspect;
  return (
    <group>
      <mesh position={line.mid} quaternion={line.quat}>
        <cylinderGeometry args={[0.006, 0.006, line.len, 6]} />
        <meshBasicMaterial color={accent} transparent opacity={0.55} toneMapped={false} depthTest={false} />
      </mesh>
      <mesh position={a}>
        <sphereGeometry args={[0.03, 8, 8]} />
        <meshBasicMaterial color={accent} toneMapped={false} depthTest={false} />
      </mesh>
      <group ref={billboard} position={labelPos}>
        <mesh>
          <planeGeometry args={[w, h]} />
          <meshBasicMaterial map={tex} transparent toneMapped={false} depthWrite={false} depthTest={false} />
        </mesh>
      </group>
    </group>
  );
}

export function Callouts({ frame }: { frame: FrameData }) {
  const items = useMemo(() => calloutTargets(frame), [frame]);
  return (
    <group>
      {items.map((c) => (
        <CalloutItem key={c.id} id={c.id} label={c.label} anchor={c.anchor} />
      ))}
    </group>
  );
}
