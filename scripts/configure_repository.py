#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

TOKEN = "__APS_REPOSITORY__"
FILES = ("install.sh", "install.ps1", "README.md", "QUICKSTART_中文.txt")

def main() -> int:
    ap = argparse.ArgumentParser(description="Bind APS distribution files to a GitHub owner/repo.")
    ap.add_argument("repository", help="GitHub repository in owner/repo form")
    args = ap.parse_args()
    repo = args.repository.strip().strip("/")
    if repo.count("/") != 1 or any(not part for part in repo.split("/")):
        ap.error("repository must be owner/repo")
    root = Path(__file__).resolve().parents[1]
    changed = 0
    for rel in FILES:
        p = root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if TOKEN in text:
            p.write_text(text.replace(TOKEN, repo), encoding="utf-8")
            changed += 1
    print(f"Configured {changed} file(s) for {repo}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
