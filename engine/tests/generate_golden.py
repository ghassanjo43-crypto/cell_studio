"""Regenerate the golden trajectory fixture.

Run intentionally (only when the dynamics are *meant* to change)::

    python -m tests.generate_golden      # from the engine/ directory

This writes ``tests/golden/toy_trajectory.json`` from the canonical config in
``tests.test_golden_trajectory`` so the fixture and the test can never diverge.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.test_golden_trajectory import (
    CONFIG,
    DT,
    N_STEPS,
    SEED,
    VARIABLE,
    _run_and_record,
)


def main() -> None:
    trajectory = _run_and_record(N_STEPS)
    out = Path(__file__).parent / "golden" / "toy_trajectory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "seed": SEED,
                "dt": DT,
                "n_steps": N_STEPS,
                "config": CONFIG,
                "variable": VARIABLE,
                "trajectory": trajectory,
            },
            indent=2,
        ),
        "utf-8",
    )
    print(f"wrote {out} ({len(trajectory)} points)")


if __name__ == "__main__":
    main()
