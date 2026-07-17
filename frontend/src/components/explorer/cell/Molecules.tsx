// The molecular traffic + crowding of the cytoplasm, all instanced and data-driven,
// with a biological scale hierarchy, non-spherical protein-like shapes, per-instance
// uniqueness, and per-class Brownian (thermal) diffusion:
//  • crowding blobs pack the cytoplasm      (∝ biomass + protein)     — tiny, slow
//  • folded proteins tumble through it       (∝ protein synthesis)     — small, slow
//    (rendered across several distinct geometries so no two look identical)
//  • metabolic enzymes with active-site cleft(∝ metabolism + pool)     — small
//  • ribosomes (two-lobed 60S/40S)           (∝ protein synthesis)     — medium
//  • vesicles traffic to the membrane        (∝ growth + repair)       — medium, slow
//  • ATP produced centrally, transported out (∝ metabolic activity)    — tiny, fast
//  • glucose streams in to the transporters  (∝ external glucose)      — tiny, fast
//  • metabolites diffuse internally          (∝ internal glucose pool) — tiny, fastest
//
// Diffusion coefficients differ per class (small molecules jitter more than big
// complexes), as in a real crowded cytoplasm.

import { useMemo } from "react";
import * as THREE from "three";
import type { ObjectId } from "../inspect";
import { COMPARTMENT_OFFSET } from "../scene/geometry";
import type { CellVisual } from "./biomap";
import { useDrugFx } from "./drugVisual";
import { InstancedField } from "./InstancedField";
import { enzymeVariants, proteinVariants, ribosomeGeometry } from "./shapes";

export function Molecules({
  visual, cinematic = false, onSelect,
}: {
  visual: CellVisual;
  cinematic?: boolean;
  onSelect?: (id: ObjectId) => void;
}) {
  const R = visual.radius;
  const dens = cinematic ? 1.4 : 1;
  const proteins = proteinVariants();
  const enzymes = enzymeVariants();
  // Drug response: ATP dims, ribosomes stall, polymerase/DNA-binding traffic fades.
  const fx = useDrugFx();

  // A handful of stable cluster centres → the cytoplasm forms dense molecular "clouds"
  // separated by sparser valleys, so the interior reads as a landscape with ridges and
  // hollows instead of a uniform spherical fill. Placement only (counts still come from
  // data), so it asserts no biology — just where the crowd happens to bunch up.
  // A cluster of `n` centre points at a chosen radius band (fraction of R), optionally
  // pulled toward the floor. Each molecular species gets its OWN set, so the cell forms
  // distinct neighbourhoods — a ribosome-rich zone here, an enzyme-rich zone there — the
  // way a real cytoplasm is organised, not one uniform cloud. Arrangement only (counts
  // stay data-driven), so it asserts no biology.
  const { anchors, ribosomeAnchors, enzymeAnchors, metaboliteAnchors, membraneSpots } = useMemo(() => {
    const make = (n: number, minR: number, maxR: number, floor = 0.12) => {
      const list: THREE.Vector3[] = [];
      for (let k = 0; k < n; k++) {
        const v = new THREE.Vector3(Math.random() * 2 - 1, (Math.random() * 2 - 1) * 0.7, Math.random() * 2 - 1);
        if (v.lengthSq() < 1e-4) v.set(1, 0, 0);
        v.normalize().multiplyScalar(R * (minR + Math.random() * (maxR - minR)));
        v.y -= R * floor;
        list.push(v);
      }
      return list;
    };
    // A few "active membrane regions" (unit directions) — transporter/repair-rich spots
    // on the surface. Glucose funnels toward them (converging on transporters) and repair
    // vesicles deliver lipid there, so both have a destination rather than wandering.
    const spots: THREE.Vector3[] = [];
    for (let k = 0; k < 4; k++) {
      const v = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1);
      if (v.lengthSq() < 1e-4) v.set(1, 0, 0);
      spots.push(v.normalize());
    }
    return {
      anchors: make(6, 0.32, 0.82), // general crowd landscape
      ribosomeAnchors: make(4, 0.3, 0.55), // hug the DNA shell (transcription-coupled)
      enzymeAnchors: make(3, 0.2, 0.55), // enzyme-rich metabolic patches
      metaboliteAnchors: make(4, 0.25, 0.7), // metabolite-rich pockets
      membraneSpots: spots,
    };
  }, [R]);

  // The single hottest ATP compartment (from measured compartment.energy), if any — ATP
  // is enriched around it (energy is produced there and diffuses out).
  const hotComp = useMemo(() => {
    const comps = visual.compartments;
    if (!comps) return null;
    let best: string | null = null;
    for (const [name, c] of Object.entries(comps)) if (best === null || c.energy > comps[best].energy) best = name;
    if (!best || comps[best].energy <= 0) return null;
    const off = COMPARTMENT_OFFSET[best] ?? [0, 0, 0];
    return new THREE.Vector3(off[0] * R, off[1] * R, off[2] * R);
  }, [visual.compartments, R]);

  // Fill the cytoplasm volume: stable per-instance radius from the seed index. A gentle
  // downward "floor bias" packs more of the crowd toward the lower interior, then each
  // instance is pulled partway toward one of `centers` → clumpy clouds and sparse valleys.
  const clustered = (spread: number, centers: THREE.Vector3[], pull: number) =>
    (dir: THREE.Vector3, phase: number, i: number, out: THREE.Vector3) => {
      const rr = R * (0.15 + spread * ((i * 0.61803) % 1));
      const wob = 1 + 0.025 * Math.sin(phase * 6.28 + i * 0.7);
      out.copy(dir).multiplyScalar(rr * wob);
      out.y = out.y * 0.78 - R * 0.12;
      out.lerp(centers[i % centers.length], pull);
    };
  const volume = (spread: number) => clustered(spread, anchors, 0.32);

  return (
    <group>
      {/* Macromolecular crowding — the dense, wall-to-wall macromolecular background of
          the cytoplasm. Split across three of the folded-protein variant geometries (with
          muted, desaturated colours) so the "crowd" reads as real, differently-shaped
          macromolecules packed together — not a haze of identical grey dots. Matte and
          scene-lit (no glow), so SSAO lays down contact shadows between neighbours and the
          interior looks like a Goodsell-style solid mass of protein rather than empty gel. */}
      {[3, 5, 7].map((k, j) => (
        <InstancedField
          key={`crowd-${k}`}
          max={360}
          count={Math.round((visual.crowdingCount / 3) * dens)}
          color={["#43476e", "#553f6b", "#3a5566"][j]}
          size={0.036 + j * 0.006}
          speed={0.045}
          emissive={0.02}
          roughness={0.9}
          metalness={0.02}
          spin
          diffusion={0.016}
          soft={0.16}
          aspect
          geometry={<primitive object={proteins[k]} attach="geometry" />}
          place={volume(0.82)}
        />
      ))}

      {/* Colourful "hero" protein complexes scattered through the crowd — saturated,
          glossy, wet-looking beads (magenta / teal / amber) that pop against the muted
          background, like the flower-cluster complexes in the reference. */}
      {[
        { c: "#e879a8", k: 1 },
        { c: "#3fc7c0", k: 6 },
        { c: "#f0a862", k: 9 },
      ].map(({ c, k }, j) => (
        <InstancedField
          key={`hero-${j}`}
          max={26}
          count={Math.round((visual.proteinCount / 5) * dens)}
          color={c}
          size={0.07}
          speed={0.075}
          emissive={0.12}
          roughness={0.38}
          metalness={0.12}
          spin
          diffusion={0.02}
          soft={0.2}
          aspect
          hoverId="protein"
          onSelect={onSelect}
          geometry={<primitive object={proteins[k]} attach="geometry" />}
          place={volume(0.68 + j * 0.04)}
        />
      ))}

      {/* Folded proteins — the brighter, functional foreground proteins, split across
          distinct geometries so none are identical. Matte + scene-lit (hydrated, not neon). */}
      {[0, 2, 4].map((k, j) => (
        <InstancedField
          key={k}
          max={48}
          count={Math.round((visual.proteinCount / 3) * dens)}
          color={["#8fb8f0", "#b79aef", "#6fcfe0"][j]}
          size={0.062}
          speed={0.085}
          emissive={0.06}
          roughness={0.44}
          metalness={0.08}
          spin
          diffusion={0.018}
          soft={0.18}
          aspect
          hoverId="protein"
          onSelect={onSelect}
          geometry={<primitive object={proteins[k]} attach="geometry" />}
          place={volume(0.74 + j * 0.03)}
        />
      ))}

      {/* Metabolic enzymes (two-lobed, active-site cleft) — split across the enzyme
          variants so the population looks heterogeneous, and gathered into a few
          enzyme-rich metabolic patches (their own neighbourhood, not the general crowd). */}
      {[0, 1, 2].map((k) => (
        <InstancedField
          key={`enz-${k}`}
          max={44}
          count={Math.round(visual.enzymeCount / 3)}
          color={["#5fcabc", "#57b8a8", "#6bd0c0"][k]}
          size={0.052}
          speed={0.12}
          emissive={0.05}
          roughness={0.72}
          metalness={0.03}
          spin
          diffusion={0.03}
          soft={0.16}
          aspect
          hoverId="enzyme"
          onSelect={onSelect}
          geometry={<primitive object={enzymes[k]} attach="geometry" />}
          place={clustered(0.5, enzymeAnchors, 0.5)}
        />
      ))}

      {/* Ribosomes (two-lobed 60S/40S) — abundance tracks protein synthesis. Enriched in
          a shell hugging the DNA (transcription-coupled translation), so the nucleoid is
          the busiest place in the cell. Medium, matte, with a subtle translation throb. */}
      <InstancedField
        max={64}
        count={visual.ribosomeCount}
        color="#e8eef8"
        size={0.082}
        speed={0.1}
        emissive={0.06}
        roughness={0.5}
        metalness={0.06}
        spin
        diffusion={0.012}
        pulse={0.14 * (1 - fx.ribosomeStall)}
        soft={0.1}
        aspect
        hoverId="ribosome"
        onSelect={onSelect}
        geometry={<primitive object={ribosomeGeometry()} attach="geometry" />}
        place={clustered(0.38, ribosomeAnchors, 0.64)}
      />

      {/* DNA-binding proteins — RNA polymerase / replication machinery / nucleoid-
          associated proteins bound around the chromosome. Count derives from measured
          activity (transcription foci ∝ mRNA, plus the replisome when replicating); they
          sit in a flattened shell on the DNA ring, making the genome visibly busy. */}
      <InstancedField
        max={30}
        count={Math.round(
          Math.min(28, visual.transcriptionFoci * 2.2 + (visual.replicating ? 10 : 0) + visual.proteinCount * 0.12) *
            (1 - fx.polymeraseFade),
        )}
        color="#7cc7f0"
        size={0.05}
        speed={0.07}
        emissive={0.14}
        roughness={0.42}
        metalness={0.1}
        spin
        diffusion={0.01}
        soft={0.16}
        aspect
        hoverId="protein"
        onSelect={onSelect}
        geometry={<primitive object={proteins[3]} attach="geometry" />}
        place={(_dir, phase, i, out) => {
          // Travel around the chromosome ring (radius ~0.44R) — polymerases / binding
          // proteins tracking along the DNA rather than sitting still. Each on its own
          // arc; the per-instance pause envelope makes some dock while others move.
          const a = i * 2.399 + phase * Math.PI * 2;
          const rr = R * 0.44 * (0.88 + 0.24 * ((i * 0.61803) % 1));
          out.set(Math.cos(a) * rr, Math.sin(a) * rr, (((i * 0.37) % 1) - 0.5) * R * 0.12);
        }}
      />

      {/* Vesicles trafficking to the membrane — medium, translucent, hydrated (a wet
          lipid carrier, not a glassy bauble). Softly deforming as they drift. */}
      <InstancedField
        max={18}
        count={visual.vesicleCount}
        color="#c7d2fe"
        size={0.12}
        speed={0.16}
        emissive={0.06}
        roughness={0.6}
        metalness={0.02}
        transparent
        opacity={0.45}
        diffusion={0.008}
        soft={0.14}
        hoverId="vesicle"
        onSelect={onSelect}
        geometry={<icosahedronGeometry args={[1, 2]} />}
        fade
        place={(dir, phase, i, out) => {
          // Lipid-carrier vesicles traffic from the interior out to an active membrane
          // region and dock there (targeted delivery / repair), rather than drifting to
          // random points — more so while membrane repair is up-regulated.
          const spot = membraneSpots[i % membraneSpots.length];
          const rr = R * (0.55 + 0.42 * phase);
          const bias = 0.35 + 0.4 * Math.min(1, phase) * (0.5 + 0.5 * Math.max(0, visual.membraneRepair - 1));
          out.set(
            dir.x + (spot.x - dir.x) * bias,
            dir.y + (spot.y - dir.y) * bias,
            dir.z + (spot.z - dir.z) * bias,
          ).multiplyScalar(rr);
        }}
      />

      {/* ATP — the energy currency: bright, hard-pulsing, fast and purposeful so it
          immediately reads as "energy." Enriched around the hot ATP compartment (its
          source) and streaming outward toward demand; otherwise it radiates from the
          metabolic core. Self-luminous (bloom-fed). */}
      <InstancedField
        max={96}
        count={Math.round(visual.atpCount * dens)}
        color="#5ef0ff"
        size={0.036 * (1 - 0.3 * fx.atpDim)}
        speed={0.8}
        emissive={1.5 * (1 - 0.8 * fx.atpDim)}
        pulse={0.4}
        diffusion={0.06}
        glow
        hoverId="atp"
        onSelect={onSelect}
        fade
        place={(dir, phase, _i, out) => {
          out.copy(dir).multiplyScalar(R * (0.1 + 0.72 * phase));
          if (hotComp) out.lerp(hotComp, 0.55 * (1 - phase)); // dense at the source, thinning as it diffuses out
        }}
      />

      {/* Glucose influx → membrane transporters (small, streaming inward, luminous). */}
      <InstancedField
        max={76}
        count={visual.glucoseCount}
        color="#fbbf24"
        size={0.034}
        speed={0.35}
        diffusion={0.04}
        glow
        hoverId="glucose"
        onSelect={onSelect}
        fade
        place={(dir, phase, i, out) => {
          // Glucose streams inward and converges on transporter-rich membrane spots
          // (attracted to the transporters) rather than arriving at random points.
          const spot = membraneSpots[i % membraneSpots.length];
          const start = R + 1.4;
          const end = R + 0.03;
          const conv = 0.55 * phase; // funnels toward the spot as it nears the surface
          out.set(
            dir.x + (spot.x - dir.x) * conv,
            dir.y + (spot.y - dir.y) * conv,
            dir.z + (spot.z - dir.z) * conv,
          ).normalize().multiplyScalar(start + (end - start) * phase);
        }}
      />

      {/* Internal metabolites — smallest, fastest thermal motion — diffusing outward but
          concentrated into a few metabolite-rich pockets (their own neighbourhood). */}
      <InstancedField
        max={90}
        count={Math.round(visual.metaboliteCount * dens)}
        color="#a3e635"
        size={0.021}
        speed={0.3}
        diffusion={0.06}
        glow
        hoverId="metabolite"
        onSelect={onSelect}
        fade
        place={(dir, phase, i, out) => {
          out.copy(dir).multiplyScalar(R * (0.15 + 0.55 * phase));
          out.lerp(metaboliteAnchors[i % metaboliteAnchors.length], 0.28);
        }}
      />
    </group>
  );
}
