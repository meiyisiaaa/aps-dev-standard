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


def write_json_if_changed(path: Path, data: dict) -> bool:
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.is_file():
        try:
            if path.read_bytes() == encoded:
                return False
        except OSError:
            pass
    atomic_write(path, encoded)
    return True


def backup_file(root: Path, path: Path) -> None:
    if not path.exists():
        return
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    backup_rel = Path(*rel.parts[1:]) if rel.parts and rel.parts[0] == ".ai" else rel
    content_hash = sha256(path)
    dst = root / ".ai" / "archive" / "install-backups" / content_hash / backup_rel
    if dst.is_file() and sha256(dst) == content_hash:
        return
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


def copy_file_if_changed(src: Path, dst: Path, src_hash: str) -> bool:
    if dst.is_file() and sha256(dst) == src_hash:
        return False
    copy_file_atomic(src, dst)
    return True


def update_marked_block(path: Path, begin: str, end: str, block: str, root: Path) -> str:
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    begin_count = old.count(begin)
    end_count = old.count(end)
    if begin_count != end_count or begin_count > 1:
        raise RuntimeError(f"managed marker block is duplicated or incomplete: {path}")
    if begin_count == 1:
        prefix, rest = old.split(begin, 1)
        _, suffix = rest.split(end, 1)
        prefix = prefix.rstrip()
        suffix = suffix.lstrip("\n")
        separator = "\n\n" if prefix else ""
        new = prefix + separator + block.strip() + "\n" + suffix
        action = "update"
    else:
        sep = "\n\n" if old.strip() else ""
        new = old.rstrip() + sep + block.strip() + "\n"
        action = "append" if old.strip() else "create"
    if new == old:
        return "unchanged"
    if path.exists():
        backup_file(root, path)
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
                    backup_file(root, dst)
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
                copy_file_if_changed(src, incoming_dst, src_hash)
                installed_hashes[dst_rel] = src_hash
                incoming.append(dst_rel)

        agents_block = (payload / "templates" / "AGENTS.block.md").read_text(encoding="utf-8")
        if update_marked_block(root / "AGENTS.md", BEGIN_AGENTS, END_AGENTS, agents_block, root) != "unchanged":
            changed += 1

        ignore_body = (payload / "gitignore.fragment").read_text(encoding="utf-8").strip()
        ignore_block = f"{BEGIN_GITIGNORE}\n{ignore_body}\n{END_GITIGNORE}"
        if update_marked_block(root / ".gitignore", BEGIN_GITIGNORE, END_GITIGNORE, ignore_block, root) != "unchanged":
            changed += 1

        install_manifest = dict(old_manifest) if isinstance(old_manifest, dict) else {}
        install_manifest.update(
            {
                "name": "ai-project-standard",
                "version": version,
                "layout_version": 1,
                "host_hint": host,
                "installed_files": installed_hashes,
                "local_modification_conflicts": incoming,
            }
        )
        if not install_manifest.get("installed_at"):
            install_manifest["installed_at"] = utc_now()
        manifest_changed = write_json_if_changed(old_manifest_path, install_manifest)
        if not quiet:
            if old_manifest.get("version") == version and changed == 0 and not incoming and not manifest_changed:
                print(f"AI Project Standard {version} already current in {root}")
            else:
                print(f"Installed AI Project Standard {version} in {root}")
            if incoming:
                print(f"WARN: {len(incoming)} locally modified managed file(s) preserved; review .ai/incoming/{version}/")
        return {
            "changed": changed,
            "incoming": incoming,
            "manifest_changed": manifest_changed,
            "root": str(root),
            "version": version,
        }
