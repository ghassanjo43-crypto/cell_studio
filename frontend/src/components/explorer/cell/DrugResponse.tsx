// Additive drug-response visuals: the new, immediately-readable effects that tell you
// which drug is acting — leakage & membrane flashes (disruptor), glucose piling up outside
// (transport inhibitor), ROS particles & mutation sparks (oxidative), repair vesicles
// rushing to the membrane. Everything is gated by the DrugVisualController's intensities
// (0 ⇒ nothing renders), reuses the existing instanced-field renderer, and slows with the
// global motion multiplier, so it is data-driven and cheap. Modulation of *existing*
// molecules (ATP dimming, ribosome stall, fork freeze) lives in those components.

import type { DrugVisualState } from "./drugVisual";
import { InstancedField } from "./InstancedField";

const count = (intensity: number, max: number) => Math.round(Math.max(0, Math.min(1, intensity)) * max);

export function DrugResponse({ fx, radius }: { fx: DrugVisualState; radius: number }) {
  if (!fx.active) return null;
  const R = radius;
  const tint = fx.tints[0] ?? "#f87171";

  return (
    <group>
      {/* Membrane disruptor — leakage particles escaping through the ruptured envelope. */}
      <InstancedField
        max={48}
        count={count(fx.leakage, 40)}
        color={tint}
        size={0.03}
        speed={0.5}
        emissive={1.3}
        diffusion={0.05}
        glow
        fade
        place={(dir, phase, _i, out) => {
          out.copy(dir).multiplyScalar(R * (0.85 + 0.6 * phase)); // from the membrane outward
        }}
      />

      {/* Membrane disruptor — bright flashes at damaged sites on the surface. */}
      <InstancedField
        max={28}
        count={count(fx.membraneDamage, 22)}
        color={tint}
        size={0.06}
        speed={0.9}
        emissive={1.6}
        glow
        fade
        place={(dir, _phase, _i, out) => {
          out.copy(dir).multiplyScalar(R * 1.0); // sit on the membrane surface
        }}
      />

      {/* Membrane disruptor — repair vesicles rush inward→out to the damaged membrane. */}
      <InstancedField
        max={20}
        count={count(fx.membraneRepair, 16)}
        color="#4ade80"
        size={0.09}
        speed={0.4}
        emissive={0.5}
        transparent
        opacity={0.55}
        diffusion={0.01}
        soft={0.14}
        geometry={<icosahedronGeometry args={[1, 2]} />}
        fade
        place={(dir, phase, _i, out) => {
          out.copy(dir).multiplyScalar(R * (0.45 + 0.55 * phase)); // travel out to the membrane
        }}
      />

      {/* Transport inhibitor — glucose accumulates OUTSIDE the membrane (can't get in). */}
      <InstancedField
        max={72}
        count={count(fx.transportBlock, 60)}
        color="#fbbf24"
        size={0.034}
        speed={0.12}
        emissive={0.9}
        diffusion={0.03}
        glow
        place={(dir, phase, i, out) => {
          // A dense shell just outside the surface, jostling but not entering.
          const rr = R * (1.06 + 0.3 * ((i * 0.61803) % 1));
          const wob = 1 + 0.015 * Math.sin(phase * 6.28 + i);
          out.copy(dir).multiplyScalar(rr * wob);
        }}
      />

      {/* Oxidative stress — reactive-oxygen-species particles filling the cytoplasm. */}
      <InstancedField
        max={80}
        count={count(fx.ros, 66)}
        color="#fb7185"
        size={0.028}
        speed={0.5}
        emissive={1.4}
        diffusion={0.08}
        glow
        fade
        place={(dir, phase, i, out) => {
          const rr = R * (0.15 + 0.8 * ((i * 0.61803) % 1));
          out.copy(dir).multiplyScalar(rr * (1 + 0.03 * Math.sin(phase * 6.28 + i)));
        }}
      />

      {/* Oxidative stress — mutation sparks flashing on the genome. */}
      <InstancedField
        max={24}
        count={count(fx.mutationSparks, 18)}
        color="#fde68a"
        size={0.04}
        speed={1.1}
        emissive={2.0}
        glow
        fade
        place={(dir, _phase, i, out) => {
          const p = dir.clone();
          p.y *= 0.4;
          if (p.lengthSq() < 1e-4) p.set(1, 0, 0);
          p.normalize();
          out.copy(p).multiplyScalar(R * 0.44 * (0.9 + 0.2 * ((i * 0.61803) % 1)));
        }}
      />
    </group>
  );
}
