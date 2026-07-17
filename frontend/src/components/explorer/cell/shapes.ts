// Cached non-spherical geometries for a richer, more protein-like molecular look.
// Built once and shared across instanced meshes.

import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

let _ribosome: THREE.BufferGeometry | null = null;
/** A ribosome: a large (60S) lobe fused to a small (40S) lobe. */
export function ribosomeGeometry(): THREE.BufferGeometry {
  if (_ribosome) return _ribosome;
  const large = new THREE.SphereGeometry(1, 12, 12);
  const small = new THREE.SphereGeometry(0.62, 10, 10);
  small.translate(0, 0.95, 0);
  _ribosome = mergeGeometries([large, small]) ?? large;
  return _ribosome;
}

let _protein: THREE.BufferGeometry | null = null;
/** A folded-protein-like cluster of fused faceted blobs. */
export function proteinGeometry(): THREE.BufferGeometry {
  if (_protein) return _protein;
  const parts: THREE.BufferGeometry[] = [];
  const pts: [number, number, number][] = [
    [0, 0, 0], [0.7, 0.3, 0.1], [-0.5, 0.5, -0.2], [0.2, -0.6, 0.4],
  ];
  for (const [x, y, z] of pts) {
    const s = new THREE.IcosahedronGeometry(0.6, 0);
    s.translate(x, y, z);
    parts.push(s);
  }
  _protein = mergeGeometries(parts) ?? new THREE.IcosahedronGeometry(1, 0);
  return _protein;
}

let _receptor: THREE.BufferGeometry | null = null;
/** A receptor: a domed head on a short stalk (embedded in the membrane). */
export function receptorGeometry(): THREE.BufferGeometry {
  if (_receptor) return _receptor;
  const head = new THREE.SphereGeometry(1, 12, 12);
  const stalk = new THREE.CylinderGeometry(0.4, 0.55, 1.2, 8);
  stalk.translate(0, -1.1, 0);
  _receptor = mergeGeometries([head, stalk]) ?? head;
  return _receptor;
}

// A tiny deterministic PRNG so procedural shapes are stable across reloads (no
// flicker) yet each variant is distinct.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** One procedurally folded protein: an asymmetric cluster of fused faceted domains. */
function foldedProtein(seed: number): THREE.BufferGeometry {
  const rnd = mulberry32(seed);
  const parts: THREE.BufferGeometry[] = [];
  const domains = 3 + Math.floor(rnd() * 4); // 3–6 domains → irregular, organic
  let px = 0;
  let py = 0;
  let pz = 0;
  for (let i = 0; i < domains; i++) {
    const r = 0.35 + rnd() * 0.5;
    const g = new THREE.IcosahedronGeometry(r, 0);
    // Walk from the previous domain so the chain folds asymmetrically.
    px += (rnd() - 0.5) * 1.1;
    py += (rnd() - 0.5) * 1.1;
    pz += (rnd() - 0.5) * 1.1;
    g.translate(px, py, pz);
    parts.push(g);
  }
  const merged = mergeGeometries(parts) ?? new THREE.IcosahedronGeometry(1, 0);
  merged.center();
  // Normalise scale so variants are visually comparable in size.
  merged.computeBoundingSphere();
  const s = merged.boundingSphere ? 1 / merged.boundingSphere.radius : 1;
  merged.scale(s, s, s);
  return merged;
}

/** Merge fused domains, centre, and normalise to unit radius so variants are size-comparable. */
function finalizeProtein(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const merged = mergeGeometries(parts) ?? new THREE.IcosahedronGeometry(1, 0);
  merged.center();
  merged.computeBoundingSphere();
  const s = merged.boundingSphere ? 1 / merged.boundingSphere.radius : 1;
  merged.scale(s, s, s);
  return merged;
}

/** Elongated / fibrillar protein: a gently curved chain of shrinking domains. */
function elongatedProtein(seed: number): THREE.BufferGeometry {
  const rnd = mulberry32(seed);
  const parts: THREE.BufferGeometry[] = [];
  const n = 4 + Math.floor(rnd() * 3);
  const curve = (rnd() - 0.5) * 0.5;
  for (let i = 0; i < n; i++) {
    const r = 0.5 - i * 0.045 + rnd() * 0.1;
    const g = new THREE.IcosahedronGeometry(Math.max(0.2, r), 0);
    g.translate(i * 0.85, Math.sin(i * curve) * 0.5, Math.cos(i * curve) * 0.25);
    parts.push(g);
  }
  return finalizeProtein(parts);
}

/** Branched protein: a central hub with a few radiating arm domains. */
function branchedProtein(seed: number): THREE.BufferGeometry {
  const rnd = mulberry32(seed);
  const parts: THREE.BufferGeometry[] = [new THREE.IcosahedronGeometry(0.7, 0)];
  const arms = 3 + Math.floor(rnd() * 2);
  for (let i = 0; i < arms; i++) {
    const a = (i / arms) * Math.PI * 2 + rnd();
    const tilt = (rnd() - 0.5) * 1.2;
    const len = 0.9 + rnd() * 0.6;
    const g = new THREE.IcosahedronGeometry(0.4 + rnd() * 0.2, 0);
    g.translate(Math.cos(a) * len, tilt, Math.sin(a) * len);
    parts.push(g);
  }
  return finalizeProtein(parts);
}

/** Compact globular protein: a tight cluster of overlapping lobes (near-spherical). */
function compactGlobular(seed: number): THREE.BufferGeometry {
  const rnd = mulberry32(seed);
  const parts: THREE.BufferGeometry[] = [];
  const n = 4 + Math.floor(rnd() * 3);
  for (let i = 0; i < n; i++) {
    const g = new THREE.IcosahedronGeometry(0.55 + rnd() * 0.25, 1);
    g.translate((rnd() - 0.5) * 0.7, (rnd() - 0.5) * 0.7, (rnd() - 0.5) * 0.7);
    parts.push(g);
  }
  return finalizeProtein(parts);
}

let _proteinVariants: THREE.BufferGeometry[] | null = null;
/**
 * A library of distinct protein geometries spanning several structural families —
 * asymmetric folded, elongated/fibrillar, branched, and compact globular — so nearby
 * proteins never look like copies of one shape. Cached; distinct vertex counts.
 */
export function proteinVariants(): THREE.BufferGeometry[] {
  if (_proteinVariants) return _proteinVariants;
  _proteinVariants = [
    foldedProtein(1000),
    elongatedProtein(1201),
    branchedProtein(1409),
    compactGlobular(1613),
    foldedProtein(1811),
    elongatedProtein(2017),
    branchedProtein(2213),
    compactGlobular(2417),
    foldedProtein(2621),
    elongatedProtein(2819),
  ];
  return _proteinVariants;
}

let _enzymeVariants: THREE.BufferGeometry[] | null = null;
/** Enzymes: two-lobed shapes with a visible cleft (the active site). */
export function enzymeVariants(): THREE.BufferGeometry[] {
  if (_enzymeVariants) return _enzymeVariants;
  _enzymeVariants = Array.from({ length: 3 }, (_, k) => {
    const rnd = mulberry32(500 + k * 131);
    const a = new THREE.IcosahedronGeometry(0.9, 0);
    a.translate(-0.55, 0, 0);
    const b = new THREE.IcosahedronGeometry(0.75 + rnd() * 0.2, 0);
    b.translate(0.6, (rnd() - 0.5) * 0.4, 0);
    const merged = mergeGeometries([a, b]) ?? a;
    merged.center();
    return merged;
  });
  return _enzymeVariants;
}

let _channel: THREE.BufferGeometry | null = null;
/** A channel pore: an oligomeric barrel of subunits around a central lumen (no cylinder). */
export function channelGeometry(): THREE.BufferGeometry {
  if (_channel) return _channel;
  const subs: THREE.BufferGeometry[] = [];
  const n = 5; // pentameric barrel of subunits
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const s = new THREE.CapsuleGeometry(0.28, 1.0, 3, 6);
    s.translate(Math.cos(a) * 0.5, 0, Math.sin(a) * 0.5);
    subs.push(s);
  }
  _channel = mergeGeometries(subs) ?? new THREE.CylinderGeometry(0.5, 0.5, 1, 8);
  return _channel;
}

let _dnaHelix: THREE.BufferGeometry | null = null;
/**
 * A circular double helix: two sugar-phosphate strands spiralling around a ring of
 * radius `ringR`, joined by base-pair rungs — the bacterial chromosome read as the
 * iconic double helix (it genuinely is a supercoiled circular duplex, so this asserts
 * no biology the minimal cell lacks). Built once in unit space and cached; the caller
 * scales it via the nucleoid group.
 */
export function dnaDoubleHelixRing(ringR = 0.42, turns = 24): THREE.BufferGeometry {
  if (_dnaHelix) return _dnaHelix;
  const parts: THREE.BufferGeometry[] = [];
  const strandR = 0.055; // helix radius about the ring centreline
  const tube = 0.02; // strand thickness
  const seg = 400;
  const Z = new THREE.Vector3(0, 0, 1);
  const point = (u: number, a: number) => {
    const radial = new THREE.Vector3(Math.cos(u), Math.sin(u), 0);
    const off = radial.clone().multiplyScalar(Math.cos(a) * strandR).add(Z.clone().multiplyScalar(Math.sin(a) * strandR));
    return new THREE.Vector3(Math.cos(u) * ringR, Math.sin(u) * ringR, 0).add(off);
  };
  // Two antiparallel strands, phase-offset by π.
  for (const phase of [0, Math.PI]) {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= seg; i++) {
      const u = (i / seg) * Math.PI * 2;
      pts.push(point(u, turns * u + phase));
    }
    const curve = new THREE.CatmullRomCurve3(pts, true);
    parts.push(new THREE.TubeGeometry(curve, seg, tube, 6, true));
  }
  // Base-pair rungs bridging the two strands.
  const up = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < seg; i += 4) {
    const u = (i / seg) * Math.PI * 2;
    const a = turns * u;
    const c0 = point(u, a);
    const c1 = point(u, a + Math.PI);
    const mid = c0.clone().add(c1).multiplyScalar(0.5);
    const len = c0.distanceTo(c1);
    if (len < 1e-4) continue;
    const rung = new THREE.CylinderGeometry(0.008, 0.008, len, 5);
    rung.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(up, c1.clone().sub(c0).normalize()));
    rung.translate(mid.x, mid.y, mid.z);
    parts.push(rung);
  }
  _dnaHelix = mergeGeometries(parts) ?? new THREE.TorusGeometry(ringR, 0.05, 12, 120);
  return _dnaHelix;
}
