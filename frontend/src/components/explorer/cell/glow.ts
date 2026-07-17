// A soft radial-gradient sprite texture used for cinematic light haze / god-ray glow.
// Cached — one canvas texture shared by all instances.

import * as THREE from "three";

let cached: THREE.CanvasTexture | null = null;

export function radialGlowTexture(): THREE.CanvasTexture {
  if (cached) return cached;
  const size = 256;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,0.9)");
  g.addColorStop(0.35, "rgba(200,230,255,0.35)");
  g.addColorStop(1, "rgba(200,230,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  cached = new THREE.CanvasTexture(c);
  cached.colorSpace = THREE.SRGBColorSpace;
  return cached;
}
