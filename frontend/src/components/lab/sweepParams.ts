// The parameters a user can sweep in the Experiment Lab, mapped to DesignConfig
// fields. Kept pure so the list + filtering can be unit-tested.

export interface SweepParam {
  field: string;
  label: string;
  kind: "number" | "category";
  options?: string[];
  scenarios: string[]; // "*" = all
  example: string;
}

export const SWEEP_PARAMS: SweepParam[] = [
  { field: "glucose_mmol", label: "Glucose (mmol)", kind: "number",
    scenarios: ["minimal", "lifecycle", "evolution", "compartment", "signalling"], example: "10, 30, 60" },
  { field: "medium_glucose", label: "Medium glucose (mmol)", kind: "number",
    scenarios: ["population"], example: "80, 150, 250" },
  { field: "nutrient_init", label: "Nutrient / site", kind: "number",
    scenarios: ["petri"], example: "0.6, 1.0, 1.5" },
  { field: "ammonium_conc", label: "Nitrogen (mM)", kind: "number",
    scenarios: ["spatial"], example: "2, 6, 12" },
  { field: "mutation_rate", label: "Mutation rate", kind: "number",
    scenarios: ["evolution", "population", "petri"], example: "0.5, 1.0, 2.0" },
  { field: "initial_cells", label: "Founder count", kind: "number",
    scenarios: ["population", "petri"], example: "1, 4, 8" },
  { field: "nutrient_pattern", label: "Nutrient gradient", kind: "category",
    options: ["uniform", "gradient", "patches"], scenarios: ["petri"], example: "gradient, patches" },
  { field: "feed_rate", label: "Feed rate", kind: "number",
    scenarios: ["population", "petri"], example: "0, 0.05, 0.15" },
  { field: "petri_diffusion", label: "Diffusion rate", kind: "number",
    scenarios: ["petri"], example: "0.1, 0.18, 0.24" },
  { field: "max_steps", label: "Max steps", kind: "number", scenarios: ["*"], example: "200, 400, 600" },
];

/** Sweep parameters applicable to a given base scenario. */
export function paramsForScenario(scenario: string): SweepParam[] {
  return SWEEP_PARAMS.filter((p) => p.scenarios.includes("*") || p.scenarios.includes(scenario));
}

/** Parse a comma-separated values string into typed sweep values. */
export function parseSweepValues(raw: string, kind: "number" | "category"): (number | string)[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => (kind === "number" ? Number(s) : s))
    .filter((v) => (typeof v === "number" ? !Number.isNaN(v) : true));
}
