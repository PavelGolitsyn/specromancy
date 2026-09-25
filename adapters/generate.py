"""Reserved entry point for adapter generation implemented in Stage 07."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from specromancy.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["adapters", "generate"]))
