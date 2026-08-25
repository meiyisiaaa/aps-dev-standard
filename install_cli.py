#!/usr/bin/env python3
"""Offline installer for the `aps` command. No pip or third-party dependencies."""
from __future__ import annotations

import argparse
import os
import shutil
import site
import sys
from pathlib import Path

VERSION = "1.0.0"


def default_prefix() -> Path:
    if os.name == "nt":
        return Path(site.USER_BASE)
    return Path.home() / ".local"


def main() -> int:
    ap = argparse.ArgumentParser(description="Install APS CLI without pip")
    ap.add_argument("--prefix", type=Path, default=default_prefix(), help="installation prefix")
    args = ap.parse_args()

    src_root = Path(__file__).resolve().parent
    prefix = args.prefix.expanduser().resolve()
    app_root = prefix / ("share" if os.name != "nt" else "share") / "aps-cli"
    version_root = app_root / VERSION
    current_root = app_root / "current"
    bin_dir = prefix / ("Scripts" if os.name == "nt" else "bin")

    if version_root.exists():
        shutil.rmtree(version_root)
    version_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_root / "aps.py", version_root / "aps.py")
    shutil.copytree(src_root / "src" / "aps_cli", version_root / "src" / "aps_cli")
    shutil.copy2(src_root / "VERSION", version_root / "VERSION")

    if current_root.exists() or current_root.is_symlink():
        if current_root.is_dir() and not current_root.is_symlink():
            shutil.rmtree(current_root)
        else:
            current_root.unlink()
    # Copy instead of symlink for Windows and restricted environments.
    shutil.copytree(version_root, current_root)

    bin_dir.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).resolve()
    if os.name == "nt":
        launcher = bin_dir / "aps.cmd"
        launcher.write_text(
            f'@echo off\r\n"{python}" "{current_root / "aps.py"}" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / "aps"
        launcher.write_text(
            f'#!/bin/sh\nexec "{python}" "{current_root / "aps.py"}" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)

    print(f"Installed APS CLI {VERSION}")
    print(f"Launcher: {launcher}")
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(bin_dir) not in path_parts:
        print("\nPATH note:")
        if os.name == "nt":
            print(f"Add this directory to PATH: {bin_dir}")
            print(f"Until then run: {launcher}")
        else:
            print(f'Add this to your shell profile: export PATH="{bin_dir}:$PATH"')
            print(f"Until then run: {launcher}")
    else:
        print("\nRun: aps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
