// Data-driven callout labels for the cinematic view (reference-image style). A label
// is only produced for a structure that actually exists in the current frame. Pure.

import type { FrameData } from "../../../api/types";
import { radiusForMass } from "./biomap";

export interface Callout {
  id: string;
  label: string;
  anchor: [number, number, number]; // point the leader line touches
}

export function calloutTargets(frame: FrameData): Callout[] {
  const R = radiusForMass(frame.mass ?? 0.001);
  const list: Callout[] = [
    { id: "membrane", label: "Membrane", anchor: [R * 0.94, R * 0.34, 0] },
    { id: "transport", label: "Transport Protein", anchor: [R * 0.72, R * 0.66, R * 0.12] },
    { id: "channel", label: "Glucose Channel", anchor: [-R * 0.78, R * 0.5, R * 0.12] },
    { id: "ribosome", label: "Ribosome", anchor: [R * 0.34, -R * 0.3, R * 0.36] },
    { id: "nucleoid", label: "Nucleoid / Genome", anchor: [0, 0, 0] },
    { id: "cytoplasm", label: "Cytoplasm", anchor: [-R * 0.42, -R * 0.52, R * 0.22] },
    { id: "atp", label: "ATP Flow", anchor: [R * 0.24, R * 0.22, -R * 0.32] },
  ];
  if (frame.signalling) {
    list.push({ id: "signalling", label: "Signalling Pathway", anchor: [-R * 0.6, -R * 0.42, -R * 0.22] });
  }
  if (frame.field_glc && frame.field_glc.length) {
    list.push({ id: "nutrients", label: "Nutrient Gradient", anchor: [0, R + 0.7, 0] });
  }
  return list;
}
