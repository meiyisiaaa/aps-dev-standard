from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, STANDARD_VERSION
from .decision import DecisionError, answer_request, cancel_request, list_requests, load_runtime_state, register_request, show_request
from .governance import GovernanceProblem, governance_problem, load_project_profile, profile_status, registry_problems, runtime_governance_problems
from .installer import BEGIN_AGENTS, BEGIN_GITIGNORE, END_AGENTS, END_GITIGNORE, SHA256_RE, assert_no_reparse, install_standard, is_safe_version, sha256
from .research import render_brief

HOSTS = ("codex", "generic")
PLAN_MODE_REQUIRED_STAGES = frozenset({1, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 20})
MANAGED_PATH_PREFIX = ".ai/"


class ProjectBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Diagnostic:
    """An internal, non-persistent diagnostic with one recovery route."""

    code: str
    marker: str
    problem: str
    cause: str
    next_action: str
    exit_code: int = 2


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


def project_path(value: Path) -> Path:
    candidate = value.expanduser()
    try:
        assert_no_reparse(candidate, allow_ancestor_links=True)
        root = candidate.resolve()
        assert_no_reparse(root)
        return root
    except (OSError, RuntimeError) as exc:
        raise ProjectBoundaryError(str(exc)) from exc


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
        ".ai/tools/standards-lint.py",
        ".ai/.install.lock",
        ".ai/schemas/project-profile.schema.json",
        ".ai/schemas/transition-record.schema.json",
        ".ai/schemas/release-readiness.schema.json",
        ".ai/project-profile.json",
        ".ai/audit/transitions.jsonl",
        ".ai/release-readiness.json",
    )
    if has_aps_markers(root) or any((root / path).exists() or (root / path).is_symlink() for path in paths):
        return True
    incoming = root / ".ai" / "incoming"
    try:
        return incoming.is_dir() and any(incoming.rglob("*"))
    except OSError:
        return True


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


def _safe_managed_path(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(MANAGED_PATH_PREFIX) or "\\" in value:
        return False
    if any(ord(char) < 32 for char in value):
        return False
    parts = value.split("/")
    return len(parts) > 1 and all(part not in {"", ".", ".."} for part in parts)


def manifest_problems(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest 不是 JSON 对象"]
    problems: list[str] = []
    if manifest.get("name") != "ai-project-standard":
        problems.append("manifest name 无效")
    if not is_safe_version(manifest.get("version")):
        problems.append("manifest version 无效")
    if manifest.get("layout_version") != 1:
        problems.append("manifest layout_version 无效")
    installed = manifest.get("installed_files")
    if not isinstance(installed, dict) or not installed:
        problems.append("manifest installed_files 缺失或为空")
    else:
        seen_paths: set[str] = set()
        for relative, digest in installed.items():
            if not _safe_managed_path(relative) or not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                problems.append(f"manifest 托管文件记录无效：{relative}")
                continue
            folded = relative.casefold()
            if folded in seen_paths:
                problems.append(f"manifest 托管文件路径大小写碰撞：{relative}")
            seen_paths.add(folded)
    conflicts = manifest.get("local_modification_conflicts", [])
    if not isinstance(conflicts, list) or any(not _safe_managed_path(item) for item in conflicts):
        problems.append("manifest local_modification_conflicts 无效")
    return problems


def runtime_state(root: Path) -> tuple[dict | None, str | None]:
    path = root / ".ai" / "state.yaml"
    if not path.exists() and not path.is_symlink():
        return None, None
    if path.is_symlink():
        return None, "state.yaml 不能是符号链接"
    try:
        return load_runtime_state(root), None
    except (DecisionError, OSError, RuntimeError) as exc:
        return None, str(exc)


def boundary_error(path: Path) -> str | None:
    try:
        assert_no_reparse(path)
    except RuntimeError as exc:
        return str(exc)
    return None


def project_boundary_error(root: Path) -> str | None:
    for relative, directory in ((".ai", True), (".agents", True), ("AGENTS.md", False), (".gitignore", False)):
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue
        if (error := boundary_error(path)):
            return f"{relative}：{error}"
        if directory and not path.is_dir():
            return f"{relative} 必须是目录"
        if not directory and not path.is_file():
            return f"{relative} 必须是普通文件"
    return None


def missing_managed_files(root: Path, manifest: dict) -> list[str]:
    installed_files = manifest.get("installed_files")
    if not isinstance(installed_files, dict) or not installed_files:
        return [".ai/standard-manifest.json (invalid installed_files)"]
    missing = []
    for relative in installed_files:
        path = Path(relative)
        unsafe_target = False
        if _safe_managed_path(relative) and not path.is_absolute() and ".." not in path.parts:
            try:
                assert_no_reparse(root / path)
            except RuntimeError:
                unsafe_target = True
        else:
            unsafe_target = True
        if unsafe_target:
            missing.append(f"invalid managed path: {relative}")
        elif not (root / path).is_file():
            missing.append(relative)
    return missing


def modified_managed_files(root: Path, manifest: dict) -> list[str]:
    installed_files = manifest.get("installed_files")
    if not isinstance(installed_files, dict):
        return []
    modified = []
    for relative, expected in installed_files.items():
        if not _safe_managed_path(relative) or not isinstance(expected, str):
            continue
        path = root / Path(relative)
        try:
            assert_no_reparse(path)
            if path.is_file() and sha256(path).lower() != expected.lower():
                modified.append(relative)
        except (OSError, RuntimeError):
            modified.append(relative)
    return modified


def read_runtime_state(root: Path) -> dict:
    state, error = runtime_state(root)
    if error:
        raise DecisionError(error)
    return state or {}


def ensure_git(root: Path, enabled: bool = True) -> None:
    if not enabled:
        return
    current = root
    while True:
        git_marker = current / ".git"
        if git_marker.exists() or git_marker.is_symlink():
            if current != root:
                print(f"OK    检测到父级 Git 仓库，跳过嵌套初始化：{current}")
            return
        if has_aps_artifacts(current):
            return
        if current.parent == current:
            break
        current = current.parent
    git = shutil.which("git")
    if not git:
        print("WARN  未找到 git，已跳过 Git 初始化。")
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
        print("OK    已初始化 Git 仓库。")
    else:
        print("WARN  Git 初始化失败；项目文件仍已安装。")


def recovery(cause: str, next_action: str) -> None:
    print(f"原因：{cause}")
    print(f"NEXT  {next_action}")


GOVERNANCE_CAUSES = {
    "registry": "Registry 缺失或无法严格解析，Agent 不能安全定位当前 Source of Truth。",
    "project_profile": "项目风险基线缺失或无法严格解析，APS 不会猜测为 NORMAL。",
    "transition_audit": "Stage / Gate / Cycle 审计链缺失、断裂或未对齐当前状态。",
    "release_readiness": "Release readiness 缺失或未满足当前风险级别的必需检查。",
    "prd_snapshot": "当前 PRD Snapshot 的来源 revision 或字段不完整，不能证明它反映当前状态。",
}

GOVERNANCE_NEXT_ACTIONS = {
    "registry": "在 Host 中按 `.ai/templates/registry.yaml` 修复 `.ai/registry.yaml`，再运行 `{doctor_command}`。",
    "project_profile": "在 Host 中按 `.ai/templates/project-profile.json` 创建或修复 `.ai/project-profile.json`，再运行 `{doctor_command}`。",
    "transition_audit": "在 Host 中人工修复或补齐 `.ai/audit/transitions.jsonl`，使最后一条记录与 `.ai/state.yaml` 一致，再运行 `{doctor_command}`。",
    "release_readiness": "在 Host 中按 `.ai/templates/release-readiness.json` 补齐 `.ai/release-readiness.json`，再运行 `{doctor_command}`。",
    "prd_snapshot": "在 Host 中更新当前 Cycle 的 `08_PRD_SNAPSHOT.md`，补齐最新 Source State Revision 和来源引用，再运行 `aps status`。",
}
DEFAULT_GOVERNANCE_NEXT_ACTION = "运行 `{doctor_command}`，按第一项治理问题人工修复后再运行 `aps status`。"


def governance_diagnostic(
    problem: GovernanceProblem,
    *,
    action: str | None = None,
    standard_only: bool = False,
    marker: str = "FAIL",
) -> Diagnostic:
    cause = GOVERNANCE_CAUSES.get(problem.code, "项目治理校验未通过，APS 不会猜测或绕过当前状态。")
    doctor_command = "aps doctor --standard-only" if standard_only else "aps doctor"
    next_action = action or GOVERNANCE_NEXT_ACTIONS.get(problem.code, DEFAULT_GOVERNANCE_NEXT_ACTION).format(doctor_command=doctor_command)
    detail = problem.message
    if problem.path and problem.path not in detail:
        detail = f"{detail}（路径：{problem.path}）"
    return Diagnostic(
        code=problem.code,
        marker=marker,
        problem=f"项目治理校验失败：{detail}",
        cause=cause,
        next_action=next_action,
    )


def emit_diagnostic(diagnostic: Diagnostic) -> int:
    print(f"{diagnostic.marker}  {diagnostic.problem}")
    recovery(diagnostic.cause, diagnostic.next_action)
    return diagnostic.exit_code


def print_governance_failure(
    problem: GovernanceProblem,
    *,
    action: str | None = None,
    standard_only: bool = False,
    marker: str = "FAIL",
) -> None:
    emit_diagnostic(governance_diagnostic(problem, action=action, standard_only=standard_only, marker=marker))


def command_hint(argv: list[str]) -> str:
    return " ".join(f'"{arg}"' if any(char.isspace() for char in arg) else arg for arg in ("aps", *argv))


def _runtime_summary(root: Path, *, include_profile: bool = True) -> list[str]:
    state_path = root / ".ai" / "state.yaml"
    if not state_path.is_file():
        return [
            "Runtime state: not initialized（运行状态尚未初始化）",
            "原因：Bootstrap 尚未写入 `.ai/state.yaml`，当前不能推断 active Stage。",
            "Next action: 在 Agent Host 中完成 Bootstrap；Codex 不会自动启动普通会话。",
        ]
    try:
        state = load_runtime_state(root)
    except DecisionError as exc:
        return [
            f"Runtime state invalid: {exc}",
            f"原因：项目运行状态无法安全解析。",
            "Next action: 先运行 `aps doctor --standard-only`，修复第一项状态问题后再运行 `aps resume --no-launch`。",
        ]

    lines = [
        f"Cycle: {state.get('cycle', 'unknown')}",
        f"Stage: {state.get('stage', 'unknown')} / {state.get('stage_type', 'unknown')}",
        f"Status: {state.get('stage_status', 'unknown')}",
    ]
    if include_profile:
        profile, profile_error = load_project_profile(root)
        if profile is not None:
            lines.append(f"Risk profile: {profile['risk_profile']}")
            lines.append(f"Workstreams: {len(profile['workstreams'])}")
        elif profile_error:
            profile_path = root / ".ai" / "project-profile.json"
            if profile_path.exists() or profile_path.is_symlink():
                lines.append(f"Risk profile: invalid（{profile_error}）")
            else:
                lines.append("Risk profile: not initialized（风险基线尚未初始化）")
    if stage_requires_plan_mode(state):
        lines.append("Mode gate: PLAN (required on Stage entry)（进入阶段前必须打开 Plan 模式）")
        lines.append("Mode action: 先在当前 Host 打开原生 Plan 模式并确认计划，再切换普通模式执行文件修改。")
    else:
        lines.append("Mode gate: NORMAL (Plan mode not required)（当前阶段无需 Plan 模式）")
    gate = state.get("gate_status")
    if gate not in (None, "null"):
        lines.append(f"Gate: {gate}")
    goal = state.get("current_goal")
    if isinstance(goal, str) and goal.strip():
        lines.append(f"Goal: {goal.strip()}")
    pending = [ref for ref in state.get("pending_decision_refs", []) if isinstance(ref, str)]
    if pending:
        lines.append(f"Pending decisions: {', '.join(pending)}")
    active_changes = [ref for ref in state.get("active_change_refs", []) if isinstance(ref, str)]
    if active_changes:
        lines.append(f"Active changes: {', '.join(active_changes)}")
        lines.append("Change action: 读取当前 Cycle 的 `22_CHANGE_LOG.md`，先完成 Impact Analysis，再只重跑受影响 Stage 和验证。")
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
    stage_ready = (
        not pending
        and not blockers
        and (state.get("stage_status") == "COMPLETE" or gate == "PASS")
    )
    next_action = state.get("next_action")
    if next_action in (None, "", "null"):
        if pending:
            next_action = (
                f"在当前对话完成 {', '.join(pending)} 的决策卡分析并回答，"
                f"然后运行 `aps decision answer {pending[0]} <ANSWER>`。"
            )
        elif active_changes:
            next_action = "读取 `.ai/templates/change-log.md` 完成 Impact Analysis；确认最早受影响 Stage 后再执行变更。"
        elif blockers:
            next_action = "解决以上 blocker，并重新运行 `aps status`。"
        elif stage_ready:
            next_action = "读取 Transition Contract，直接进入其指定的下一 Stage；不需要额外确认当前 Stage PASS。"
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
    if stage_ready:
        lines.append(
            "下一阶段入口提醒：读取 Transition Contract；如果目标 Stage 需要 Plan 模式，"
            "先在当前 Host 打开 Plan，再开始工作。普通 Stage PASS 不需要额外用户确认。"
        )
    return lines


def handoff_prompt(mode: str, root: Path | None = None) -> str:
    if mode == "init":
        prompt = (
            "请读取 `.ai/bootstrap/bootstrap-prompt.txt` 并执行。"
            "这是一个新项目：初始化运行治理状态并从 Stage 01 开始；"
            "任何文件修改前先切换到 Codex Plan 模式；普通 Stage 满足 Artifact 和 Validation 后直接推进，"
            "仅在需要用户决策的 Gate 或 Release 边界停止。"
        )
    elif mode == "resume":
        prompt = (
            "请读取 `.ai/bootstrap/bootstrap-prompt.txt` 并执行。"
            "从项目实际当前状态恢复；除非 Standard 明确要求，不要创建新的 Rebaseline Cycle。"
        )
    elif mode == "rebaseline":
        prompt = (
            "请先读取并执行 `.ai/bootstrap/bootstrap-prompt.txt`，"
            "再读取并执行 `.ai/bootstrap/rebaseline-existing-project.txt`。"
            "创建新的 Rebaseline Cycle，并在 Codex Plan 模式下从 Stage 01 开始；不要在一次对话中跑完整生命周期。"
        )
    else:
        raise ValueError(mode)
    if root is not None and mode in {"resume", "rebaseline"}:
        summary = _runtime_summary(root)
        if summary:
            prompt += "\n\nCurrent APS handoff:\n" + "\n".join(summary)
    return prompt


def current_stage_requires_plan_mode(root: Path) -> bool:
    state, error = runtime_state(root)
    if error:
        raise DecisionError(error)
    return True if state is None else stage_requires_plan_mode(state)


def launch_host(root: Path, host: str, prompt: str, no_launch: bool, require_plan_mode: bool = False) -> int:
    def print_copyable_handoff(title: str) -> None:
        print(f"\n{title}")
        print("请复制下面整个代码块发送到 Agent Host；APS 不写入项目文件，也不使用剪贴板：\n")
        print("```text")
        print(prompt)
        print("```")

    if require_plan_mode and host == "codex" and not no_launch:
        print("\nWARN  Codex Plan mode is required before this Stage handoff（当前阶段必须先打开 Plan 模式）。")
        print("APS will not auto-launch a normal Codex session（不会自动启动普通 Codex 会话）。")
        print("NEXT  Host 操作：打开项目，选择 Plan mode，然后发送下面的完整代码块。")
        print_copyable_handoff("=== APS Agent Handoff ===")
        print("=== End APS Agent Handoff ===")
        return 0
    if no_launch or host != "codex":
        print_copyable_handoff("=== APS Agent Handoff ===")
        print("=== End APS Agent Handoff ===")
        print("NEXT  在 Agent Host 中执行上方 handoff；完成 Bootstrap 后运行 `aps doctor`。")
        return 0
    codex = shutil.which("codex")
    if not codex:
        print("\nWARN  Codex CLI was not found on PATH（未找到 Codex CLI）。")
        print("NEXT  Host 操作：打开项目，选择对应模式，然后发送下面的完整代码块。")
        print_copyable_handoff("=== APS Agent Handoff ===")
        print("=== End APS Agent Handoff ===")
        return 0
    print("\n正在启动 Codex...\n")
    return subprocess.run([codex, prompt], cwd=root).returncode


def run_doctor(root: Path, host: str, strict_runtime: bool = True) -> int:
    if not root.is_dir():
        print(f"FAIL  项目目录不存在：{root}")
        recovery("doctor 找不到指定项目目录。", "确认路径后重新运行 `aps doctor <PROJECT>`。")
        return 2
    if (boundary := project_boundary_error(root)):
        print(f"FAIL  项目边界不安全：{boundary}")
        recovery("APS 不会跟随链接、reparse point 或错误类型的项目边界读取或写入文件。", "先移除或重命名冲突路径，再运行 `aps doctor --standard-only`。")
        return 2
    manifest_path = root / ".ai" / "standard-manifest.json"
    manifest = read_manifest(root)
    if manifest_path.exists():
        path_error = boundary_error(manifest_path)
        if path_error:
            print(f"FAIL  APS manifest 路径不安全：{path_error}")
            recovery("manifest 位于符号链接或 Windows reparse point 上。", "先移除该路径碰撞，再运行 `aps upgrade` 修复 Standard。")
            return 2
        problems = manifest_problems(manifest)
        if problems:
            print(f"FAIL  APS manifest 无效：{problems[0]}")
            recovery("无法确认当前 Standard 文件集合和托管边界。", "先运行 `aps upgrade` 修复半安装或损坏的 Standard。")
            return 2
        if manifest.get("version") != STANDARD_VERSION:
            print(f"FAIL  Standard 版本不匹配：{manifest.get('version')} -> {STANDARD_VERSION}")
            recovery("当前项目使用旧版 Standard，doctor 不会隐式覆盖它。", "运行 `aps upgrade`，再重新运行 `aps doctor`。")
            return 2
        marker_missing = missing_aps_markers(root)
        if marker_missing:
            print(f"FAIL  APS 路由标记不完整：{marker_missing[0]}")
            recovery("项目入口标记缺失，Agent Host 可能无法读取治理规则。", "运行 `aps upgrade` 修复标记后重试 `aps doctor`。")
            return 2
        missing = missing_managed_files(root, manifest)
        if missing:
            print(f"FAIL  Standard 托管文件缺失：{missing[0]}")
            recovery("manifest 记录的托管文件无法全部验证。", "运行 `aps upgrade` 修复文件后重试 `aps doctor`。")
            return 2
        conflicts = manifest.get("local_modification_conflicts", [])
        if conflicts:
            print(f"FAIL  存在未解决的托管文件冲突：{conflicts[0]}")
            recovery("本地修改的 Standard 文件尚未人工合并。", "先人工合并 `.ai/incoming/<version>/` 对应文件，再运行 `aps upgrade`。")
            return 2
        modified = modified_managed_files(root, manifest)
        if modified:
            print(f"FAIL  Standard 托管文件已被本地修改：{modified[0]}")
            recovery("当前文件内容与 manifest 记录的内置 Standard 不一致。", "运行 `aps upgrade` 将新版本放入 `.ai/incoming/<version>/`，人工合并后再运行 `aps upgrade`。")
            return 2
    elif has_aps_artifacts(root):
        print("FAIL  APS 安装不完整。")
        recovery("检测到 APS 残留但缺少有效 manifest，doctor 不会把它当作普通项目。", "运行 `aps upgrade` 修复可识别的 Standard 文件。")
        return 2
    lint = root / ".ai" / "tools" / "standards-lint.py"
    if not lint.is_file():
        print("FAIL  AI Project Standard 未完整安装。")
        if manifest_path.exists() or has_aps_artifacts(root):
            next_action = "运行 `aps upgrade` 修复半安装 Standard，再重新运行 `aps doctor`。"
        elif project_has_content(root):
            next_action = "运行 `aps resume --no-launch` 接管已有项目，再重新运行 `aps doctor`。"
        else:
            next_action = "运行 `aps init --no-launch` 初始化新项目，再重新运行 `aps doctor`。"
        recovery("项目中缺少 `.ai/tools/standards-lint.py`，无法开始体检。", next_action)
        return 2
    state_path = root / ".ai" / "state.yaml"
    state_present = state_path.exists() or state_path.is_symlink()
    if not state_present and strict_runtime:
        print("FAIL  Runtime state 尚未初始化。")
        recovery("Bootstrap 尚未写入 `.ai/state.yaml`，无法检查 active Stage。", "运行 `aps resume --no-launch`，完成 Bootstrap 后再运行 `aps doctor`。")
        return 2
    if state_present and not state_path.is_file():
        print("FAIL  Runtime state 路径无效：`.ai/state.yaml` 必须是普通文件。")
        recovery("状态路径是目录、链接或其他非普通文件，APS 不会猜测其内容。", "运行 `aps doctor --standard-only`，修复 `.ai/state.yaml` 后再运行 `aps resume --no-launch`。")
        return 2
    state = None
    if state_present:
        state, state_error = runtime_state(root)
        if state_error:
            print(f"FAIL  Runtime state 无法严格解析：{state_error}")
            if strict_runtime:
                next_action = "运行 `aps doctor --standard-only`，按第一项状态问题人工修复 `.ai/state.yaml`，再运行 `aps resume --no-launch`。"
            else:
                next_action = "在 Host 中按第一项状态问题人工修复 `.ai/state.yaml`，再运行 `aps resume --no-launch`。"
            recovery("状态损坏时 APS 不会猜测普通模式，也不会启动普通会话。", next_action)
            return 2
        profile, governance_problems = runtime_governance_problems(root, state)
        if governance_problems:
            print_governance_failure(governance_problems[0], standard_only=not strict_runtime)
            return 2
    else:
        registry_path = root / ".ai" / "registry.yaml"
        registry_required = registry_path.exists() or registry_path.is_symlink()
        registry_required = registry_required or any(
            (root / relative).exists() or (root / relative).is_symlink()
            for relative in (".ai/project-profile.json", ".ai/audit/transitions.jsonl")
        )
        if registry_required:
            registry_issues = registry_problems(root)
            if registry_issues:
                print_governance_failure(
                    governance_problem("registry", registry_issues[0], ".ai/registry.yaml"),
                    standard_only=not strict_runtime,
                )
                return 2
        if (root / ".ai" / "project-profile.json").exists() or (root / ".ai" / "project-profile.json").is_symlink():
            # A profile is optional before Bootstrap, but an explicitly created one must still be valid.
            _, profile_error = load_project_profile(root)
            if profile_error:
                print_governance_failure(
                    governance_problem("project_profile", profile_error, ".ai/project-profile.json"),
                    action="在 Host 中按 `.ai/templates/project-profile.json` 修复 `.ai/project-profile.json`，再运行 `aps doctor --standard-only`。",
                )
                return 2
    cmd = [sys.executable, str(lint)]
    if strict_runtime:
        cmd += ["--project-root", str(root), "--host", host]
    result = subprocess.run(cmd, cwd=root)
    if result.returncode:
        print("FAIL  体检未通过。")
        recovery("上方检查报告列出了当前 Standard 或运行状态的失败项。", "按上方 FAIL 逐项修复后重新运行 `aps doctor`。")
    return result.returncode


def install(root: Path, host: str, force_managed: bool = False, quiet: bool = False) -> dict:
    return install_standard(bundle_dir(), root, host=host, force_managed=force_managed, quiet=quiet)


def cmd_init(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    if (boundary := project_boundary_error(root)):
        print(f"REFUSE  项目边界不安全：{boundary}")
        recovery("APS 不会跟随链接、reparse point 或错误类型的项目边界写入文件。", "先移除或重命名冲突路径，再运行 `aps init --no-launch`。")
        return 2
    ancestor = governed_ancestor(root)
    if ancestor:
        print(f"REFUSE  检测到位于受 APS 管理项目下的嵌套项目：{ancestor}")
        recovery("当前目录会破坏外层项目的治理边界。", "回到外层项目根目录运行 `aps resume`；如确需独立项目，先明确创建独立目录边界。")
        return 2
    if has_aps_artifacts(root):
        print("REFUSE  当前目录已经存在 APS 文件或运行状态。")
        recovery("`init` 不能覆盖已有治理资产。", "恢复已有项目运行 `aps resume`；只更新 Standard 运行 `aps upgrade`。")
        return 2
    existed_with_content = project_has_content(root)
    if existed_with_content:
        print("REFUSE  检测到已有项目内容。")
        recovery("`init` 只适用于新建或空目录，不能把旧项目伪装成新项目。", "接管旧项目运行 `aps resume`；需要重新审查时在接管后运行 `aps rebaseline --confirm`。")
        return 2
    root.mkdir(parents=True, exist_ok=True)
    ensure_git(root, enabled=not args.no_git)
    install(root, args.host, args.force_managed)
    rc = launch_host(root, args.host, handoff_prompt("init", root), args.no_launch, require_plan_mode=True)
    if rc != 0:
        return rc
    if args.no_launch:
        print("\nAfter Bootstrap: `aps doctor`（完成 Bootstrap 后再用 `aps status` 确认当前 Stage）")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    if not root.is_dir():
        print(f"FAIL  项目目录不存在：{root}")
        recovery("resume 找不到指定项目目录。", "确认路径后重新运行 `aps resume <PROJECT>`。")
        return 2
    if (boundary := project_boundary_error(root)):
        print(f"REFUSE  项目边界不安全：{boundary}")
        recovery("APS 不会跟随链接、reparse point 或错误类型的项目边界写入文件。", "先移除或重命名冲突路径，再运行 `aps resume --no-launch`。")
        return 2
    ancestor = governed_ancestor(root)
    if ancestor and not is_governed(root):
        print(f"REFUSE  当前目录是受 APS 管理项目下的未接管嵌套目录：{ancestor}")
        recovery("resume 不能在嵌套目录建立第二套治理边界。", "回到受治理项目根目录运行 `aps resume`。")
        return 2
    if is_governed(root):
        manifest = read_manifest(root)
        path_error = boundary_error(root / ".ai" / "standard-manifest.json")
        if path_error:
            print(f"REFUSE  APS manifest 路径不安全：{path_error}")
            recovery("不能从链接或 reparse point 读取治理清单。", "先移除该路径碰撞，再运行 `aps upgrade` 修复 Standard。")
            return 2
        problems = manifest_problems(manifest)
        if problems:
            print(f"REFUSE  APS manifest 不可读或无效：{problems[0]}")
            recovery("无法确认已安装 Standard 文件的完整性。", "先人工检查项目状态；确认可修复后运行 `aps upgrade`，不要用 `init` 覆盖项目。")
            return 2
        if manifest.get("version") != STANDARD_VERSION:
            print(f"REFUSE  已安装 Standard 为 {manifest.get('version', 'unknown')}，当前 CLI 内置版本为 {STANDARD_VERSION}。")
            recovery("resume 不会隐式升级或覆盖项目中的 Standard 文件。", "审查变更后运行 `aps upgrade`，再运行 `aps resume --no-launch`。")
            return 2
        marker_missing = missing_aps_markers(root)
        if marker_missing:
            print("REFUSE  APS 路由标记不完整：")
            for item in marker_missing:
                print(f"  - {item}")
            recovery("AGENTS.md 或 .gitignore 的 APS 管理块缺失或不完整。", "审查项目文件后运行 `aps upgrade`，再重新运行 `aps resume`。")
            return 2
        missing = missing_managed_files(root, manifest)
        if missing:
            print("REFUSE  已安装 Standard 文件缺失或无效：")
            for item in missing:
                print(f"  - {item}")
            recovery("manifest 记录的托管文件无法全部找到。", "审查缺失文件后运行 `aps upgrade`，再重新运行 `aps resume`。")
            return 2
        conflicts = manifest.get("local_modification_conflicts", [])
        if conflicts:
            print("REFUSE  存在未解决的托管文件冲突：")
            for item in conflicts:
                print(f"  - {item}")
            recovery("本地修改的 Standard 文件仍未人工合并，resume 不会绕过冲突恢复。", "在 Host 中人工合并 `.ai/incoming/<version>/` 对应文件，再运行 `aps upgrade`。")
            return 2
        modified = modified_managed_files(root, manifest)
        if modified:
            print(f"REFUSE  Standard 托管文件已被本地修改：{modified[0]}")
            recovery("当前文件内容与 manifest 记录的内置 Standard 不一致。", "运行 `aps upgrade` 保留新版本到 `.ai/incoming/<version>/`，人工合并后再运行 `aps resume --no-launch`。")
            return 2
        state_path = root / ".ai" / "state.yaml"
        state, state_error = runtime_state(root)
        if (state_path.exists() or state_path.is_symlink()) and state_error:
            print(f"REFUSE  Runtime state 无法严格解析：{state_error}")
            recovery("状态损坏时 APS 不会猜测普通模式，也不会启动普通会话。", "运行 `aps doctor --standard-only`，修复第一项状态问题后再运行 `aps resume --no-launch`。")
            return 2
        registry_path = root / ".ai" / "registry.yaml"
        registry_required = registry_path.exists() or registry_path.is_symlink()
        registry_required = registry_required or any(
            (root / relative).exists() or (root / relative).is_symlink()
            for relative in (".ai/project-profile.json", ".ai/audit/transitions.jsonl")
        )
        if registry_required:
            registry_issues = registry_problems(root)
            if registry_issues:
                print_governance_failure(
                    governance_problem("registry", registry_issues[0], ".ai/registry.yaml"),
                    standard_only=True,
                    marker="REFUSE",
                )
                return 2
        if state is not None:
            profile_path = root / ".ai" / "project-profile.json"
            audit_path = root / ".ai" / "audit" / "transitions.jsonl"
            if not (profile_path.exists() or profile_path.is_symlink()) and not (audit_path.exists() or audit_path.is_symlink()):
                print("WARN  当前项目尚未完成风险基线和 Transition Bootstrap。")
                print("NEXT  先在 Agent Host 完成 Bootstrap；Codex 不会自动启动普通会话。")
                return launch_host(
                    root,
                    args.host,
                    handoff_prompt("resume", root),
                    args.no_launch,
                    require_plan_mode=True,
                )
            _, governance_problems = runtime_governance_problems(root, state)
            if governance_problems:
                print_governance_failure(governance_problems[0], standard_only=True, marker="REFUSE")
                return 2
        return launch_host(
            root,
            args.host,
            handoff_prompt("resume", root),
            args.no_launch,
            require_plan_mode=current_stage_requires_plan_mode(root),
        )
    if has_aps_artifacts(root):
        print("REFUSE  检测到没有有效 manifest 的不完整 APS 安装。")
        recovery("直接修复可能覆盖不完整安装留下的文件。", "先审查目录内容；确认需要修复后运行 `aps upgrade`。")
        return 2
    if not project_has_content(root):
        print("REFUSE  当前目录像是新项目或空目录。")
        recovery("resume 只接管已有项目，不负责初始化新项目。", "新项目运行 `aps init`。")
        return 2
    print("OK    正在接管已有项目；完成本次安装后，后续 `aps resume` 只恢复状态，不修改项目。")
    install(root, args.host, force_managed=False)
    return launch_host(root, args.host, handoff_prompt("resume", root), args.no_launch, require_plan_mode=True)


def cmd_rebaseline(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    if not root.is_dir() or not is_governed(root):
        print("REFUSE  rebaseline 需要已存在且受 APS 管理的项目。")
        recovery("当前目录没有可恢复的有效 APS 项目。", "先运行 `aps resume` 接管已有项目，或对新项目运行 `aps init`。")
        return 2
    if (boundary := project_boundary_error(root)):
        print(f"REFUSE  项目边界不安全：{boundary}")
        recovery("rebaseline 不会跟随链接、reparse point 或错误类型的项目边界写入文件。", "先移除或重命名冲突路径，再运行 `aps rebaseline --confirm`。")
        return 2
    if not args.confirm:
        print("REFUSE  rebaseline 会创建新的 Cycle，必须显式确认。")
        recovery("未检测到 `--confirm`，因此没有创建新 Cycle，也没有修改工作区。", "确认当前 Cycle 可重新审查后运行 `aps rebaseline --confirm`。")
        return 2
    manifest = read_manifest(root)
    path_error = boundary_error(root / ".ai" / "standard-manifest.json")
    if path_error:
        print(f"REFUSE  APS manifest 路径不安全：{path_error}")
        recovery("rebaseline 不能从链接或 reparse point 读取治理清单。", "先移除该路径碰撞，再运行 `aps upgrade` 修复 Standard。")
        return 2
    problems = manifest_problems(manifest)
    if problems:
        print(f"REFUSE  APS manifest 不可读或无效：{problems[0]}")
        recovery("无法确认当前 Standard 文件集合。", "先人工审查项目状态，再运行 `aps upgrade` 修复 Standard。")
        return 2
    marker_missing = missing_aps_markers(root)
    if marker_missing:
        print("REFUSE  APS 路由标记不完整。")
        recovery("AGENTS.md 或 .gitignore 的 APS 管理块不完整。", "先运行 `aps upgrade`，再重新确认 `aps rebaseline --confirm`。")
        return 2
    runtime, state_error = runtime_state(root)
    if state_error:
        print(f"REFUSE  Runtime state 无法严格解析：{state_error}")
        recovery("rebaseline 不能在损坏状态上推断当前 Cycle。", "运行 `aps doctor --standard-only`，修复第一项状态问题后再运行 `aps rebaseline --confirm`。")
        return 2
    if runtime is None:
        print("REFUSE  rebaseline 需要已初始化的运行状态。")
        recovery("当前项目尚未完成 Bootstrap，无法判断应从哪个 Cycle 重建。", "先在 Agent Host 完成 Bootstrap，再运行 `aps rebaseline --confirm`。")
        return 2
    _, governance_problems = runtime_governance_problems(root, runtime)
    if governance_problems:
        print_governance_failure(governance_problems[0], standard_only=True, marker="REFUSE")
        return 2
    if runtime["cycle"] != "CYCLE-001" and runtime["stage_status"] != "COMPLETE":
        print(f"REFUSE  当前 Cycle {runtime['cycle']} 尚未完成，不能再创建 Cycle。")
        recovery("非首个 Cycle 必须先完成当前生命周期。", "运行 `aps resume --no-launch` 恢复当前 Cycle，不要再次执行 rebaseline。")
        return 2
    if runtime["cycle"] != "CYCLE-001":
        if runtime["stage"] != 23 or runtime["stage_status"] != "COMPLETE":
            print(f"REFUSE  当前 Cycle {runtime['cycle']} 尚未完成 Stage 23 Cycle Review。")
            recovery("只有完成 Cycle Review 后才能建立新的 Rebaseline Cycle。", "运行 `aps resume --no-launch` 完成 Stage 23，再重新运行 `aps rebaseline --confirm`。")
            return 2
        if runtime["stage_type"] == "GATED" and runtime["gate_status"] != "PASS":
            print(f"REFUSE  当前 Cycle {runtime['cycle']} 的 Stage 23 Gate 尚未 PASS。")
            recovery("GATED Stage 23 必须先通过 Gate，不能用 rebaseline 绕过。", "运行 `aps resume --no-launch` 修复 Stage 23，再重新运行 `aps rebaseline --confirm`。")
            return 2
        if runtime["blockers"] or runtime["pending_decision_refs"]:
            print(f"REFUSE  当前 Cycle {runtime['cycle']} 仍有 blocker 或待决策。")
            recovery("Cycle Review 关闭前必须清除所有 blocker 和待决策。", "运行 `aps resume --no-launch` 处理阻塞项，再重新运行 `aps rebaseline --confirm`。")
            return 2
    if manifest.get("version") != STANDARD_VERSION:
        print(f"REFUSE  已安装 Standard 为 {manifest.get('version', 'unknown')}，需要先升级到 {STANDARD_VERSION}。")
        recovery("rebaseline 必须建立在当前 Standard 文件集合上。", "运行 `aps upgrade`，确认无冲突后再运行 `aps rebaseline --confirm`。")
        return 2
    missing = missing_managed_files(root, manifest)
    if missing:
        print("REFUSE  已安装 Standard 文件缺失或无效。")
        recovery("manifest 记录的托管文件无法全部找到。", "先运行 `aps upgrade` 修复文件，再运行 `aps rebaseline --confirm`。")
        return 2
    conflicts = manifest.get("local_modification_conflicts", [])
    if conflicts:
        print("REFUSE  存在未解决的托管文件冲突。")
        recovery("rebaseline 不会绕过本地 Standard 文件冲突。", "先人工合并 `.ai/incoming/<version>/` 对应文件，再运行 `aps upgrade`。")
        return 2
    modified = modified_managed_files(root, manifest)
    if modified:
        print(f"REFUSE  Standard 托管文件已被本地修改：{modified[0]}")
        recovery("rebaseline 必须建立在 manifest 对应的内置 Standard 文件上。", "运行 `aps upgrade` 保留新版本到 `.ai/incoming/<version>/`，人工合并后再运行 `aps rebaseline --confirm`。")
        return 2
    return launch_host(root, args.host, handoff_prompt("rebaseline", root), args.no_launch, require_plan_mode=True)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    host = args.host
    return run_doctor(root, host, strict_runtime=not args.standard_only)


def cmd_upgrade(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    if not root.is_dir():
        print(f"FAIL  项目目录不存在：{root}")
        recovery("upgrade 找不到指定项目目录。", "确认路径后重新运行 `aps upgrade <PROJECT>`。")
        return 2
    if (boundary := project_boundary_error(root)):
        print(f"REFUSE  项目边界不安全：{boundary}")
        recovery("APS 不会跟随链接、reparse point 或错误类型的项目边界写入文件。", "先移除或重命名冲突路径，再运行 `aps upgrade`。")
        return 2
    ancestor = governed_ancestor(root)
    if ancestor and not is_governed(root):
        print(f"REFUSE  当前目录是受 APS 管理项目下的未接管嵌套目录：{ancestor}")
        recovery("upgrade 不能在嵌套目录建立第二套治理边界。", "回到受治理项目根目录运行 `aps upgrade`。")
        return 2
    manifest_path = root / ".ai" / "standard-manifest.json"
    before_manifest = read_manifest(root)
    manifest_problems_found = manifest_path.exists() and bool(manifest_problems(before_manifest))
    if not manifest_path.exists() and not has_aps_artifacts(root):
        if project_has_content(root):
            print("REFUSE  当前项目尚未受 APS 管理，upgrade 不会越权接管。")
            recovery("普通旧项目必须先建立接管边界和 Bootstrap 路径。", "运行 `aps resume --no-launch` 接管已有项目。")
        else:
            print("REFUSE  当前目录为空，upgrade 不负责初始化新项目。")
            recovery("空目录没有可升级的 APS 安装。", "运行 `aps init --no-launch` 初始化新项目。")
        return 2
    if manifest_problems_found or (not manifest_path.exists() and has_aps_artifacts(root)):
        print("WARN  检测到 APS 半安装或损坏残留，upgrade 将只修复可识别的 Standard 文件。")
    before = before_manifest.get("version")
    result = install(root, args.host, args.force_managed)
    after = result["version"]
    if before == after and result["changed"] == 0 and not result["manifest_changed"]:
        if result["incoming"]:
            print(f"OK    Standard {after} 未变化；仍有 {len(result['incoming'])} 个托管文件冲突。")
        else:
            print(f"OK    当前已经是内置 Standard {after}。")
    else:
        print(f"OK    Standard {before or 'unmanaged'} -> {after}。")
    if result["incoming"]:
        print("WARN  本地修改的托管文件已保留到以下 incoming 路径：")
        for item in result["incoming"]:
            print(f"  - .ai/incoming/{after}/{Path(item).relative_to('.ai').as_posix()}")
        recovery("升级未自动合并本地托管文件，避免覆盖用户修改。", f"在 Host 中对比当前文件与 `.ai/incoming/{after}/`，手动合并后再运行 `aps doctor`；不要自动合并。")
    else:
        print("NEXT  Bootstrap/runtime state 可用后运行 `aps doctor`，再用 `aps status` 确认结果。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = project_path(args.project)
    if not root.is_dir():
        print(f"FAIL  项目目录不存在：{root}")
        recovery("status 找不到指定项目目录。", "确认路径后重新运行 `aps status <PROJECT>`。")
        return 2
    if (boundary := project_boundary_error(root)):
        print(f"Project: {root}")
        print(f"FAIL  项目边界不安全：{boundary}")
        recovery("APS 不会跟随链接、reparse point 或错误类型的项目边界读取状态。", "先移除或重命名冲突路径，再运行 `aps status`。")
        return 2
    manifest = read_manifest(root)
    manifest_path = root / ".ai" / "standard-manifest.json"
    manifest_present = manifest_path.exists() or manifest_path.is_symlink()
    state = root / ".ai" / "state.yaml"
    print(f"Project: {root}")
    if not manifest_present:
        if has_aps_artifacts(root):
            print("Governed: partial APS install（半安装）")
            print("REFUSE  检测到 APS 残留，但没有有效 manifest。")
            recovery("当前安装边界不完整，status 不会把半安装当作正常项目。", "运行 `aps upgrade` 修复可识别的 APS Standard 文件。")
            return 2
        print("Governed: no（是否受治理）")
        print("Runtime state: not initialized")
        if project_has_content(root):
            print("NEXT  运行 `aps resume --no-launch` 接管已有项目。")
        else:
            print("NEXT  运行 `aps init --no-launch` 初始化新项目。")
        return 0

    print("Governed: yes（是否受治理）")
    path_error = boundary_error(manifest_path)
    if path_error:
        print(f"FAIL  APS manifest 路径不安全：{path_error}")
        recovery("manifest 位于符号链接或 Windows reparse point 上。", "先移除该路径碰撞，再运行 `aps upgrade` 修复 Standard。")
        return 2
    problems = manifest_problems(manifest)
    if problems:
        print(f"FAIL  APS manifest 无效：{problems[0]}")
        recovery("无法从 `.ai/standard-manifest.json` 确认托管文件和版本。", "先人工审查项目状态，确认后运行 `aps upgrade`，不要运行 `aps init`。")
        return 2

    print(f"Standard: {manifest['version']}")
    if manifest["version"] != STANDARD_VERSION:
        print(f"FAIL  Standard 版本不匹配：当前 {manifest['version']}，内置 {STANDARD_VERSION}。")
        recovery("resume 不会隐式升级或覆盖项目中的 Standard 文件。", "运行 `aps upgrade`，确认无冲突后再运行 `aps status`。")
        return 2
    marker_missing = missing_aps_markers(root)
    if marker_missing:
        print(f"FAIL  APS 路由标记不完整：{marker_missing[0]}")
        recovery("AGENTS.md 或 .gitignore 的 APS 管理块缺失或不完整。", "运行 `aps upgrade` 修复路由标记后重试 `aps status`。")
        return 2
    missing = missing_managed_files(root, manifest)
    if missing:
        print(f"FAIL  Standard 托管文件缺失或无效：{missing[0]}")
        recovery("manifest 记录的托管文件无法全部验证。", "运行 `aps upgrade` 修复文件后重试 `aps status`。")
        return 2
    conflicts = manifest.get("local_modification_conflicts", [])
    print(f"Managed conflicts: {len(conflicts)}")
    if conflicts:
        print("REFUSE  托管文件存在未解决的本地修改冲突：")
        for item in conflicts:
            print(f"  - {item}")
        recovery("APS 不会自动合并本地 Standard 修改。", "先人工合并 `.ai/incoming/<version>/` 对应文件，再运行 `aps upgrade`。")
        return 2
    modified = modified_managed_files(root, manifest)
    if modified:
        print(f"FAIL  Standard 托管文件已被本地修改：{modified[0]}")
        recovery("当前文件内容与 manifest 记录的内置 Standard 不一致。", "运行 `aps upgrade` 将新版本放入 `.ai/incoming/<version>/`，人工合并后再运行 `aps upgrade`。")
        return 2

    state_exists = state.exists() or state.is_symlink()
    registry_path = root / ".ai" / "registry.yaml"
    registry_required = registry_path.exists() or registry_path.is_symlink()
    registry_required = registry_required or any(
        (root / relative).exists() or (root / relative).is_symlink()
        for relative in (".ai/project-profile.json", ".ai/audit/transitions.jsonl")
    )
    if registry_required:
        registry_issues = registry_problems(root)
        if registry_issues:
            print_governance_failure(
                governance_problem("registry", registry_issues[0], ".ai/registry.yaml"),
            )
            return 2
    if not state_exists:
        print("Runtime state: not initialized")
        profile, profile_error = load_project_profile(root)
        if profile is not None:
            print(f"Risk profile: {profile['risk_profile']}")
            print(f"Workstreams: {len(profile['workstreams'])}")
        elif profile_error and ((root / ".ai" / "project-profile.json").exists() or (root / ".ai" / "project-profile.json").is_symlink()):
            print_governance_failure(
                governance_problem("project_profile", profile_error, ".ai/project-profile.json"),
                action="在 Host 中按 `.ai/templates/project-profile.json` 修复 `.ai/project-profile.json`，再运行 `aps doctor --standard-only`。",
            )
            return 2
        print("NEXT  运行 `aps resume --no-launch`，让 Agent Host 完成 Bootstrap。")
        return 0
    runtime, state_error = runtime_state(root)
    if state_error:
        print(f"Runtime state: invalid（状态无效）")
        print(f"FAIL  {state_error}")
        recovery("状态损坏时 APS 不会默认判定为普通模式。", "运行 `aps doctor --standard-only`，修复第一项状态问题后再运行 `aps resume --no-launch`。")
        return 2
    print("Runtime state: present")
    assert runtime is not None
    risk_profile, governance_problems = profile_status(root, runtime)
    print(f"Risk profile: {risk_profile}")
    if governance_problems:
        print_governance_failure(governance_problems[0])
        return 2
    profile, _ = load_project_profile(root)
    if profile is not None:
        print(f"Workstreams: {len(profile['workstreams'])}")
    for line in _runtime_summary(root, include_profile=False):
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
    print("\nAI Project Standard（aps）\n")
    print(f"Project: {root}（项目目录）")
    if governed:
        print("Detected: 已检测到受 APS 管理的项目")
    elif existing:
        print("Detected: 已检测到已有项目")
    else:
        print("Detected: 新项目或空目录")
    print("\n1. 初始化新项目")
    print("2. 接管 / 恢复已有项目")
    print("3. 从 Stage 01 重新建立审查 Cycle")
    print("4. Doctor / 项目体检")
    print("5. 升级 Standard")
    print("6. 查看 Status / 状态")
    print("0. 退出")
    try:
        choice = input("\n请选择：").strip()
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
        print("REFUSE  无效选择。")
        print("NEXT  输入 1-6 执行操作，或输入 0 退出。")
        return 2
    if choice == "0":
        return 0
    if choice == "3":
        try:
            confirmation = input("确认创建新的 Cycle？输入 yes 确认，其他输入取消：").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nOK    已取消 rebaseline；未创建新 Cycle，工作区未改变。")
            return 0
        if confirmation not in {"y", "yes"}:
            print("OK    已取消 rebaseline；未创建新 Cycle，工作区未改变。")
            return 0
        mapping["3"].append("--confirm")
    return main(mapping[choice])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aps",
        description="APS（AI Project Standard）命令行工具：安装、接管、恢复和检查项目治理状态。",
        epilog=(
            "典型路径：\n"
            "  新项目：aps init --no-launch → 在 Host 执行 handoff → aps doctor\n"
            "  旧项目：aps resume --no-launch → 完成 Bootstrap → aps status\n"
            "  遇到阻塞：aps status → 按 NEXT 操作；需要恢复时运行 aps resume --no-launch\n"
            "  决策：aps decision request <REQUEST-FILE> → 当前对话分析 → aps decision answer DEC-001 A\n"
            "  研究：aps research brief <ARTIFACT>；完整报告仍保留在 Stage Artifact。\n"
            "  风险：Bootstrap 确认 NORMAL/LARGE/REGULATED 并写入 .ai/project-profile.json。\n"
            "  Release：Stage 20 边界补齐 .ai/release-readiness.json；Release approval 仍需用户确认，普通 Stage PASS 不需要额外确认。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"aps {__version__} (Standard {STANDARD_VERSION})")
    sub = p.add_subparsers(dest="command")

    def common(sp: argparse.ArgumentParser, default_project: str = ".") -> None:
        sp.add_argument("project", nargs="?", default=default_project, type=Path, help="项目目录，默认当前目录")
        sp.add_argument("--host", choices=HOSTS, default="codex", help="Agent Host：codex 或 generic")
        sp.add_argument("--force-managed", action="store_true", help="备份后替换本地修改的托管 Standard 文件")

    s = sub.add_parser("init", help="初始化新项目并输出 Agent handoff")
    common(s)
    s.add_argument("--no-launch", action="store_true", help="只安装并打印 handoff，不启动 Codex")
    s.add_argument("--no-git", action="store_true", help="新空目录中不初始化 Git")
    s.add_argument("--force-mode", action="store_true", help="已弃用；不能绕过已有项目保护")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("resume", help="接管或恢复已有项目")
    common(s)
    s.add_argument("--no-launch", action="store_true", help="只打印 handoff，不启动 Codex")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("rebaseline", help="从 Stage 01 开始新的完整审查 Cycle")
    common(s)
    s.add_argument("--confirm", action="store_true", help="确认创建新的 Cycle")
    s.add_argument("--no-launch", action="store_true", help="只打印 handoff，不启动 Codex")
    s.set_defaults(func=cmd_rebaseline)

    s = sub.add_parser("doctor", help="检查 Standard 和项目治理健康状态")
    s.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    s.add_argument("--host", choices=HOSTS, default="codex", help="Agent Host：codex 或 generic")
    s.add_argument("--standard-only", action="store_true", help="只检查已安装 Standard，不要求运行状态已初始化")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("upgrade", help="安装当前 aps CLI 内置的 Standard 版本")
    common(s)
    s.set_defaults(func=cmd_upgrade)

    s = sub.add_parser("status", help="查看项目治理、运行状态和唯一下一步")
    s.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("decision", help="登记、回答或取消结构化用户决策")
    decision_sub = s.add_subparsers(dest="decision_command", required=True)

    d = decision_sub.add_parser("request", help="登记待处理 Decision Request")
    d.add_argument("request_file", type=Path, help=".ai/cycles 下的 Decision Request JSON")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    d.set_defaults(func=cmd_decision_request)

    d = decision_sub.add_parser("list", help="列出待处理 Decision Request")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    d.set_defaults(func=cmd_decision_list)

    d = decision_sub.add_parser("show", help="查看 Decision Request")
    d.add_argument("reference", help="例如 DEC-001")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    d.set_defaults(func=cmd_decision_show)

    d = decision_sub.add_parser("answer", help="记录 Decision Request 的用户回答")
    d.add_argument("reference", help="例如 DEC-001")
    d.add_argument("answer", help="选项 ID、逗号分隔选项或自由文本")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    d.add_argument("--reason", default="", help="随决策记录的可选理由")
    d.set_defaults(func=cmd_decision_answer)

    d = decision_sub.add_parser("cancel", help="取消待处理 Decision Request")
    d.add_argument("reference", help="例如 DEC-001")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
    d.add_argument("--reason", default="", help="可选的取消原因")
    d.set_defaults(func=cmd_decision_cancel)

    s = sub.add_parser("research", help="展示经过字段校验的研究输出")
    research_sub = s.add_subparsers(dest="research_command", required=True)
    d = research_sub.add_parser("brief", help="从 Stage Artifact 展示 Research Brief")
    d.add_argument("artifact", type=Path, help=".ai/cycles 下的 Markdown Artifact")
    d.add_argument("project", nargs="?", default=".", type=Path, help="项目目录，默认当前目录")
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
        print("\nOK    已取消。")
        return 130
    except ProjectBoundaryError as exc:
        print(f"FAIL  项目边界不安全：{exc}", file=sys.stderr)
        print("原因：APS 不会跟随项目根目录的符号链接、reparse point 或错误路径。", file=sys.stderr)
        print(f"NEXT  移除或重命名冲突路径后重试：`{command_hint(argv)}`", file=sys.stderr)
        return 2
    except Exception as exc:
        command = getattr(args, "command", None)
        print(f"FAIL  {exc}", file=sys.stderr)
        if command in {"init", "resume", "upgrade", "status", "decision", "research"}:
            if command == "decision":
                cause = "Decision Request 或项目运行状态未通过校验。"
            elif command == "research":
                cause = "Research Artifact 路径、Research Brief 标识或必需字段未通过校验。"
            elif command == "init":
                cause = "安装或初始化过程中出现未满足的本地环境条件。"
            else:
                cause = "项目当前状态不满足该命令的安全前置条件。"
            print(f"原因：{cause}", file=sys.stderr)
            print(f"NEXT  修复上方问题后重新运行：`{command_hint(argv)}`", file=sys.stderr)
        return 1
