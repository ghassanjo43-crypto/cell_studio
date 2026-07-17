"""AI Research Scientist — a grounded, deterministic research engine.

This package turns a research *goal* into an auto-designed set of Experiment Lab
experiments and, once they have run, a **data-grounded** analysis: discovered
parameter→metric relationships, hypotheses with confidence, a knowledge graph, a
research notebook, and a publication draft.

Design principles:

* **Never invent biology.** Every statement is computed from measured
  ``ExperimentRun`` metrics. The LLM (optional) is only used to *narrate* the
  already-computed analysis, never to produce the facts.
* **Pure + testable.** These modules take plain dicts (no DB, no engine, no LLM)
  so the science can be unit-tested deterministically.
* **Extensible.** New objectives / parameters / analysers plug into the registries
  here without touching the orchestration or the UI — the foundation for future
  Drug Discovery / Disease / Digital-Twin modules.
"""

from __future__ import annotations
