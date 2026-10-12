"""Where the app writes. Absolute paths only: on SEPAL the CWD is read-only."""

import os
from pathlib import Path

ENV_RESULTS_DIR = "FRA_GRID_RESULTS_DIR"


def results_dir() -> Path:
    """Root holding one folder per generated grid; created on first use.

    ``$FRA_GRID_RESULTS_DIR`` wins (tests, operators); otherwise the SEPAL-wide
    ``~/module_results/<module>`` convention.
    """
    env = os.environ.get(ENV_RESULTS_DIR)
    root = Path(env).expanduser() if env else Path.home() / "module_results" / "fra_grid_generator"
    root = root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    return root
