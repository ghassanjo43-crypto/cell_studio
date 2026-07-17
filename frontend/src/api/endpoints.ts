// Typed endpoint functions grouped by resource.

import { apiGet, apiLoginForm, apiSend, downloadFile, setToken, streamSSE } from "./client";
import type {
  Design,
  DesignConfig,
  DesignProposal,
  Experiment,
  ExperimentInterpretation,
  ExperimentResults,
  Frame,
  Interpretation,
  Notebook,
  Project,
  Publication,
  SimEvent,
  Simulation,
  Study,
  StudyAnalysis,
  SweepAxis,
  SweepProposalResponse,
  User,
} from "./types";

export const authApi = {
  async register(email: string, password: string): Promise<User> {
    return apiSend<User>("/auth/register", "POST", { email, password });
  },
  async login(email: string, password: string): Promise<string> {
    const { access_token } = await apiLoginForm("/auth/token", email, password);
    setToken(access_token);
    return access_token;
  },
  me(): Promise<User> {
    return apiGet<User>("/auth/me");
  },
  logout(): void {
    setToken(null);
  },
};

export const projectsApi = {
  list(): Promise<Project[]> {
    return apiGet<Project[]>("/projects");
  },
  create(name: string, description = ""): Promise<Project> {
    return apiSend<Project>("/projects", "POST", { name, description });
  },
};

export const designsApi = {
  list(projectId: number): Promise<Design[]> {
    return apiGet<Design[]>(`/projects/${projectId}/designs`);
  },
  create(projectId: number, name: string, config: Partial<DesignConfig>): Promise<Design> {
    return apiSend<Design>(`/projects/${projectId}/designs`, "POST", { name, config });
  },
};

export const simulationsApi = {
  create(designId: number): Promise<Simulation> {
    return apiSend<Simulation>("/simulations", "POST", { design_id: designId });
  },
  get(id: number): Promise<Simulation> {
    return apiGet<Simulation>(`/simulations/${id}`);
  },
  start(id: number): Promise<Simulation> {
    return apiSend<Simulation>(`/simulations/${id}/start`, "POST");
  },
  pause(id: number): Promise<Simulation> {
    return apiSend<Simulation>(`/simulations/${id}/pause`, "POST");
  },
  resume(id: number): Promise<Simulation> {
    return apiSend<Simulation>(`/simulations/${id}/resume`, "POST");
  },
  stop(id: number): Promise<Simulation> {
    return apiSend<Simulation>(`/simulations/${id}/stop`, "POST");
  },
  frames(id: number, sinceStep = -1): Promise<Frame[]> {
    return apiGet<Frame[]>(`/simulations/${id}/frames?since_step=${sinceStep}`);
  },
  events(id: number, sinceStep = -1): Promise<SimEvent[]> {
    return apiGet<SimEvent[]>(`/simulations/${id}/events?since_step=${sinceStep}`);
  },
};

export const experimentsApi = {
  list(projectId: number): Promise<Experiment[]> {
    return apiGet<Experiment[]>(`/projects/${projectId}/experiments`);
  },
  create(
    projectId: number,
    name: string,
    baseConfig: Partial<DesignConfig>,
    sweep: SweepAxis[],
    description = "",
  ): Promise<Experiment> {
    return apiSend<Experiment>(`/projects/${projectId}/experiments`, "POST", {
      name,
      description,
      base_config: baseConfig,
      sweep,
    });
  },
  get(id: number): Promise<Experiment> {
    return apiGet<Experiment>(`/experiments/${id}`);
  },
  run(id: number): Promise<Experiment> {
    return apiSend<Experiment>(`/experiments/${id}/run`, "POST");
  },
  results(id: number): Promise<ExperimentResults> {
    return apiGet<ExperimentResults>(`/experiments/${id}/results`);
  },
  interpret(id: number, question: string): Promise<ExperimentInterpretation> {
    return apiSend<ExperimentInterpretation>(`/experiments/${id}/interpret`, "POST", { question });
  },
  interpretStream(id: number, question: string, onDelta: (text: string) => void): Promise<string> {
    return streamSSE(`/experiments/${id}/interpret/stream`, { question }, onDelta);
  },
  suggest(id: number): Promise<SweepProposalResponse> {
    return apiSend<SweepProposalResponse>(`/experiments/${id}/suggest`, "POST");
  },
  export(id: number, format: "csv" | "json"): Promise<void> {
    return downloadFile(`/experiments/${id}/export?format=${format}`, `experiment_${id}.${format}`);
  },
};

export const researchApi = {
  list(projectId: number): Promise<Study[]> {
    return apiGet<Study[]>(`/projects/${projectId}/studies`);
  },
  create(projectId: number, goal: string, scenario?: string, maxSteps?: number): Promise<Study> {
    return apiSend<Study>(`/projects/${projectId}/studies`, "POST", {
      goal,
      scenario: scenario ?? null,
      max_steps: maxSteps ?? null,
    });
  },
  get(id: number): Promise<Study> {
    return apiGet<Study>(`/studies/${id}`);
  },
  analysis(id: number): Promise<StudyAnalysis> {
    return apiGet<StudyAnalysis>(`/studies/${id}/analysis`);
  },
  notebook(id: number): Promise<Notebook> {
    return apiGet<Notebook>(`/studies/${id}/notebook`);
  },
  publication(id: number): Promise<Publication> {
    return apiGet<Publication>(`/studies/${id}/publication`);
  },
  interpretStream(id: number, question: string, onDelta: (text: string) => void): Promise<string> {
    return streamSSE(`/studies/${id}/interpret/stream`, { question }, onDelta);
  },
  export(id: number, kind: "notebook" | "publication", format: "md" | "json"): Promise<void> {
    const ext = format === "md" ? "md" : "json";
    return downloadFile(`/studies/${id}/export?kind=${kind}&format=${format}`, `study_${id}_${kind}.${ext}`);
  },
};

export const aiApi = {
  design(prompt: string): Promise<DesignProposal> {
    return apiSend<DesignProposal>("/ai/design", "POST", { prompt });
  },
  interpret(simId: number, question: string): Promise<Interpretation> {
    return apiSend<Interpretation>(`/ai/simulations/${simId}/interpret`, "POST", { question });
  },
  interpretStream(simId: number, question: string, onDelta: (text: string) => void): Promise<string> {
    return streamSSE(`/ai/simulations/${simId}/interpret/stream`, { question }, onDelta);
  },
  narrate(simId: number): Promise<Interpretation> {
    return apiSend<Interpretation>(`/ai/simulations/${simId}/narrate`, "POST");
  },
};
