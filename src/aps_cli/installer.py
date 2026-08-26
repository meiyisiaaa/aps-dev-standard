from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


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


def copy_file_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
        shutil.copy2(src, temporary)
        os.replace(temporary, dst)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


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
    atomic_write(path, new.encode("utf-8"))
    return action


def validate_bundle(bundle: Path) -> tuple[str, dict[str, str]]:
    """Validate the embedded Standard and return its version and install mapping."""
    payload = bundle / "package"
    manifest_src = load_json(bundle / "package-manifest.json")
    version = manifest_src.get("version")
    if not payload.is_dir() or not isinstance(version, str) or not version:
        raise RuntimeError("installer payload/manifest missing or version-mismatched")
    payload_hashes = manifest_src.get("payload_sha256", {})
    if not isinstance(payload_hashes, dict) or not payload_hashes:
        raise RuntimeError("package manifest has no payload checksums")
    for rel, expected in payload_hashes.items():
        relative = Path(rel)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"package manifest contains unsafe path: {rel}")
        src = payload / rel
        if not src.is_file() or sha256(src) != expected:
            raise RuntimeError(f"package integrity check failed: {rel}")

    managed_files = manifest_src.get("managed_files")
    if not isinstance(managed_files, list) or not managed_files:
        raise RuntimeError("package manifest has no managed files")
    mapping: dict[str, str] = {}
    for dst_rel in managed_files:
        if not isinstance(dst_rel, str) or not dst_rel.startswith(".ai/"):
            raise RuntimeError(f"package manifest contains unsafe managed path: {dst_rel}")
        src_rel = dst_rel.removeprefix(".ai/")
        source_path = Path(src_rel)
        if (
            source_path.is_absolute()
            or ".." in source_path.parts
            or not src_rel
            or src_rel in mapping
            or src_rel not in payload_hashes
        ):
            raise RuntimeError(f"package manifest managed file is not covered: {dst_rel}")
        mapping[src_rel] = dst_rel
    return version, mapping


@contextmanager
def install_lock(root: Path):
    lock_path = root / ".ai" / ".install.lock"
    if lock_path.is_symlink():
        raise RuntimeError("installation lock path must not be a symlink")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            raise RuntimeError("another APS installation is in progress") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def install_standard(bundle: Path, root: Path, host: str = "codex", force_managed: bool = False, quiet: bool = False) -> dict:
    """Install/upgrade the embedded Standard into root without creating runtime project facts."""
    version, mapping = validate_bundle(bundle)
    payload = bundle / "package"

    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"project path is not a directory: {root}")

    with install_lock(root):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        old_manifest_path = root / ".ai" / "standard-manifest.json"
        old_manifest = load_json(old_manifest_path)
        old_hashes = old_manifest.get("installed_files", {}) if isinstance(old_manifest.get("installed_files", {}), dict) else {}

        dirs = [
            ".ai/standards", ".ai/bootstrap", ".ai/tools", ".ai/schemas", ".ai/templates",
            ".ai/runtime/hosts", ".ai/cycles", ".ai/archive", ".agents/skills",
        ]
        for rel in dirs:
            (root / rel).mkdir(parents=True, exist_ok=True)

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
                copy_file_atomic(src, dst)
                if dst_rel.endswith(".py"):
                    dst.chmod(dst.stat().st_mode | 0o111)
                installed_hashes[dst_rel] = src_hash
                changed += 1
            else:
                incoming_rel = Path(dst_rel)
                if incoming_rel.parts and incoming_rel.parts[0] == ".ai":
                    incoming_rel = Path(*incoming_rel.parts[1:])
                incoming_dst = root / ".ai" / "incoming" / version / incoming_rel
                copy_file_atomic(src, incoming_dst)
                installed_hashes[dst_rel] = src_hash
                incoming.append(dst_rel)

        agents_block = (payload / "templates" / "AGENTS.block.md").read_text(encoding="utf-8")
        update_marked_block(root / "AGENTS.md", BEGIN_AGENTS, END_AGENTS, agents_block, root, stamp)

        ignore_body = (payload / "gitignore.fragment").read_text(encoding="utf-8").strip()
        ignore_block = f"{BEGIN_GITIGNORE}\n{ignore_body}\n{END_GITIGNORE}"
        update_marked_block(root / ".gitignore", BEGIN_GITIGNORE, END_GITIGNORE, ignore_block, root, stamp)

        install_manifest = {
            "name": "ai-project-standard",
            "version": version,
            "layout_version": 1,
            "installed_at": utc_now(),
            "host_hint": host,
            "installed_files": installed_hashes,
            "local_modification_conflicts": incoming,
        }
        write_json(old_manifest_path, install_manifest)
        if not quiet:
            print(f"Installed AI Project Standard {version} in {root}")
            if incoming:
                print(f"WARN: {len(incoming)} locally modified managed file(s) preserved; review .ai/incoming/{version}/")
        return {"changed": changed, "incoming": incoming, "root": str(root), "version": version}
