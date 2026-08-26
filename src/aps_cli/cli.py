from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, STANDARD_VERSION
from .decision import DecisionError, answer_request, cancel_request, list_requests, load_runtime_state, register_request, show_request
from .installer import BEGIN_AGENTS, BEGIN_GITIGNORE, END_AGENTS, END_GITIGNORE, install_standard
from .research import render_brief

HOSTS = ("codex", "generic")
PLAN_MODE_REQUIRED_STAGES = frozenset({1, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 20})


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def stage_requires_plan_mode(state: dict) -> bool:
    """Return whether the active Stage requires a Plan-mode entry handoff."""
    if state.get("stage_status") == "COMPLETE":
        return False
    stage = state.get("stage")
    if isinstance(stage, int) and stage in PLAN_MODE_REQUIRED_STAGES:
        return True
    return stage == 22 and bool(state.get("active_change_refs"))


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


def has_aps_markers(root: Path) -> bool:
    for path, begin, end in (
        (root / "AGENTS.md", BEGIN_AGENTS, END_AGENTS),
        (root / ".gitignore", BEGIN_GITIGNORE, END_GITIGNORE),
    ):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return True
        if begin in text or end in text:
            return True
    return False


def missing_aps_markers(root: Path) -> list[str]:
    missing = []
    for path, begin, end in (
        (root / "AGENTS.md", BEGIN_AGENTS, END_AGENTS),
        (root / ".gitignore", BEGIN_GITIGNORE, END_GITIGNORE),
    ):
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError:
            text = ""
        if begin not in text or end not in text:
            missing.append(str(path.relative_to(root)))
    return missing


def has_aps_artifacts(root: Path) -> bool:
    paths = (
        ".ai/standard-manifest.json",
        ".ai/state.yaml",
        ".ai/decisions.md",
        ".ai/registry.yaml",
        ".ai/standards/lifecycle.md",
        ".ai/bootstrap/bootstrap-prompt.txt",
    )
    return has_aps_markers(root) or any((root / path).exists() for path in paths)


def governed_ancestor(root: Path) -> Path | None:
    for parent in root.parents:
        if has_aps_artifacts(parent):
            return parent
    return None


def is_governed(root: Path) -> bool:
    return (root / ".ai" / "standard-manifest.json").is_file()


def read_manifest(root: Path) -> dict:
    p = root / ".ai" / "standard-manifest.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except Exception:
        return {}


def missing_managed_files(root: Path, manifest: dict) -> list[str]:
    installed_files = manifest.get("installed_files")
    if not isinstance(installed_files, dict) or not installed_files:
        return [".ai/standard-manifest.json (invalid installed_files)"]
    missing = []
    for relative in installed_files:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            missing.append(f"invalid managed path: {relative}")
        elif not (root / path).is_file():
            missing.append(relative)
    return missing


def read_runtime_state(root: Path) -> dict[str, str]:
    path = root / ".ai" / "state.yaml"
    if not path.is_file():
        return {}
    fields: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"cycle", "stage_status"}:
            fields[key.strip()] = value.strip().strip("\"'")
    if not fields.get("cycle") or not fields.get("stage_status"):
        return {}
    return fields


def ensure_git(root: Path, enabled: bool = True) -> None:
    if not enabled or (root / ".git").exists():
        return
    git = shutil.which("git")
    if not git:
        print("WARN  git not found; skipped git init")
        return
    proc = subprocess.run(
        [git, "init"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode == 0:
        print("OK    initialized Git repository")
    else:
        print("WARN  git init failed")


def _runtime_summary(root: Path) -> list[str]:
    try:
        state = load_runtime_state(root)
    except DecisionError as exc:
        return [f"Runtime state invalid: {exc}"]

    lines = [
        f"Cycle: {state.get('cycle', 'unknown')}",
        f"Stage: {state.get('stage', 'unknown')} / {state.get('stage_type', 'unknown')}",
        f"Status: {state.get('stage_status', 'unknown')}",
    ]
    if stage_requires_plan_mode(state):
        lines.append("Mode gate: PLAN (required on Stage entry)")
        lines.append("Mode action: switch Codex to Plan mode before changing files; after plan acceptance, execute normally.")
    else:
        lines.append("Mode gate: NORMAL (Plan mode not required)")
    gate = state.get("gate_status")
    if gate not in (None, "null"):
        lines.append(f"Gate: {gate}")
    goal = state.get("current_goal")
    if isinstance(goal, str) and goal.strip():
        lines.append(f"Goal: {goal.strip()}")
    pending = [ref for ref in state.get("pending_decision_refs", []) if isinstance(ref, str)]
    if pending:
        lines.append(f"Pending decisions: {', '.join(pending)}")
    blockers = state.get("blockers", [])
    for blocker in blockers:
        if isinstance(blocker, dict):
            kind = str(blocker.get("type") or "blocker")
            ref = str(blocker.get("ref") or "")
            detail = str(blocker.get("reason") or blocker.get("message") or "")
            suffix = " ".join(part for part in (ref, detail) if part)
            lines.append(f"Blocker: {kind}{(' ' + suffix) if suffix else ''}")
        elif blocker:
            lines.append(f"Blocker: {blocker}")
    next_action = state.get("next_action")
    if next_action in (None, "", "null"):
        if pending:
            next_action = (
                f"在当前对话完成 {', '.join(pending)} 的决策卡分析并回答，"
                f"然后运行 `aps decision answer {pending[0]} <ANSWER>`。"
            )
        elif blockers:
            next_action = "解决以上 blocker，并重新运行 `aps status`。"
        elif state.get("stage_status") == "COMPLETE" or gate == "PASS":
            next_action = "读取 Transition Contract，进入下一 Stage。"
        elif gate == "REVISE":
            next_action = "按 Failure Route 修复当前 Stage，并重新验证。"
        elif gate == "HOLD":
            next_action = "确认等待条件或恢复当前 Stage。"
        elif gate == "STOP":
            next_action = "当前 Cycle 已停止，不执行后续 Stage。"
        elif state.get("stage_type") == "GATED":
            next_action = "完成当前 Stage 的 Artifact、验收条件和验证，再更新 Gate。"
        else:
            next_action = "读取当前 Stage Contract 和 Artifact，继续 Required Actions。"
    if isinstance(next_action, str):
        rendered = next_action
    else:
        rendered = json.dumps(next_action, ensure_ascii=False)
    lines.append(f"Next action: {rendered}")
    return lines


def handoff_prompt(mode: str, root: Path | None = None) -> str:
    if mode == "init":
        prompt = (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it. "
            "Treat this as a new project, initialize the runtime governance state, start Stage 01, "
            "switch to Codex Plan mode before any file-changing action, and stop at the first required Gate or user decision."
        )
    elif mode == "resume":
        prompt = (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it. "
            "Resume this existing project from its actual current state; do not rebaseline it unless explicitly required by the Standard."
        )
    elif mode == "rebaseline":
        prompt = (
            "Read `.ai/bootstrap/bootstrap-prompt.txt` and execute it first. "
            "Then read `.ai/bootstrap/rebaseline-existing-project.txt` and execute it. "
            "Create the new rebaseline Cycle and begin Stage 01 in Codex Plan mode; do not run the full lifecycle in one turn."
        )
    else:
        raise ValueError(mode)
    if root is not None and mode in {"resume", "rebaseline"}:
        summary = _runtime_summary(root)
        if summary:
            prompt += "\n\nCurrent APS handoff:\n" + "\n".join(summary)
    return prompt


def current_stage_requires_plan_mode(root: Path) -> bool:
    try:
        return stage_requires_plan_mode(load_runtime_state(root))
    except DecisionError:
        return False


def launch_host(root: Path, host: str, prompt: str, no_launch: bool, require_plan_mode: bool = False) -> int:
    if require_plan_mode and host == "codex" and not no_launch:
        print("\nCodex Plan mode is required before this Stage handoff.")
        print("APS will not auto-launch a normal Codex session. Open the project in Codex, select Plan mode, and send:\n")
        print(prompt)
        return 0
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
    ancestor = governed_ancestor(root)
    if ancestor:
        print(f"REFUSE  nested APS project detected under governed project: {ancestor}")
        print("Use the existing project root, or explicitly create a separate project boundary first.")
        return 2
    if has_aps_artifacts(root):
        print("REFUSE  APS files or runtime state already exist in this directory.")
        print("Use `aps resume` to recover it or `aps upgrade` to update the Standard.")
        return 2
    existed_with_content = project_has_content(root)
    if existed_with_content:
        print("REFUSE  existing project content detected.")
        print("Use `aps resume` to adopt it, or `aps rebaseline` to re-audit it from Stage 01.")
        return 2
    root.mkdir(parents=True, exist_ok=True)
    ensure_git(root, enabled=not args.no_git)
    install(root, args.host, args.force_managed)
    rc = launch_host(root, args.host, handoff_prompt("init", root), args.no_launch, require_plan_mode=True)
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
    ancestor = governed_ancestor(root)
    if ancestor and not is_governed(root):
        print(f"REFUSE  nested ungoverned directory under APS project: {ancestor}")
        print("Run `aps resume` from the governed project root.")
        return 2
    if is_governed(root):
        manifest = read_manifest(root)
        if not manifest:
            print("REFUSE  APS manifest is unreadable or invalid.")
            print("Run `aps upgrade` only after reviewing the damaged project state.")
            return 2
        if manifest.get("version") != STANDARD_VERSION:
            print(f"REFUSE  installed Standard is {manifest.get('version', 'unknown')}; bundled version is {STANDARD_VERSION}.")
            print("Run `aps upgrade` explicitly before resuming.")
            return 2
        marker_missing = missing_aps_markers(root)
        if marker_missing:
            print("REFUSE  APS routing markers are incomplete:")
            for item in marker_missing:
                print(f"  - {item}")
            print("Run `aps upgrade` explicitly after reviewing the project state.")
            return 2
        missing = missing_managed_files(root, manifest)
        if missing:
            print("REFUSE  installed Standard files are missing or invalid:")
            for item in missing:
                print(f"  - {item}")
            print("Run `aps upgrade` explicitly after reviewing the project state.")
            return 2
        return launch_host(
            root,
            args.host,
            handoff_prompt("resume", root),
            args.no_launch,
            require_plan_mode=current_stage_requires_plan_mode(root),
        )
    if has_aps_artifacts(root):
        print("REFUSE  partial APS installation detected without a valid manifest.")
        print("Review the directory before using `aps upgrade` to repair it.")
        return 2
    if not project_has_content(root):
        print("REFUSE  this looks like an empty/new project. Use `aps init`.")
        return 2
    print("Adopting existing project into APS; future `aps resume` operations are read-only.")
    install(root, args.host, force_managed=False)
    return launch_host(root, args.host, handoff_prompt("resume", root), args.no_launch, require_plan_mode=True)


def cmd_rebaseline(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir() or not is_governed(root):
        print("REFUSE  rebaseline requires an existing project.")
        return 2
    if not args.confirm:
        print("REFUSE  rebaseline creates a new Cycle and requires explicit confirmation.")
        print("Re-run with `aps rebaseline --confirm` after reviewing the current project state.")
        return 2
    manifest = read_manifest(root)
    if not manifest:
        print("REFUSE  APS manifest is unreadable or invalid.")
        return 2
    marker_missing = missing_aps_markers(root)
    if marker_missing:
        print("REFUSE  APS routing markers are incomplete; run `aps upgrade` first.")
        return 2
    runtime = read_runtime_state(root)
    if not runtime:
        print("REFUSE  rebaseline requires initialized runtime state; resume Bootstrap first.")
        return 2
    if runtime["cycle"] != "CYCLE-001" and runtime["stage_status"] != "COMPLETE":
        print(f"REFUSE  active Cycle {runtime['cycle']} is not complete; resume it instead of creating another Cycle.")
        return 2
    if manifest.get("version") != STANDARD_VERSION:
        print(f"REFUSE  installed Standard is {manifest.get('version', 'unknown')}; run `aps upgrade` first.")
        return 2
    missing = missing_managed_files(root, manifest)
    if missing:
        print("REFUSE  installed Standard files are missing or invalid; run `aps upgrade` first.")
        return 2
    return launch_host(root, args.host, handoff_prompt("rebaseline", root), args.no_launch, require_plan_mode=True)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    host = args.host
    return run_doctor(root, host, strict_runtime=not args.standard_only)


def cmd_upgrade(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        print(f"FAIL  project directory not found: {root}")
        return 2
    ancestor = governed_ancestor(root)
    if ancestor and not is_governed(root):
        print(f"REFUSE  nested ungoverned directory under APS project: {ancestor}")
        print("Run `aps upgrade` from the governed project root.")
        return 2
    before = read_manifest(root).get("version")
    result = install(root, args.host, args.force_managed)
    after = result["version"]
    if before == after and result["changed"] == 0 and not result["manifest_changed"]:
        if result["incoming"]:
            print(f"OK    Standard {after} unchanged; {len(result['incoming'])} managed conflict(s) remain")
        else:
            print(f"OK    already on bundled Standard {after}")
    else:
        print(f"OK    Standard {before or 'unmanaged'} -> {after}")
    print("Run `aps doctor` after Bootstrap/runtime state is available.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    manifest = read_manifest(root)
    manifest_present = (root / ".ai" / "standard-manifest.json").is_file()
    state = root / ".ai" / "state.yaml"
    print(f"Project: {root}")
    if manifest_present and not manifest:
        print("Governed: invalid manifest")
    else:
        print(f"Governed: {'yes' if manifest else 'no'}")
    if manifest:
        print(f"Standard: {manifest.get('version', 'unknown')}")
        conflicts = manifest.get("local_modification_conflicts") or []
        print(f"Managed conflicts: {len(conflicts)}")
    print(f"Runtime state: {'present' if state.is_file() else 'not initialized'}")
    if state.is_file():
        for line in _runtime_summary(root):
            print("  " + line)
    return 0


def cmd_decision_request(args: argparse.Namespace) -> int:
    return register_request(args.project, args.request_file)


def cmd_decision_list(args: argparse.Namespace) -> int:
    return list_requests(args.project)


def cmd_decision_show(args: argparse.Namespace) -> int:
    return show_request(args.project, args.reference)


def cmd_decision_answer(args: argparse.Namespace) -> int:
    return answer_request(args.project, args.reference, args.answer, args.reason)


def cmd_decision_cancel(args: argparse.Namespace) -> int:
    return cancel_request(args.project, args.reference, args.reason)


def cmd_research_brief(args: argparse.Namespace) -> int:
    return render_brief(args.project, args.artifact)


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
        "3": ["rebaseline", str(root), "--confirm"],
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
    s.add_argument("--force-mode", action="store_true", help="deprecated; cannot bypass existing-project protection")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("resume", help="adopt/resume an existing project")
    common(s)
    s.add_argument("--no-launch", action="store_true")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("rebaseline", help="start a new full review Cycle from Stage 01")
    common(s)
    s.add_argument("--confirm", action="store_true", help="confirm creation of a new Cycle")
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

    s = sub.add_parser("decision", help="register and resolve structured user decisions")
    decision_sub = s.add_subparsers(dest="decision_command", required=True)

    d = decision_sub.add_parser("request", help="register a pending Decision Request")
    d.add_argument("request_file", type=Path)
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.set_defaults(func=cmd_decision_request)

    d = decision_sub.add_parser("list", help="list pending Decision Requests")
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.set_defaults(func=cmd_decision_list)

    d = decision_sub.add_parser("show", help="show a Decision Request")
    d.add_argument("reference")
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.set_defaults(func=cmd_decision_show)

    d = decision_sub.add_parser("answer", help="record a selected Decision Request answer")
    d.add_argument("reference")
    d.add_argument("answer")
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.add_argument("--reason", default="", help="optional reason recorded with the decision")
    d.set_defaults(func=cmd_decision_answer)

    d = decision_sub.add_parser("cancel", help="cancel a pending Decision Request")
    d.add_argument("reference")
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.add_argument("--reason", default="", help="optional cancellation reason")
    d.set_defaults(func=cmd_decision_cancel)

    s = sub.add_parser("research", help="render validated research outputs")
    research_sub = s.add_subparsers(dest="research_command", required=True)
    d = research_sub.add_parser("brief", help="render the Research Brief section from a Stage Artifact")
    d.add_argument("artifact", type=Path)
    d.add_argument("project", nargs="?", default=".", type=Path)
    d.set_defaults(func=cmd_research_brief)
    return p


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
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
