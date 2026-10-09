"""Entry point for Claude Desktop (which can't set a working directory).

Point Claude Desktop at:  <venv python> <full path>/run_server.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)               # so .env and data/seed.json are found
sys.path.insert(0, str(ROOT))

from summit_ops.server import main  # noqa: E402

if __name__ == "__main__":
    main()
