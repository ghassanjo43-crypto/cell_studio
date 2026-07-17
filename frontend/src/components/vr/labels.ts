// Pure builders for the floating info panels shown in the 3D / VR scene.
// Kept free of React/Three so they can be unit-tested.

import type { FrameData } from "../../api/types";

export interface Panel {
  title: string;
  lines: string[];
}

function fmt(v: number): string {
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1000 || a < 0.01) return v.toExponential(2);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(3);
}

/** Build the set of panels appropriate to the current frame (scenario-aware). */
export function buildPanels(frame: FrameData | null): Panel[] {
  if (!frame) return [{ title: "Cell", lines: ["awaiting data…"] }];

  const panels: Panel[] = [
    {
      title: "Vitals",
      lines: [
        `status: ${frame.status ?? "—"}`,
        `biomass: ${fmt(frame.mass)} gDW`,
        `generation: ${frame.generation}`,
        `divisions: ${frame.divisions}`,
        `membrane: ${Math.round(frame.membrane_integrity * 100)}%`,
      ],
    },
  ];

  if (frame.nutrients) {
    const lines = Object.entries(frame.nutrients).map(
      ([n, v]) => `${n}: surface ${fmt(v.surface)} mM`,
    );
    if (frame.limiting) lines.push(`limiting: ${frame.limiting.replace("met.", "")}`);
    panels.push({ title: "Nutrients", lines });
  } else {
    panels.push({
      title: "Glucose",
      lines: [`medium: ${fmt(frame.env_glucose)}`, `internal: ${fmt(frame.pool_glucose)}`],
    });
  }

  if (frame.compartments) {
    panels.push({
      title: "Compartments (energy)",
      lines: Object.entries(frame.compartments).map(
        ([c, v]) => `${c.replace("_", " ")}: ${fmt(v.energy)}${v.stressed ? " ⚠" : ""}`,
      ),
    });
  }

  if (frame.signalling) {
    const s = frame.signalling;
    panels.push({
      title: "Signalling",
      lines: [
        `mode: ${s.mode ?? "—"}${s.survival ? " ⚠" : ""}`,
        `starvation: ${fmt(s.signals.starvation)}`,
        `growth: ${fmt(s.signals.growth)}`,
      ],
    });
  }

  return panels;
}
