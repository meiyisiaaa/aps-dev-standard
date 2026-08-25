from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, STANDARD_VERSION
from .installer import install_standard

HOSTS = ("codex", "generic")


def bundle_dir() -> Path:
    return Path(__file__).resolve().parent / "bundle"


def project_has_content(root: Path) -> bool:
    if not root.exists():
        return False
    ignored = {".git", ".ai", ".agents", ".DS_Store"}
    try:
        entries = [p for p in root.iterdir() if p.name not in ignored]
    except OSError:
        return True
    return bool(entries)


def is_governed(root: Path) -> bool:
    return (root / ".ai" / "standard-manifest.json").is_file()


def read_manifest(root: Path) -> dict:
    p = root / ".ai" / "standard-manifest.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except Exception:
        return {}


def ensure_git(root: Path, enabled: bool = True) -> None:
    if not enabled or (root / ".git").exists():
        return
    git = shutil.which("git")
    if not git:
        print("WARN  git not found; skipped git init")
        return
    proc = subprocess.run([git, "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode == 0:
        print("OK    initialized Git repository")
    else:
        print("WARN  git init failed")


def handoff_prompt(mode: str) -> str:
    if mode == "init":
        return (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it. "
            "Treat this as a new project, initialize the runtime governance state, start Stage 01, "
            "and stop at the first required Gate or user decision."
        )
    if mode == "resume":
        return (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it. "
            "Resume this existing project from its actual current state; do not rebaseline it unless explicitly required by the Standard."
        )
    if mode == "rebaseline":
        return (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it first. "
            "Then read `.ai/bootstrap/rebaseline-existing-project.txt` and execute it. "
            "Create the new rebaseline Cycle and begin Stage 01; do not run the full lifecycle in one turn."
        )
    raise ValueError(mode)


def launch_host(root: Path, host: str, prompt: str, no_launch: bool) -> int:
    if no_launch or host != "codex":
        print("\nNext action in your Agent Host:\n")
        print(prompt)
        return 0
    codex = shutil.which("codex")
    if not codex:
        print("\nCodex CLI was not found on PATH. Open the project in Codex and send:\n")
        print(prompt)
        return 0
    print("\nLaunching Codex...\n")
    return subprocess.run([codex, prompt], cwd=root).returncode


def run_doctor(root: Path, host: str, strict_runtime: bool = True) -> int:
    lint = root / ".ai" / "tools" / "standards-lint.py"
    if not lint.is_file():
        print("FAIL  AI Project Standard is not installed. Run `aps init`, `aps resume`, or `aps upgrade`.")
        return 2
    cmd = [sys.executable, str(lint)]
    if strict_runtime:
        cmd += ["--project-root", str(root), "--host", host]
    return subprocess.run(cmd, cwd=root).returncode


def install(root: Path, host: str, force_managed: bool = False, quiet: bool = False) -> dict:
    return install_standard(bundle_dir(), root, host=host, force_managed=force_managed, quiet=quiet)


def cmd_init(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    existed_with_content = project_has_content(root)
    if existed_with_content and not args.force_mode:
        print("REFUSE  existing project content detected.")
        print("Use `aps resume` to adopt it, or `aps rebaseline` to re-audit it from Stage 01.")
        return 2
    root.mkdir(parents=True, exist_ok=True)
    ensure_git(root, enabled=not args.no_git)
    install(root, args.host, args.force_managed)
    rc = launch_host(root, args.host, handoff_prompt("init"), args.no_launch)
    if rc != 0:
        return rc
    if args.no_launch:
        print("\nAfter Bootstrap: `aps doctor`")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        print(f"FAIL  project directory not found: {root}")
        return 2
    if not project_has_content(root) and not is_governed(root):
        print("REFUSE  this looks like an empty/new project. Use `aps init`.")
        return 2
    install(root, args.host, args.force_managed)
    return launch_host(root, args.host, handoff_prompt("resume"), args.no_launch)


def cmd_rebaseline(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir() or (not project_has_content(root) and not is_governed(root)):
        print("REFUSE  rebaseline requires an existing project.")
        return 2
    install(root, args.host, args.force_managed)
    return launch_host(root, args.host, handoff_prompt("rebaseline"), args.no_launch)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    host = args.host
    return run_doctor(root, host, strict_runtime=not args.standard_only)


def cmd_upgrade(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        print(f"FAIL  project directory not found: {root}")
        return 2
    before = read_manifest(root).get("version")
    result = install(root, args.host, args.force_managed)
    after = result["version"]
    if before == after and result["changed"] == 0 and not result["incoming"]:
        print(f"OK    already on bundled Standard {after}")
    else:
        print(f"OK    Standard {before or 'unmanaged'} -> {after}")
    print("Run `aps doctor` after Bootstrap/runtime state is available.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    manifest = read_manifest(root)
    state = root / ".ai" / "state.yaml"
    print(f"Project: {root}")
    print(f"Governed: {'yes' if manifest else 'no'}")
    if manifest:
        print(f"Standard: {manifest.get('version', 'unknown')}")
        conflicts = manifest.get("local_modification_conflicts") or []
        print(f"Managed conflicts: {len(conflicts)}")
    print(f"Runtime state: {'present' if state.is_file() else 'not initialized'}")
    if state.is_file():
        text = state.read_text(encoding="utf-8", errors="replace")
        wanted = ("cycle:", "stage:", "stage_type:", "stage_status:", "gate_status:")
        for line in text.splitlines():
            if line.lstrip().startswith(wanted):
                print("  " + line.strip())
    return 0


def interactive_menu() -> int:
    root = Path.cwd().resolve()
    governed = is_governed(root)
    existing = project_has_content(root)
    print("\nAI Project Standard (aps)\n")
    print(f"Project: {root}")
    if governed:
        print("Detected: governed project")
    elif existing:
        print("Detected: existing project")
    else:
        print("Detected: new/empty project")
    print("\n1. Start a new project")
    print("2. Resume/adopt existing project")
    print("3. Rebaseline existing project from Stage 01")
    print("4. Doctor / health check")
    print("5. Upgrade Standard")
    print("6. Status")
    print("0. Exit")
    try:
        choice = input("\nSelect: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 130
    mapping = {
        "1": ["init", str(root)],
        "2": ["resume", str(root)],
        "3": ["rebaseline", str(root)],
        "4": ["doctor", str(root)],
        "5": ["upgrade", str(root)],
        "6": ["status", str(root)],
        "0": [],
    }
    if choice not in mapping:
        print("Invalid selection.")
        return 2
    if choice == "0":
        return 0
    return main(mapping[choice])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aps", description="AI Project Standard CLI")
    p.add_argument("--version", action="version", version=f"aps {__version__} (Standard {STANDARD_VERSION})")
    sub = p.add_subparsers(dest="command")

    def common(sp: argparse.ArgumentParser, default_project: str = ".") -> None:
        sp.add_argument("project", nargs="?", default=default_project, type=Path)
        sp.add_argument("--host", choices=HOSTS, default="codex")
        sp.add_argument("--force-managed", action="store_true", help="replace locally modified managed Standard files after backup")

    s = sub.add_parser("init", help="initialize a new project and hand off to the Agent")
    common(s)
    s.add_argument("--no-launch", action="store_true", help="install only; print the Agent handoff instead of launching Codex")
    s.add_argument("--no-git", action="store_true", help="do not initialize Git in a new empty directory")
    s.add_argument("--force-mode", action="store_true", help="allow init even when project content already exists")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("resume", help="adopt/resume an existing project")
    common(s)
    s.add_argument("--no-launch", action="store_true")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("rebaseline", help="start a new full review Cycle from Stage 01")
    common(s)
    s.add_argument("--no-launch", action="store_true")
    s.set_defaults(func=cmd_rebaseline)

    s = sub.add_parser("doctor", help="validate Standard and project governance health")
    s.add_argument("project", nargs="?", default=".", type=Path)
    s.add_argument("--host", choices=HOSTS, default="codex")
    s.add_argument("--standard-only", action="store_true", help="validate installed Standard without requiring initialized runtime state")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("upgrade", help="apply the Standard version bundled with this aps CLI")
    common(s)
    s.set_defaults(func=cmd_upgrade)

    s = sub.add_parser("status", help="show lightweight project governance status")
    s.add_argument("project", nargs="?", default=".", type=Path)
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return interactive_menu()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return interactive_menu()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
