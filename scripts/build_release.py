#!/usr/bin/env python3
from __future__ import annotations
import hashlib, zipfile
from pathlib import Path

def read_cli_version(root: Path) -> str:
    for line in (root / "VERSION").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "APS_CLI":
            value = value.strip()
            if value:
                return value
    raise SystemExit("APS_CLI version not found in VERSION")

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    version = read_cli_version(root)
    out = root / "dist"
    out.mkdir(exist_ok=True)
    for old in out.glob("APS_CLI_*"):
        if old.is_file(): old.unlink()
    zip_path = out / f"APS_CLI_{version}.zip"
    sha_path = out / f"APS_CLI_{version}.zip.sha256"
    exclude = {".git", "dist", "__pycache__"}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        base = f"APS_CLI_{version}"
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(part in exclude for part in rel.parts):
                continue
            if p.is_file():
                z.write(p, Path(base) / rel)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(zip_path)
    print(sha_path)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
