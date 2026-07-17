// Rendering quality tiers for the Scientific Cell renderer. Pure so the tier → effect
// mapping and the auto-quality stepping can be unit-tested. Higher tiers enable more
// post-processing and denser molecular traffic; lower tiers stay smooth on weak GPUs.

export type Quality = "low" | "medium" | "high";
export type QualityMode = Quality | "auto";

export interface QualitySettings {
  bloom: boolean;
  vignette: boolean;
  dof: boolean; // depth of field
  ssao: boolean; // ambient occlusion
  fresnel: boolean; // Fresnel membrane rim
  densityScale: number; // molecular particle-count multiplier
  dpr: number; // device-pixel-ratio cap
}

export function qualitySettings(q: Quality): QualitySettings {
  switch (q) {
    case "low":
      return { bloom: false, vignette: false, dof: false, ssao: false, fresnel: true, densityScale: 0.45, dpr: 1 };
    case "medium":
      return { bloom: true, vignette: true, dof: false, ssao: false, fresnel: true, densityScale: 0.75, dpr: 1.5 };
    case "high":
      return { bloom: true, vignette: true, dof: true, ssao: true, fresnel: true, densityScale: 1, dpr: 2 };
  }
}

/** True when any post-processing effect is enabled (composer should mount). */
export function hasPostFX(s: QualitySettings): boolean {
  return s.bloom || s.vignette || s.dof || s.ssao;
}

const ORDER: Quality[] = ["low", "medium", "high"];

/**
 * Auto-quality stepping: drop a tier when the frame rate is poor, raise one when
 * there is comfortable headroom. Hysteresis (30 / 55 fps) avoids oscillation.
 */
export function nextAutoQuality(current: Quality, fps: number): Quality {
  const i = ORDER.indexOf(current);
  if (fps < 30 && i > 0) return ORDER[i - 1];
  if (fps > 55 && i < ORDER.length - 1) return ORDER[i + 1];
  return current;
}

/** Resolve a quality mode (which may be "auto") to a concrete tier. */
export function resolveQuality(mode: QualityMode, autoTier: Quality): Quality {
  return mode === "auto" ? autoTier : mode;
}
