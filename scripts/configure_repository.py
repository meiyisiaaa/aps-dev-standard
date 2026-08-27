#!/usr/bin/env python3
from __future__ import annotations
import argparse
import re
from pathlib import Path

TOKEN = "__APS_REPOSITORY__"
DEFAULT_REPOSITORY = "meiyisiaaa/aps-dev-standard"
FILES = ("install.sh", "install.ps1", "README.md", "QUICKSTART_中文.txt")

def write_utf8(path: Path, text: str, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def read_utf8(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), newline

def main() -> int:
    ap = argparse.ArgumentParser(description="Bind APS distribution files to a GitHub owner/repo.")
    ap.add_argument("repository", help="GitHub repository in owner/repo form")
    args = ap.parse_args()
    repo = args.repository.strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        ap.error("repository must be owner/repo")
    root = Path(__file__).resolve().parents[1]
    changed = 0
    already_configured = False
    for rel in FILES:
        p = root / rel
        if not p.exists():
            continue
        text, newline = read_utf8(p)
        updated = text.replace(TOKEN, repo).replace(DEFAULT_REPOSITORY, repo)
        if updated != text:
            write_utf8(p, updated, newline)
            changed += 1
        elif repo in text:
            already_configured = True
    if not changed:
        if already_configured:
            print(f"Repository already configured for {repo}")
            return 0
        raise SystemExit(f"No repository placeholder found; {repo} may already be configured.")
    print(f"Configured {changed} file(s) for {repo}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
