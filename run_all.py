"""
One-command demo: starts the backend, runs the client, then stops the backend.

    python run_all.py                       # translate the bundled Sinhala speech sample to Tamil
    python run_all.py --text "வணக்கம்" --source Tamil --target Sinhala

Accepts every option of cli.py (see: python cli.py --help).
"""

import sys

from cli import main

if __name__ == "__main__":
    sys.exit(main(["--run-backend", *sys.argv[1:]]))
