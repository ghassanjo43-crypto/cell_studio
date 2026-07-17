import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { aiApi, designsApi, simulationsApi } from "../api/endpoints";
import type { Design, DesignConfig, NutrientPattern, ScenarioKind } from "../api/types";

export function ProjectPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const navigate = useNavigate();

  const [designs, setDesigns] = useState<Design[]>([]);
  const [name, setName] = useState("My cell");
  const [scenario, setScenario] = useState<ScenarioKind>("evolution");
  const [glucose, setGlucose] = useState(60);
  const [maxSteps, setMaxSteps] = useState(400);
  const [mutationRate, setMutationRate] = useState(1.0);
  const [initialCells, setInitialCells] = useState(1);
  const [mediumGlucose, setMediumGlucose] = useState(200);
  const [feedRate, setFeedRate] = useState(0);
  const [maxCells, setMaxCells] = useState(200);
  const [gridSize, setGridSize] = useState(80);
  const [nutrientPattern, setNutrientPattern] = useState<NutrientPattern>("gradient");
  const [nutrientInit, setNutrientInit] = useState(1.0);
  const [error, setError] = useState<string | null>(null);

  const [aiPrompt, setAiPrompt] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);

  useEffect(() => {
    designsApi.list(pid).then(setDesigns).catch((e) => setError(String(e)));
  }, [pid]);

  async function designWithAi(e: FormEvent) {
    e.preventDefault();
    if (!aiPrompt.trim()) return;
    setAiBusy(true);
    setAiNote(null);
    setError(null);
    try {
      // NL → validated DesignConfig, then create the design (validated again).
      const { config, rationale } = await aiApi.design(aiPrompt.trim());
      const design = await designsApi.create(pid, `AI: ${aiPrompt.trim().slice(0, 40)}`, config);
      setDesigns((d) => [...d, design]);
      setAiNote(rationale || "Design created.");
      setAiPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI design failed");
    } finally {
      setAiBusy(false);
    }
  }

  async function createDesign(e: FormEvent) {
    e.preventDefault();
    const config: Partial<DesignConfig> = {
      scenario,
      glucose_mmol: glucose,
      max_steps: maxSteps,
      mutation_rate: mutationRate,
      ...(scenario === "population"
        ? {
            initial_cells: initialCells,
            medium_glucose: mediumGlucose,
            feed_rate: feedRate,
            max_cells: maxCells,
          }
        : {}),
      ...(scenario === "petri"
        ? {
            initial_cells: initialCells,
            grid_width: gridSize,
            grid_height: gridSize,
            nutrient_pattern: nutrientPattern,
            nutrient_init: nutrientInit,
            feed_rate: feedRate,
          }
        : {}),
    };
    const design = await designsApi.create(pid, name, config);
    setDesigns((d) => [...d, design]);
  }

  async function runDesign(designId: number) {
    const sim = await simulationsApi.create(designId);
    navigate(`/simulations/${sim.id}`);
  }

  return (
    <div className="page">
      <div className="sim-header">
        <button className="btn btn-small" onClick={() => navigate("/")}>
          ← Projects
        </button>
        <button className="btn btn-small btn-active" onClick={() => navigate(`/projects/${pid}/lab`)}>
          🧪 Experiment Lab
        </button>
        <button className="btn btn-small btn-active" onClick={() => navigate(`/projects/${pid}/scientist`)}>
          🔬 AI Scientist
        </button>
      </div>
      <h1>Cell designs</h1>

      <form className="ai-design" onSubmit={designWithAi}>
        <div className="copilot-title">◈ Design with AI</div>
        <div className="inline-form">
          <input
            placeholder="Describe a cell in words, e.g. 'an evolving cell starved of glucose'"
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={aiBusy}>
            {aiBusy ? "Designing…" : "Generate"}
          </button>
        </div>
        {aiNote ? <div className="muted">{aiNote}</div> : null}
      </form>

      <form className="design-form" onSubmit={createDesign}>
        <div className="field">
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Scenario</label>
          <select value={scenario} onChange={(e) => setScenario(e.target.value as ScenarioKind)}>
            <option value="minimal">minimal (metabolism only)</option>
            <option value="lifecycle">lifecycle (grow → divide → die)</option>
            <option value="evolution">evolution (+ genome & mutation)</option>
            <option value="spatial">spatial (multi-nutrient + diffusion)</option>
            <option value="compartment">compartment (organelles + energy)</option>
            <option value="signalling">signalling (adaptive survival mode)</option>
            <option value="population">population (colony + evolution)</option>
            <option value="petri">petri (digital Petri dish)</option>
          </select>
        </div>
        <div className="field">
          <label>Glucose (mmol)</label>
          <input type="number" value={glucose} onChange={(e) => setGlucose(Number(e.target.value))} />
        </div>
        <div className="field">
          <label>Max steps</label>
          <input type="number" value={maxSteps} onChange={(e) => setMaxSteps(Number(e.target.value))} />
        </div>
        {scenario === "evolution" ? (
          <div className="field">
            <label>Mutation rate</label>
            <input
              type="number"
              step="0.1"
              value={mutationRate}
              onChange={(e) => setMutationRate(Number(e.target.value))}
            />
          </div>
        ) : null}
        {scenario === "population" ? (
          <>
            <div className="field">
              <label>Founder cells</label>
              <input type="number" min={1} value={initialCells} onChange={(e) => setInitialCells(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Medium glucose (mmol)</label>
              <input type="number" value={mediumGlucose} onChange={(e) => setMediumGlucose(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Feed rate (mmol/t)</label>
              <input type="number" step="0.5" value={feedRate} onChange={(e) => setFeedRate(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Max colony size</label>
              <input type="number" value={maxCells} onChange={(e) => setMaxCells(Number(e.target.value))} />
            </div>
          </>
        ) : null}
        {scenario === "petri" ? (
          <>
            <div className="field">
              <label>Founder colonies</label>
              <input type="number" min={1} value={initialCells} onChange={(e) => setInitialCells(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Dish size (grid)</label>
              <input type="number" min={16} max={200} value={gridSize} onChange={(e) => setGridSize(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Nutrient pattern</label>
              <select value={nutrientPattern} onChange={(e) => setNutrientPattern(e.target.value as NutrientPattern)}>
                <option value="gradient">gradient</option>
                <option value="uniform">uniform</option>
                <option value="patches">patches</option>
              </select>
            </div>
            <div className="field">
              <label>Nutrient / site</label>
              <input type="number" step="0.1" value={nutrientInit} onChange={(e) => setNutrientInit(Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Feed rate</label>
              <input type="number" step="0.02" value={feedRate} onChange={(e) => setFeedRate(Number(e.target.value))} />
            </div>
          </>
        ) : null}
        <button className="btn btn-primary" type="submit">
          Add design
        </button>
      </form>

      {error ? <div className="form-error">{error}</div> : null}

      <ul className="card-list">
        {designs.map((d) => (
          <li key={d.id} className="card design-card">
            <div>
              <strong>{d.name}</strong>
              <span className="muted"> — {d.config.scenario}, {d.config.glucose_mmol} mmol, {d.config.max_steps} steps</span>
            </div>
            <button className="btn btn-primary btn-small" onClick={() => runDesign(d.id)}>
              ▶ Run
            </button>
          </li>
        ))}
        {designs.length === 0 ? <li className="muted">No designs yet — add one above.</li> : null}
      </ul>
    </div>
  );
}
