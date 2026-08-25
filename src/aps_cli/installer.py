from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
BEGIN_AGENTS = "<!-- AI-PROJECT-STANDARD:BEGIN -->"
END_AGENTS = "<!-- AI-PROJECT-STANDARD:END -->"
BEGIN_GITIGNORE = "# >>> AI PROJECT STANDARD >>>"
END_GITIGNORE = "# <<< AI PROJECT STANDARD <<<"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def backup_file(root: Path, path: Path, stamp: str) -> None:
    if not path.exists():
        return
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    backup_rel = Path(*rel.parts[1:]) if rel.parts and rel.parts[0] == ".ai" else rel
    dst = root / ".ai" / "archive" / "install-backups" / stamp / backup_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def update_marked_block(path: Path, begin: str, end: str, block: str, root: Path, stamp: str) -> str:
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if begin in old and end in old:
        prefix, rest = old.split(begin, 1)
        _, suffix = rest.split(end, 1)
        new = prefix.rstrip() + "\n\n" + block.strip() + "\n" + suffix.lstrip("\n")
        action = "update"
    else:
        sep = "\n\n" if old.strip() else ""
        new = old.rstrip() + sep + block.strip() + "\n"
        action = "append" if old.strip() else "create"
    if new == old:
        return "unchanged"
    if path.exists():
        backup_file(root, path, stamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return action


def install_standard(bundle: Path, root: Path, host: str = "codex", force_managed: bool = False, quiet: bool = False) -> dict:
    """Install/upgrade the embedded Standard into root without creating runtime project facts."""
    payload = bundle / "package"
    manifest_src = load_json(bundle / "package-manifest.json")
    if not payload.is_dir() or manifest_src.get("version") != VERSION:
        raise RuntimeError("installer payload/manifest missing or version-mismatched")
    payload_hashes = manifest_src.get("payload_sha256", {})
    if not isinstance(payload_hashes, dict) or not payload_hashes:
        raise RuntimeError("package manifest has no payload checksums")
    for rel, expected in payload_hashes.items():
        src = payload / rel
        if not src.is_file() or sha256(src) != expected:
            raise RuntimeError(f"package integrity check failed: {rel}")

    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"project path is not a directory: {root}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    old_manifest_path = root / ".ai" / "standard-manifest.json"
    old_manifest = load_json(old_manifest_path)
    old_hashes = old_manifest.get("installed_files", {}) if isinstance(old_manifest.get("installed_files", {}), dict) else {}

    dirs = [
        ".ai/standards", ".ai/bootstrap", ".ai/tools", ".ai/schemas", ".ai/templates",
        ".ai/runtime/hosts", ".ai/cycles", ".ai/archive", ".agents/skills",
    ]
    for rel in dirs:
        (root / rel).mkdir(parents=True, exist_ok=True)

    mapping = {
        "standards/lifecycle.md": ".ai/standards/lifecycle.md",
        "standards/artifact-state.md": ".ai/standards/artifact-state.md",
        "bootstrap/bootstrap-prompt.txt": ".ai/bootstrap/bootstrap-prompt.txt",
        "bootstrap/rebaseline-existing-project.txt": ".ai/bootstrap/rebaseline-existing-project.txt",
        "tools/standards-lint.py": ".ai/tools/standards-lint.py",
        "schemas/state.schema.json": ".ai/schemas/state.schema.json",
        "schemas/registry.schema.json": ".ai/schemas/registry.schema.json",
        "templates/state.yaml": ".ai/templates/state.yaml",
        "templates/registry.yaml": ".ai/templates/registry.yaml",
        "templates/decisions.md": ".ai/templates/decisions.md",
        "templates/runtime-host.yaml": ".ai/templates/runtime-host.yaml",
        "templates/design-system-skill/SKILL.md.template": ".ai/templates/design-system-skill/SKILL.md.template",
        "templates/design-system-skill/evals/README.md": ".ai/templates/design-system-skill/evals/README.md",
        "templates/design-system-skill/references/README.md": ".ai/templates/design-system-skill/references/README.md",
    }

    installed_hashes: dict[str, str] = {}
    incoming: list[str] = []
    changed = 0
    for src_rel, dst_rel in mapping.items():
        src = payload / src_rel
        dst = root / dst_rel
        if not src.is_file():
            raise RuntimeError(f"payload missing: {src_rel}")
        src_hash = sha256(src)
        current_hash = sha256(dst) if dst.is_file() else None
        previous_hash = old_hashes.get(dst_rel)
        if current_hash == src_hash:
            installed_hashes[dst_rel] = src_hash
            continue
        safe_to_replace = (not dst.exists()) or (previous_hash is not None and current_hash == previous_hash)
        if safe_to_replace or force_managed:
            if dst.exists():
                backup_file(root, dst, stamp)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst_rel.endswith(".py"):
                dst.chmod(dst.stat().st_mode | 0o111)
            installed_hashes[dst_rel] = src_hash
            changed += 1
        else:
            incoming_rel = Path(dst_rel)
            if incoming_rel.parts and incoming_rel.parts[0] == ".ai":
                incoming_rel = Path(*incoming_rel.parts[1:])
            incoming_dst = root / ".ai" / "incoming" / VERSION / incoming_rel
            incoming_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, incoming_dst)
            installed_hashes[dst_rel] = src_hash
            incoming.append(dst_rel)

    agents_block = (payload / "templates" / "AGENTS.block.md").read_text(encoding="utf-8")
    update_marked_block(root / "AGENTS.md", BEGIN_AGENTS, END_AGENTS, agents_block, root, stamp)

    ignore_body = (payload / "gitignore.fragment").read_text(encoding="utf-8").strip()
    ignore_block = f"{BEGIN_GITIGNORE}\n{ignore_body}\n{END_GITIGNORE}"
    update_marked_block(root / ".gitignore", BEGIN_GITIGNORE, END_GITIGNORE, ignore_block, root, stamp)

    install_manifest = {
        "name": "ai-project-standard",
        "version": VERSION,
        "layout_version": 1,
        "installed_at": utc_now(),
        "host_hint": host,
        "installed_files": installed_hashes,
        "local_modification_conflicts": incoming,
    }
    write_json(old_manifest_path, install_manifest)
    if not quiet:
        print(f"Installed AI Project Standard {VERSION} in {root}")
        if incoming:
            print(f"WARN: {len(incoming)} locally modified managed file(s) preserved; review .ai/incoming/{VERSION}/")
    return {"changed": changed, "incoming": incoming, "root": str(root), "version": VERSION}
