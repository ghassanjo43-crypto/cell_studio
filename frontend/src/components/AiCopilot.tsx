// AI copilot chat panel for a simulation. Grounded Q&A over the run — the backend
// constrains answers to the simulation's own data, so this never invents biology.

import { useState } from "react";
import { aiApi } from "../api/endpoints";

interface AiCopilotProps {
  simId: number;
  disabled?: boolean;
}

interface Turn {
  question: string;
  answer: string;
}

const PRESETS = ["Why did the cell die?", "Why did growth stop?", "Suggest the next experiment"];

export function AiCopilot({ simId, disabled }: AiCopilotProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function appendStreaming(question: string): number {
    let idx = 0;
    setTurns((t) => {
      idx = t.length;
      return [...t, { question, answer: "" }];
    });
    setQuestion("");
    return idx;
  }

  function setAnswerAt(idx: number, answer: string) {
    setTurns((t) => t.map((turn, i) => (i === idx ? { ...turn, answer } : turn)));
  }

  async function ask(q: string) {
    const query = q.trim();
    if (!query || busy) return;
    setBusy(true);
    setError(null);
    const idx = appendStreaming(query);
    try {
      await aiApi.interpretStream(simId, query, (text) => setAnswerAt(idx, text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI request failed");
    } finally {
      setBusy(false);
    }
  }

  async function narrate() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const idx = appendStreaming("Narrate this run");
    try {
      const { answer } = await aiApi.narrate(simId);
      setAnswerAt(idx, answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="copilot">
      <div className="copilot-title">◈ AI copilot</div>
      <div className="copilot-hint">
        Answers stream in and are grounded strictly in this run's data — no invented biology.
      </div>
      <div className="copilot-presets">
        <button className="btn btn-small btn-active" disabled={busy || disabled} onClick={narrate}>
          📖 Narrate run
        </button>
        {PRESETS.map((p) => (
          <button key={p} className="btn btn-small" disabled={busy || disabled} onClick={() => ask(p)}>
            {p}
          </button>
        ))}
      </div>

      <div className="copilot-thread">
        {turns.map((t, i) => (
          <div key={i} className="copilot-turn">
            <div className="copilot-q">{t.question}</div>
            <div className="copilot-a">{t.answer}</div>
          </div>
        ))}
        {turns.length === 0 ? (
          <div className="muted">Ask about this simulation, or use a preset above.</div>
        ) : null}
      </div>

      {error ? <div className="form-error">{error}</div> : null}
      <form
        className="copilot-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input
          placeholder="Ask about this run…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy || disabled}
        />
        <button className="btn btn-primary" type="submit" disabled={busy || disabled}>
          {busy ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
