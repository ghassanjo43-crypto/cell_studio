// The cinematic tour script — an ordered list of camera "scenes" and the shots
// triggered by biological events. Pure: scenes carry a camera target/distance, the
// structure to highlight, a dwell time, and a data-driven caption. The camera easing
// itself lives in Controls.

import type { FrameData } from "../../../api/types";
import type { ObjectId } from "../inspect";

export interface TourScene {
  key: string;
  id: ObjectId; // structure to highlight (also opens its inspector)
  distance: number;
  target: [number, number, number];
  seconds: number;
  caption: (frame: FrameData | null) => string;
}

const ORIGIN: [number, number, number] = [0, 0, 0];
const pct = (v: number) => `${Math.round(v * 100)}%`;

function singleCellScenes(): TourScene[] {
  return [
    { key: "overview", id: "membrane", distance: 7, target: ORIGIN, seconds: 5,
      caption: () => "Whole-cell overview." },
    { key: "membrane", id: "membrane", distance: 4.3, target: ORIGIN, seconds: 6,
      caption: (f) => `The phospholipid bilayer — transport proteins, channels and receptors (integrity ${pct(f?.membrane_integrity ?? 1)}).` },
    { key: "transport", id: "transport", distance: 3.6, target: ORIGIN, seconds: 5,
      caption: (f) => `Transporters importing glucose — activity ${(f?.phenotype?.transport ?? 1).toFixed(2)}×.` },
    { key: "cytoplasm", id: "cytosol", distance: 3.0, target: ORIGIN, seconds: 6,
      caption: () => "In the cytoplasm: ribosomes translate proteins and ATP powers the cell." },
    { key: "genome", id: "nucleoid", distance: 1.9, target: ORIGIN, seconds: 6,
      caption: (f) =>
        f?.replication?.replicating
          ? `A replication fork is copying the genome — ${pct(f.replication.progress)} complete.`
          : "The genome — DNA with active transcription." },
    { key: "return", id: "membrane", distance: 7, target: ORIGIN, seconds: 4,
      caption: () => "Returning to the whole-cell view." },
  ];
}

function dishScenes(): TourScene[] {
  return [
    { key: "overview", id: "petri", distance: 12, target: ORIGIN, seconds: 5,
      caption: (f) => `The Petri dish — ${f?.petri?.alive ?? 0} cells across ${f?.petri?.colonies ?? 0} colonies.` },
    { key: "nutrients", id: "nutrients", distance: 9, target: ORIGIN, seconds: 5,
      caption: () => "The nutrient landscape — valleys mark depleted, nutrient-limited colony cores." },
    { key: "colony", id: "petri", distance: 5.5, target: ORIGIN, seconds: 6,
      caption: () => "Zooming into the biofilm — bright cells are active fronts, dim cells are starved cores." },
    { key: "return", id: "petri", distance: 12, target: ORIGIN, seconds: 4,
      caption: () => "Returning to the whole-dish view." },
  ];
}

function colonyScenes(): TourScene[] {
  return [
    { key: "overview", id: "population", distance: 7, target: ORIGIN, seconds: 5,
      caption: (f) => `The colony — ${f?.population?.alive ?? 0} living cells.` },
    { key: "colony", id: "population", distance: 4, target: ORIGIN, seconds: 6,
      caption: (f) => `Cells coloured by clone; dominant lineage ${f?.population?.dominant_lineage ?? "—"}.` },
    { key: "return", id: "population", distance: 7, target: ORIGIN, seconds: 4,
      caption: () => "Returning to the colony overview." },
  ];
}

export function tourScenes(frame: FrameData | null): TourScene[] {
  if (!frame) return [];
  if (frame.petri) return dishScenes();
  if (frame.population) return colonyScenes();
  return singleCellScenes();
}

export interface EventShot {
  id: ObjectId;
  distance: number;
  target: [number, number, number];
  caption: string;
}

/** The cinematic shot to cut to when an important event fires. */
export function eventShot(type: string, frame: FrameData | null): EventShot | null {
  switch (type) {
    case "division":
      return { id: "nucleoid", distance: 4.5, target: ORIGIN, caption: "Cell division — the furrow constricts and the daughters separate." };
    case "mutation":
      return { id: "nucleoid", distance: 2.2, target: ORIGIN, caption: "A mutation flashes across the genome." };
    case "survival_mode_entered":
      return { id: "signalling", distance: 4.2, target: ORIGIN, caption: "Survival mode — signalling floods the cell." };
    case "membrane_rupture":
      return { id: "membrane", distance: 4.5, target: ORIGIN, caption: "The membrane ruptures." };
    case "death":
      return { id: "membrane", distance: 7, target: ORIGIN, caption: "The cell has died." };
    case "clone_expansion":
    case "colony_extinct":
    case "biofilm_confluent":
      return { id: frame?.petri ? "petri" : "population", distance: frame?.petri ? 9 : 6, target: ORIGIN,
        caption: type === "clone_expansion" ? "A clone is expanding." : type === "biofilm_confluent" ? "The biofilm is confluent." : "A colony has gone extinct." };
    case "population_extinct":
      return { id: frame?.petri ? "petri" : "population", distance: frame?.petri ? 12 : 7, target: ORIGIN, caption: "The population has collapsed." };
    default:
      return null;
  }
}

//: Event types that trigger a cinematic, in priority order.
export const CINEMATIC_EVENTS = [
  "death", "division", "population_extinct", "membrane_rupture",
  "survival_mode_entered", "mutation", "clone_expansion", "biofilm_confluent", "colony_extinct",
];
