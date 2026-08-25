#!/usr/bin/env python3
"""Portable launcher: `python aps.py ...` without installing the CLI."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from aps_cli.cli import main
raise SystemExit(main())
