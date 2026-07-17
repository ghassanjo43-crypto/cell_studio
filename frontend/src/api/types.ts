// TypeScript mirrors of the backend Pydantic schemas. Kept in one place so the
// API client and UI share a single source of truth for shapes.

export type ScenarioKind =
  | "minimal"
  | "lifecycle"
  | "evolution"
  | "spatial"
  | "compartment"
  | "signalling"
  | "population"
  | "petri";

export type NutrientPattern = "uniform" | "gradient" | "patches";

// --- Drug Interaction Studio -------------------------------------------------
export type DrugVizTarget =
  | "membrane" | "ribosome" | "dna" | "protein" | "transport" | "signalling" | "cytoplasm";

/** A drug in the library (representative mechanism), from GET /drugs. */
export interface Drug {
  id: string;
  name: string;
  description: string;
  mechanism: string;
  targets: string[];
  channels: Record<string, number>;
  color: string;
  viz_target: DrugVizTarget;
  confidence: "high" | "medium" | "low";
  default_dose: number;
}

/** A drug applied to a run (part of the design config). */
export interface DrugDose {
  drug_id: string;
  dose: number;
  start_time?: number;
  duration?: number | null;
}

/** A currently-acting drug, carried on a treated frame (drives the viz + narration). */
export interface ActiveDrug {
  id: string;
  name: string;
  color: string;
  viz: DrugVizTarget;
  dose: number;
  strength: number;
  targets: string[];
  mechanism: string;
  confidence: "high" | "medium" | "low";
  channels?: Record<string, number>;
}

export interface DrugInterpretResult {
  drugs: string[];
  statements: string[];
  effects: Record<string, number>;
  prediction: string;
  grounded: boolean;
  narration?: string | null;
}

export interface DesignConfig {
  scenario: ScenarioKind;
  drugs?: DrugDose[];
  dt: number;
  max_steps: number;
  seed: number;
  initial_mass: number;
  glucose_mmol: number;
  volume_l: number;
  vmax: number;
  km: number;
  maintenance_atp: number;
  mu_max: number;
  initiation_mass: number;
  replication_time: number;
  division_mass: number;
  death_steps: number;
  mutation_rate: number;
  mutation_sigma: number;
  // Population (colony) parameters.
  initial_cells: number;
  medium_glucose: number;
  medium_volume_l: number;
  feed_rate: number;
  max_cells: number;
  // Digital Petri Dish parameters.
  grid_width: number;
  grid_height: number;
  nutrient_init: number;
  nutrient_pattern: NutrientPattern;
  petri_diffusion: number;
}

// Compact cell sample carried by a Petri dish frame (parallel arrays).
export interface PetriCells {
  x: number[];
  y: number[];
  clone: number[];
  energy: number[];
  mut: number[];
  count: number;
  cap: number;
}

// Petri dish snapshot: stats + heat maps + a capped cell sample.
export interface PetriSummary {
  step: number;
  alive: number;
  dead: number;
  born: number;
  died: number;
  colonies: number;
  n_clones: number;
  dominant_clone: number;
  dominant_fraction: number;
  generations: number;
  occupancy: number;
  total_nutrient: number;
  mean_genotype: Record<string, number>;
  grid: [number, number]; // [height, width]
  hm_size: [number, number]; // [rows, cols]
  heatmaps: { population: number[]; nutrient: number[]; mutation: number[]; atp: number[] };
  clone_map: number[]; // dominant clone id per coarse cell (-1 = empty)
  cells: PetriCells;
}

export type HeatmapMetric = "clone" | "population" | "nutrient" | "mutation" | "atp";

// One cell in a colony snapshot.
export interface PopulationCell {
  id: number;
  lineage: string;
  root: string;
  generation: number;
  mass: number;
  alive: boolean;
}

// Population-level summary carried by a "population" scenario frame.
export interface PopulationSummary {
  step: number;
  size: number;
  alive: number;
  dead: number;
  total_ever: number;
  born: number;
  died: number;
  generations: number;
  medium_glucose: number;
  dominant_lineage: string | null;
  dominant_fraction: number;
  lineages: number;
  mean_genotype: Record<string, number>;
  total_biomass: number;
  cells: PopulationCell[];
}

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  owner_id: number;
  created_at: string;
}

export interface Design {
  id: number;
  project_id: number;
  name: string;
  config: DesignConfig;
}

export type SimulationStatus =
  | "CREATED"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "STOPPED"
  | "DONE"
  | "FAILED";

export interface Simulation {
  id: number;
  project_id: number;
  design_id: number;
  status: SimulationStatus;
  current_step: number;
  outcome: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

// Compact per-step frame emitted by the engine adapter.
export interface FrameData {
  mass: number;
  alive: boolean;
  status: string | null;
  metabolism_status: string | null;
  divisions: number;
  generation: number;
  lineage: string | null;
  env_glucose: number;
  pool_glucose: number;
  membrane_integrity: number;
  genotype?: Record<string, number>;
  limiting?: string | null;
  nutrients?: Record<string, { pool: number; surface: number }>;
  field_glc?: number[];
  compartments?: Record<string, { energy: number; stressed: boolean }>;
  signalling?: {
    mode: string | null;
    survival: boolean;
    signals: { starvation: number; growth: number; membrane_stress: number };
  };
  // DNA replication state — present in all scenarios (defaults when idle).
  replication?: { progress: number; replicating: boolean; complete: boolean };
  // Phenotype scaling factors (1.0 = baseline) for transport/membrane/etc.
  phenotype?: Record<string, number>;
  // Aggregate gene-expression molecule counts (drive ribosome/transcription visuals).
  expression?: { mrna: number; protein: number };
  // Active drugs (Drug Interaction Studio) — drives drug-molecule visualisation.
  drugs?: ActiveDrug[];
  // Present only for the "population" (colony) scenario.
  population?: PopulationSummary;
  // Present only for the "petri" (Digital Petri Dish) scenario.
  petri?: PetriSummary;
}

export interface Frame {
  step: number;
  time: number;
  data: FrameData;
}

export interface SimEvent {
  step: number;
  time: number;
  type: string;
  data: Record<string, unknown>;
}

// Experiment Lab.
export interface SweepAxis {
  param: string;
  values: (number | string)[];
}

export interface RunMetrics {
  outcome: string | null;
  final_step: number;
  survival_time: number;
  divisions: number;
  peak_population: number;
  dominant_clone: string | null;
  extinction_time: number | null;
  biomass_peak: number;
  nutrient_depletion: number;
}

export interface ExperimentRun {
  idx: number;
  label: string;
  config: DesignConfig;
  status: SimulationStatus;
  metrics: RunMetrics | null;
  series: { t: number[]; population: number[]; nutrient: number[] } | null;
  heatmaps: {
    hm_size: [number, number];
    grid: [number, number];
    heatmaps: { population: number[]; nutrient: number[]; mutation: number[]; atp: number[] };
    clone_map: number[];
  } | null;
  error: string | null;
}

export interface Experiment {
  id: number;
  project_id: number;
  name: string;
  description: string;
  base_config: DesignConfig;
  sweep: SweepAxis[];
  status: SimulationStatus;
  n_runs: number;
  error: string | null;
}

export interface ExperimentResults {
  experiment: Experiment;
  runs: ExperimentRun[];
}

export interface ExperimentInterpretation {
  answer: string;
  grounding: string;
}

export interface SweepProposal {
  name: string;
  base_config: DesignConfig;
  sweep: SweepAxis[];
  n_runs: number;
  rationale: string;
}

export interface SweepProposalResponse {
  proposal: SweepProposal;
  grounding: string;
}

// AI copilot.
export interface DesignProposal {
  config: DesignConfig;
  rationale: string;
}

export interface Interpretation {
  answer: string;
  grounding: string;
}

// AI Research Scientist.
export type Confidence = "high" | "medium" | "low";

export interface Objective {
  key: string;
  label: string;
  metric: string;
  direction: "max" | "min";
  note: string;
}

export interface ExperimentBrief {
  id: number;
  name: string;
  status: SimulationStatus;
  n_runs: number;
}

export interface Study {
  id: number;
  project_id: number;
  goal: string;
  objective: Objective;
  scenario: string;
  status: SimulationStatus;
  plan: {
    rationale?: string;
    expected_outcome?: string;
    n_experiments?: number;
    experiments?: { name: string; sweep: SweepAxis[]; hypothesis?: string }[];
  };
  error: string | null;
  experiments: ExperimentBrief[];
}

export interface Evidence {
  experiment_id: number | null;
  run_labels: string[];
  n: number;
  confidence: Confidence;
  detail: string;
}

export interface Relationship {
  source: string;
  target: string;
  kind: "increases" | "decreases" | "saturates" | "detrimental_above" | "correlates";
  sign: "+" | "-" | "0";
  strength: number;
  threshold: number | null;
  statement: string;
  evidence: Evidence;
}

export interface Hypothesis {
  text: string;
  confidence: Confidence;
  evidence: Evidence;
}

export interface BestDesign {
  experiment_id: number;
  run_label: string;
  metric: string;
  value: number;
  config_summary: Record<string, number | string>;
  why: string;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: "parameter" | "metric" | "mechanism";
}

export interface GraphEdge {
  source: string;
  target: string;
  sign: "+" | "-" | "0";
  strength: number;
  kind: string;
}

export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface StudyAnalysis {
  study: Study;
  objective: Objective;
  relationships: Relationship[];
  hypotheses: Hypothesis[];
  best_designs: BestDesign[];
  knowledge_graph: KnowledgeGraphData;
  open_questions: string[];
  summary: string;
  n_runs_analysed: number;
}

export interface NotebookSection {
  heading: string;
  body: string;
}

export interface Notebook {
  title: string;
  sections: NotebookSection[];
  markdown: string;
}

export interface Publication {
  title: string;
  abstract: string;
  sections: NotebookSection[];
  markdown: string;
}

// WebSocket stream messages.
export type StreamMessage =
  | { kind: "frame"; step: number; time: number; data: FrameData }
  | { kind: "event"; step: number; time: number; type: string; data: Record<string, unknown> }
  | { kind: "status"; status: SimulationStatus; done: boolean };
