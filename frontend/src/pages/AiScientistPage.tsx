// The AI Research Scientist dashboard: give a research goal, and the AI autonomously
// designs + runs Experiment-Lab studies, then presents grounded findings — discovered
// relationships, hypotheses (with confidence), a knowledge graph, best designs, open
// questions, a research notebook, and a publication draft. Everything shown is computed
// from measured runs and cites its evidence. Built entirely on the existing APIs.

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { researchApi } from "../api/endpoints";
import type {
  BestDesign,
  Confidence,
  Hypothesis,
  Notebook,
  Publication,
  Relationship,
  Study,
  StudyAnalysis,
} from "../api/types";
import { KnowledgeGraph } from "../components/research/KnowledgeGraph";
import { confidenceMeta, GOAL_PRESETS } from "../components/research/graph";

function ConfidenceBadge({ level }: { level: Confidence }) {
  const m = confidenceMeta(level);
  return (
    <span className="conf-badge" style={{ color: m.color, borderColor: m.color }}>
      {m.label}
    </span>
  );
}

function isTerminal(status: string): boolean {
  return status === "DONE" || status === "FAILED" || status === "STOPPED";
}

export function AiScientistPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [selected, setSelected] = useState<Study | null>(null);
  const [analysis, setAnalysis] = useState<StudyAnalysis | null>(null);
  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [publication, setPublication] = useState<Publication | null>(null);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [narration, setNarration] = useState("");
  const [narrating, setNarrating] = useState(false);
  const [tab, setTab] = useState<"findings" | "notebook" | "publication">("findings");
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    researchApi.list(pid).then(setStudies).catch((e) => setError(String(e)));
  }, [pid]);

  const loadAnalysis = useCallback((id: number) => {
    researchApi.analysis(id).then(setAnalysis).catch(() => setAnalysis(null));
  }, []);

  const openStudy = useCallback(
    (s: Study) => {
      setSelected(s);
      setAnalysis(null);
      setNotebook(null);
      setPublication(null);
      setNarration("");
      setTab("findings");
      loadAnalysis(s.id);
    },
    [loadAnalysis],
  );

  // Poll the selected study while it is still running; refresh analysis as runs land.
  useEffect(() => {
    if (!selected || isTerminal(selected.status)) return;
    pollRef.current = window.setInterval(async () => {
      try {
        const fresh = await researchApi.get(selected.id);
        setSelected(fresh);
        setStudies((list) => list.map((s) => (s.id === fresh.id ? fresh : s)));
        loadAnalysis(fresh.id);
        if (isTerminal(fresh.status) && pollRef.current) {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [selected, loadAnalysis]);

  async function launch(goalText: string) {
    if (!goalText.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const study = await researchApi.create(pid, goalText.trim());
      setStudies((s) => [study, ...s]);
      setGoal("");
      openStudy(study);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadNotebook() {
    if (!selected) return;
    setTab("notebook");
    if (!notebook) researchApi.notebook(selected.id).then(setNotebook).catch((e) => setError(String(e)));
  }

  async function loadPublication() {
    if (!selected) return;
    setTab("publication");
    if (!publication) researchApi.publication(selected.id).then(setPublication).catch((e) => setError(String(e)));
  }

  async function narrate() {
    if (!selected || narrating) return;
    setNarrating(true);
    setNarration("");
    try {
      await researchApi.interpretStream(selected.id, "Summarise what this study discovered and why, citing evidence.", setNarration);
    } catch (e) {
      setNarration("");
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setNarrating(false);
    }
  }

  return (
    <div className="page scientist-page">
      <div className="sim-header">
        <button className="btn btn-small" onClick={() => navigate(`/projects/${pid}`)}>← Project</button>
        <button className="btn btn-small btn-active" onClick={() => navigate(`/projects/${pid}/lab`)}>🧪 Experiment Lab</button>
      </div>
      <h1>🔬 AI Research Scientist</h1>
      <p className="muted">
        State a research goal in plain language. The AI designs experiments, runs them autonomously in the
        Experiment Lab, and reports grounded findings — every statement is computed from measured runs and cites its evidence.
      </p>

      <div className="scientist-launch">
        <div className="inline-form">
          <input
            placeholder="e.g. I want the cell to survive longer under starvation…"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && launch(goal)}
          />
          <button className="btn btn-primary" onClick={() => launch(goal)} disabled={busy}>
            {busy ? "Designing…" : "Start study"}
          </button>
        </div>
        <div className="copilot-presets">
          {GOAL_PRESETS.map((p) => (
            <button key={p.label} className="btn btn-small" onClick={() => launch(p.goal)} disabled={busy}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {error ? <div className="form-error">{error}</div> : null}

      <div className="scientist-grid">
        <aside className="study-list">
          <h2>Studies</h2>
          <ul className="card-list">
            {studies.map((s) => (
              <li
                key={s.id}
                className={`card study-item ${selected?.id === s.id ? "study-item-sel" : ""}`}
                onClick={() => openStudy(s)}
              >
                <div>
                  <strong>{s.objective.label}</strong>
                  <div className="muted study-goal">{s.goal}</div>
                </div>
                <span className={`status-badge status-${s.status.toLowerCase()}`}>{s.status}</span>
              </li>
            ))}
            {studies.length === 0 ? <li className="muted">No studies yet — start one above.</li> : null}
          </ul>
        </aside>

        <section className="study-detail">
          {!selected ? (
            <p className="muted">Select or start a study to see the AI's findings.</p>
          ) : (
            <>
              <div className="study-tabs">
                <button className={`btn btn-small ${tab === "findings" ? "btn-active" : ""}`} onClick={() => setTab("findings")}>Findings</button>
                <button className={`btn btn-small ${tab === "notebook" ? "btn-active" : ""}`} onClick={loadNotebook}>📓 Notebook</button>
                <button className={`btn btn-small ${tab === "publication" ? "btn-active" : ""}`} onClick={loadPublication}>📄 Publication</button>
              </div>

              {tab === "findings" ? (
                <FindingsView
                  study={selected}
                  analysis={analysis}
                  narration={narration}
                  narrating={narrating}
                  onNarrate={narrate}
                />
              ) : null}
              {tab === "notebook" ? <DocView doc={notebook} onExport={(f) => researchApi.export(selected.id, "notebook", f)} /> : null}
              {tab === "publication" ? (
                <DocView doc={publication} abstract={publication?.abstract} onExport={(f) => researchApi.export(selected.id, "publication", f)} />
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="research-section">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function FindingsView({
  study, analysis, narration, narrating, onNarrate,
}: {
  study: Study;
  analysis: StudyAnalysis | null;
  narration: string;
  narrating: boolean;
  onNarrate: () => void;
}) {
  const running = !isTerminal(study.status);
  return (
    <div className="findings">
      <Section title="Current Question">
        <p className="research-goal">“{study.goal}”</p>
        <p className="muted">
          Objective: <strong>{study.objective.direction === "max" ? "maximise" : "minimise"} {study.objective.metric}</strong>
          {study.objective.note ? <span className="proxy-note"> — {study.objective.note}</span> : null}
        </p>
        {study.plan?.rationale ? <p className="copilot-a">{study.plan.rationale}</p> : null}
      </Section>

      <Section title="Running Experiments">
        <ul className="exp-status-list">
          {study.experiments.map((e) => (
            <li key={e.id}>
              <span className={`status-badge status-${e.status.toLowerCase()}`}>{e.status}</span>
              <span className="exp-name">#{e.id} {e.name}</span>
              <span className="muted"> · {e.n_runs} runs</span>
            </li>
          ))}
        </ul>
        {running ? <p className="muted">⏳ Study running — findings update as runs complete.</p> : null}
      </Section>

      {analysis ? (
        <>
          <Section title="Summary">
            <p className="copilot-a">{analysis.summary}</p>
            <p className="muted">Grounded in {analysis.n_runs_analysed} completed runs.</p>
          </Section>

          <Section title="Discovered Relationships">
            <RelationshipList rels={analysis.relationships} />
          </Section>

          <Section title="Knowledge Graph">
            <KnowledgeGraph data={analysis.knowledge_graph} />
          </Section>

          <Section title="Hypotheses">
            <HypothesisList hyps={analysis.hypotheses} />
          </Section>

          <Section title="Best Designs">
            <BestDesignList designs={analysis.best_designs} />
          </Section>

          <Section title="Open Questions">
            <ul className="q-list">
              {analysis.open_questions.map((q, i) => <li key={i}>{q}</li>)}
            </ul>
          </Section>

          <Section title="AI Narration">
            <button className="btn btn-small btn-active" onClick={onNarrate} disabled={narrating}>
              {narrating ? "Narrating…" : "◈ Narrate findings"}
            </button>
            {narration ? <p className="copilot-a">{narration}{narrating ? " ▋" : ""}</p> : null}
          </Section>
        </>
      ) : (
        <p className="muted">Computing analysis…</p>
      )}
    </div>
  );
}

function RelationshipList({ rels }: { rels: Relationship[] }) {
  if (rels.length === 0) return <p className="muted">No relationship met the evidence threshold yet.</p>;
  return (
    <ul className="rel-list">
      {rels.map((r, i) => (
        <li key={i} className="rel-item">
          <span className={`rel-tag rel-${r.kind}`}>{r.kind.replace("_", " ")}</span>
          <span className="rel-text">{r.statement}</span>
          <span className="rel-ev">
            <ConfidenceBadge level={r.evidence.confidence} />
            <span className="muted"> n={r.evidence.n}{r.evidence.experiment_id ? ` · exp #${r.evidence.experiment_id}` : ""}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function HypothesisList({ hyps }: { hyps: Hypothesis[] }) {
  if (hyps.length === 0) return <p className="muted">No hypotheses could be grounded yet.</p>;
  return (
    <ol className="hyp-list">
      {hyps.map((h, i) => (
        <li key={i}>
          <span className="hyp-text">{h.text}</span>
          <span className="hyp-ev"><ConfidenceBadge level={h.confidence} /> <span className="muted">n={h.evidence.n}</span></span>
        </li>
      ))}
    </ol>
  );
}

function BestDesignList({ designs }: { designs: BestDesign[] }) {
  if (designs.length === 0) return <p className="muted">No completed runs to rank.</p>;
  return (
    <ul className="best-list">
      {designs.map((b, i) => (
        <li key={i} className="best-item">
          <div>
            <strong>{b.run_label}</strong> <span className="muted">exp #{b.experiment_id}</span>
            <div className="best-metric">{b.metric} = {b.value}</div>
          </div>
          <div className="best-why muted">{b.why}</div>
        </li>
      ))}
    </ul>
  );
}

function DocView({
  doc, abstract, onExport,
}: {
  doc: Notebook | Publication | null;
  abstract?: string;
  onExport: (format: "md" | "json") => void;
}) {
  if (!doc) return <p className="muted">Loading…</p>;
  return (
    <div className="doc-view">
      <div className="doc-toolbar">
        <h2>{doc.title}</h2>
        <div className="doc-actions">
          <button className="btn btn-small" onClick={() => onExport("md")}>⬇ Markdown</button>
          <button className="btn btn-small" onClick={() => onExport("json")}>⬇ JSON</button>
        </div>
      </div>
      {abstract ? <p className="doc-abstract">{abstract}</p> : null}
      {doc.sections.map((s) => (
        <div key={s.heading} className="doc-section">
          <h3>{s.heading}</h3>
          <pre className="doc-body">{s.body}</pre>
        </div>
      ))}
    </div>
  );
}
