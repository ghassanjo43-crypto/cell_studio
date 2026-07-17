// Small shared geometry helpers for the Cell Explorer scene.

import * as THREE from "three";

/** Cell radius (scene units) from biomass — matches the legacy viewer's scaling. */
export function radiusForMass(mass: number): number {
  return 0.6 + Math.cbrt(Math.max(mass, 0)) * 0.7;
}

/** Evenly spread `n` points on a unit sphere (Fibonacci lattice) — deterministic. */
export function spherePoints(n: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    pts.push(new THREE.Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r));
  }
  return pts;
}

/** Fixed offsets (fractions of cell radius) for the internal compartments. */
export const COMPARTMENT_OFFSET: Record<string, [number, number, number]> = {
  nucleoid: [0.0, 0.0, 0.0],
  membrane_zone: [0.55, 0.35, 0.15],
  cytosol: [-0.4, -0.28, -0.12],
};
