"""Recovery2 launcher for a fresh, separate Poolside Laguna P4 cohort.

It uses the previously frozen P4 inputs, but binds formal execution to a new
release receipt and a new output directory. The imported fail-closed runner
still enforces the approval, zero-spend, local-DVWA, and database-reset gates.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import run_poolside_laguna_p4_recovery1 as runner


# Keep the exact frozen P4 design while isolating this fresh cohort's release,
# execution approval, and raw result directory from recovery1.
runner.RELEASE_PATH = ROOT / "docs/evidence/poolside-laguna-p4-release-manifest-recovery2-2026-10-23.json"
runner.EXECUTION_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-execution-approval-recovery2-2026-10-23.json"
runner.FORMAL_OUTPUT = ROOT / "results/raw/formal/poolside-laguna-p4-recovery2-20261023"


if __name__ == "__main__":
    raise SystemExit(runner.main())
