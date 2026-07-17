// Pure helpers for scientific figure export: computing a "nice" scale-bar length and
// assembling legend entries. The actual canvas drawing lives in the capture bridge;
// these bits are unit-tested.

/** Round a raw magnitude to a 1 / 2 / 5 × 10^n "nice" number. */
export function niceStep(raw: number): number {
  if (raw <= 0) return 0;
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  const s = n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10;
  return s * pow;
}

export interface ScaleBar {
  units: number; // length of the bar in domain units (e.g. grid sites)
  px: number; // its length in pixels
}

/** A scale bar close to `targetPx` pixels long, snapped to a nice unit count. */
export function scaleBar(pixelsPerUnit: number, targetPx = 130): ScaleBar {
  if (!isFinite(pixelsPerUnit) || pixelsPerUnit <= 0) return { units: 0, px: 0 };
  const units = niceStep(targetPx / pixelsPerUnit);
  return { units, px: units * pixelsPerUnit };
}

export interface LegendEntry {
  color: string;
  label: string;
}

/** Legend entries for the current view (clone swatches, or a metric note). */
export function legendFor(mode: string, cloneColors: string[]): LegendEntry[] {
  if (mode === "clone") {
    return cloneColors.map((color, i) => ({ color, label: `clone #${i}` }));
  }
  return [{ color: "#fde047", label: `${mode} (low → high)` }];
}
