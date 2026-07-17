// "Focus modes": named camera presets that also select a structure to open the
// inspector. Pure — the camera animation itself lives in Controls, driven by the
// distance/target here.

import type { FrameData } from "../../api/types";
import type { ObjectId } from "./inspect";

export type FocusKey = "membrane" | "genome" | "metabolism" | "signalling" | "nutrients" | "colony";

export interface FocusPreset {
  key: FocusKey;
  label: string;
  id: ObjectId; // structure to select (opens the inspector)
  distance: number; // orbit distance from target
  target: [number, number, number];
}

const PRESETS: Record<FocusKey, FocusPreset> = {
  membrane: { key: "membrane", label: "Membrane", id: "membrane", distance: 4.5, target: [0, 0, 0] },
  genome: { key: "genome", label: "Genome", id: "nucleoid", distance: 1.9, target: [0, 0, 0] },
  metabolism: { key: "metabolism", label: "Metabolism", id: "cytosol", distance: 3.0, target: [0, 0, 0] },
  signalling: { key: "signalling", label: "Signalling", id: "signalling", distance: 4.2, target: [0, 0, 0] },
  nutrients: { key: "nutrients", label: "Nutrients", id: "nutrients", distance: 9.0, target: [0, 0, 0] },
  colony: { key: "colony", label: "Colony", id: "petri", distance: 12, target: [0, 0, 0] },
};

/** Focus presets that make sense for the current frame's scenario. */
export function focusPresets(frame: FrameData | null): FocusPreset[] {
  if (!frame) return [];
  if (frame.petri) {
    return [PRESETS.colony, PRESETS.nutrients];
  }
  if (frame.population) {
    return [{ ...PRESETS.colony, id: "population" }, PRESETS.nutrients];
  }
  const list: FocusPreset[] = [PRESETS.membrane, PRESETS.genome, PRESETS.metabolism];
  if (frame.signalling) list.push(PRESETS.signalling);
  if (frame.field_glc || frame.nutrients) list.push(PRESETS.nutrients);
  return list;
}
