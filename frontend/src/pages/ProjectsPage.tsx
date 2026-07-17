import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { projectsApi } from "../api/endpoints";
import type { Project } from "../api/types";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list().then(setProjects).catch((e) => setError(String(e)));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const project = await projectsApi.create(name.trim());
    setProjects((p) => [...p, project]);
    setName("");
  }

  return (
    <div className="page">
      <h1>Projects</h1>
      <form className="inline-form" onSubmit={create}>
        <input placeholder="New project name" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn btn-primary" type="submit">
          Create
        </button>
      </form>
      {error ? <div className="form-error">{error}</div> : null}
      <ul className="card-list">
        {projects.map((p) => (
          <li key={p.id} className="card">
            <Link to={`/projects/${p.id}`} className="card-link">
              <strong>{p.name}</strong>
              {p.description ? <span className="muted"> — {p.description}</span> : null}
            </Link>
          </li>
        ))}
        {projects.length === 0 ? <li className="muted">No projects yet — create one above.</li> : null}
      </ul>
    </div>
  );
}
