"""CLI entry point for running the Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as stcli


def main() -> int:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    sys.argv = ["streamlit", "run", str(app_path)]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
