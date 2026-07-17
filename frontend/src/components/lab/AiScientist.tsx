// The AI Scientist panel inside the Experiment Lab: ask grounded questions about the
// sweep (streaming), and generate a *validated* next-experiment proposal that can be
// created with one click. Everything is grounded in the experiment's measured runs.

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { experimentsApi } from "../../api/endpoints";
import type { SweepProposal } from "../../api/types";

const PRESETS: { label: string; question: string }[] = [
  { label: "Which was best?", question: "Which design performed best and why? Cite runs by #id." },
  { label: "Generate hypotheses", question: "Generate 2-3 testable hypotheses supported only by these results, citing runs and metrics." },
  { label: "Explain the trend", question: "Compare the runs and describe the trend across the swept parameter(s), citing run ids." },
];

interface AiScientistProps {
  experimentId: number;
  projectId: number;
  ready: boolean; // at least one run has completed
}

export function AiScientist({ experimentId, projectId, ready }: AiScientistProps) {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<SweepProposal | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true);
    setAnswer("");
    setError(null);
    try {
      await experimentsApi.interpretStream(experimentId, q, setAnswer);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateNext() {
    setSuggesting(true);
    setProposal(null);
    setError(null);
    try {
      const res = await experimentsApi.suggest(experimentId);
      setProposal(res.proposal);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSuggesting(false);
    }
  }

  async function createProposed() {
    if (!proposal) return;
    const exp = await experimentsApi.create(projectId, proposal.name, proposal.base_config, proposal.sweep);
    navigate(`/experiments/${exp.id}`);
  }

  return (
    <div className="copilot ai-scientist">
      <div className="copilot-title">◈ AI Scientist</div>
      <p className="copilot-hint">
        Grounded strictly in this experiment's measured runs — it cites run #ids and refuses claims beyond the data.
      </p>

      <div className="copilot-presets">
        {PRESETS.map((p) => (
          <button key={p.label} className="btn btn-small" onClick={() => ask(p.question)} disabled={busy || !ready}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="copilot-input">
        <input
          placeholder="Ask about these runs…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(question)}
          disabled={!ready}
        />
        <button className="btn btn-primary btn-small" onClick={() => ask(question)} disabled={busy || !ready}>
          {busy ? "Thinking…" : "Ask"}
        </button>
      </div>

      {answer ? <p className="copilot-a">{answer}{busy ? " ▋" : ""}</p> : null}

      <div className="scientist-next">
        <button className="btn btn-small btn-active" onClick={generateNext} disabled={suggesting || !ready}>
          {suggesting ? "Designing…" : "🧭 Generate next experiment"}
        </button>
        {proposal ? (
          <div className="proposal">
            <div className="proposal-head">
              <strong>{proposal.name}</strong>
              <span className="muted"> — {proposal.base_config.scenario}, {proposal.n_runs} runs</span>
            </div>
            <div className="proposal-sweep">
              {proposal.sweep.map((a) => (
                <span key={a.param} className="geno-chip">{a.param}: [{a.values.join(", ")}]</span>
              ))}
            </div>
            <p className="copilot-a">{proposal.rationale}</p>
            <button className="btn btn-primary btn-small" onClick={createProposed}>Create &amp; open →</button>
          </div>
        ) : null}
      </div>

      {error ? <div className="form-error">{error}</div> : null}
    </div>
  );
}
