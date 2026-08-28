from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .installer import STANDARD_VERSION_RE, assert_no_reparse


PROFILE_RELATIVE = Path(".ai/project-profile.json")
REGISTRY_RELATIVE = Path(".ai/registry.yaml")
TRANSITIONS_RELATIVE = Path(".ai/audit/transitions.jsonl")
RELEASE_READINESS_RELATIVE = Path(".ai/release-readiness.json")

PROFILE_SCHEMA_VERSION = 1
TRANSITION_SCHEMA_VERSION = 1
RELEASE_SCHEMA_VERSION = 1

RISK_PROFILES = {"NORMAL", "LARGE", "REGULATED"}
WORKSTREAM_STATUSES = {"ACTIVE", "PAUSED", "COMPLETE"}
STAGE_TYPES = {"GATED", "EXECUTION_LOOP", "OBSERVATION_LOOP", "ROUTER"}
STAGE_STATUSES = {"ACTIVE", "BLOCKED", "COMPLETE"}
GATE_STATUSES = {"PENDING", "PASS", "REVISE", "HOLD", "STOP"}
RELEASE_STATUSES = {"DRAFT", "READY", "RELEASED", "BLOCKED"}
CHECK_STATUSES = {"PASS", "FAIL", "PENDING", "SKIPPED"}
REGISTRY_STATUSES = {"DRAFT", "ACTIVE", "SUPERSEDED", "ARCHIVED", "DEPRECATED", "RETIRED"}
REGISTRY_LOAD_POLICIES = {
    "always-minimal",
    "stage",
    "task",
    "stage/task",
    "stage/on-demand",
    "ui-task",
    "trigger-only",
    "on-demand",
    "bootstrap/on-demand",
    "referenced-only",
    "bootstrap/runtime",
    "host-managed",
    "archive-never-default",
    "release-only",
}

_RELEASE_REQUIREMENTS_PATH = Path(__file__).resolve().parent / "bundle" / "package" / "tools" / "release-requirements.json"


def _load_profile_release_checks() -> dict[str, tuple[str, ...]]:
    try:
        raw = json.loads(_RELEASE_REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Release requirements are unavailable: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != RISK_PROFILES:
        raise RuntimeError("Release requirements must define NORMAL, LARGE, and REGULATED")
    checks: dict[str, tuple[str, ...]] = {}
    for profile, values in raw.items():
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value.strip() for value in values):
            raise RuntimeError(f"Release requirements for {profile} are invalid")
        checks[profile] = tuple(values)
    return checks


PROFILE_RELEASE_CHECKS = _load_profile_release_checks()

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$", re.ASCII)
WORKSTREAM_ID_RE = re.compile(r"^WS-[A-Z0-9][A-Z0-9_-]*$", re.ASCII)
TRANSITION_ID_RE = re.compile(r"^TRN-[A-Z0-9][A-Z0-9_-]*$", re.ASCII)
RELEASE_ID_RE = re.compile(r"^REL-[A-Z0-9][A-Z0-9_-]*$", re.ASCII)
CYCLE_RE = re.compile(r"^CYCLE-[0-9]{3,}$")


class GovernanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class GovernanceProblem:
    """A typed, non-persistent governance problem for CLI recovery routing."""

    code: str
    message: str
    path: str | None = None


def governance_problem(code: str, message: str, path: str | None = None) -> GovernanceProblem:
    return GovernanceProblem(code=code, message=message, path=path)


def _wrap_problems(code: str, messages: list[str], path: str | None = None) -> list[GovernanceProblem]:
    return [governance_problem(code, message, path) for message in messages]


def profile_path(root: Path) -> Path:
    return root / PROFILE_RELATIVE


def registry_path(root: Path) -> Path:
    return root / REGISTRY_RELATIVE


def transitions_path(root: Path) -> Path:
    return root / TRANSITIONS_RELATIVE


def release_readiness_path(root: Path) -> Path:
    return root / RELEASE_READINESS_RELATIVE


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_timestamp(value: object, label: str) -> None:
    if not _nonempty(value):
        raise GovernanceError(f"{label} 必须是非空 ISO 日期或时间")
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GovernanceError(f"{label} 不是有效 ISO 日期或时间：{value}") from exc


def _string_list(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise GovernanceError(f"{label} 必须是{'非空' if not allow_empty else ''}字符串列表")
    if any(not _nonempty(item) for item in value):
        raise GovernanceError(f"{label} 不能包含空字符串")
    return [str(item).strip() for item in value]


def _read_json(path: Path, label: str) -> dict[str, Any]:
    assert_no_reparse(path)
    if not path.is_file():
        raise GovernanceError(f"{label} 缺失：{path.as_posix()}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"{label} 无法解析：{exc}") from exc
    if not isinstance(value, dict):
        raise GovernanceError(f"{label} 必须是 JSON 对象")
    return value


def _validate_workstreams(value: object, risk_profile: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GovernanceError("project-profile.json 的 workstreams 必须是数组")
    if risk_profile in {"LARGE", "REGULATED"} and not value:
        raise GovernanceError(f"风险级别 {risk_profile} 必须至少定义一个 workstream")
    allowed = {"id", "name", "status", "owner", "scope", "depends_on"}
    seen: set[str] = set()
    workstreams: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise GovernanceError("project-profile.json 的 workstreams 项必须是对象")
        unknown = sorted(set(item) - allowed)
        if unknown:
            raise GovernanceError(f"workstream 包含未知字段：{', '.join(unknown)}")
        required = {"id", "name", "status"}
        missing = sorted(required - set(item))
        if missing:
            raise GovernanceError(f"workstream 缺少字段：{', '.join(missing)}")
        identifier = item["id"]
        if not isinstance(identifier, str) or not WORKSTREAM_ID_RE.fullmatch(identifier):
            raise GovernanceError(f"workstream id 无效：{identifier}")
        if identifier in seen:
            raise GovernanceError(f"workstream id 重复：{identifier}")
        seen.add(identifier)
        if not _nonempty(item["name"]):
            raise GovernanceError(f"workstream {identifier} 的 name 不能为空")
        if item["status"] not in WORKSTREAM_STATUSES:
            raise GovernanceError(f"workstream {identifier} 的 status 无效：{item['status']}")
        if risk_profile == "REGULATED" and not _nonempty(item.get("owner")):
            raise GovernanceError(f"REGULATED workstream {identifier} 必须填写 owner")
        if "owner" in item and item["owner"] is not None and not _nonempty(item["owner"]):
            raise GovernanceError(f"workstream {identifier} 的 owner 不能为空")
        if "scope" in item and item["scope"] is not None and not _nonempty(item["scope"]):
            raise GovernanceError(f"workstream {identifier} 的 scope 不能为空")
        depends_on = _string_list(item.get("depends_on", []), f"workstream {identifier} 的 depends_on")
        if identifier in depends_on:
            raise GovernanceError(f"workstream {identifier} 不能依赖自己")
        workstreams.append({**item, "depends_on": depends_on})
    for item in workstreams:
        unknown_deps = sorted(set(item["depends_on"]) - seen)
        if unknown_deps:
            raise GovernanceError(f"workstream {item['id']} 依赖不存在的 workstream：{', '.join(unknown_deps)}")

    graph = {item["id"]: item["depends_on"] for item in workstreams}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise GovernanceError(f"workstream 依赖存在循环：{identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)
    return workstreams


def validate_project_profile(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"$schema", "schema_version", "risk_profile", "reviewed_at", "review_triggers", "workstreams"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise GovernanceError(f"project-profile.json 包含未知字段：{', '.join(unknown)}")
    required = {"schema_version", "risk_profile", "reviewed_at", "review_triggers", "workstreams"}
    missing = sorted(required - set(data))
    if missing:
        raise GovernanceError(f"project-profile.json 缺少字段：{', '.join(missing)}")
    if data["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise GovernanceError(f"project-profile.json 的 schema_version 必须是 {PROFILE_SCHEMA_VERSION}")
    risk_profile = data["risk_profile"]
    if risk_profile not in RISK_PROFILES:
        raise GovernanceError(f"project-profile.json 的 risk_profile 无效：{risk_profile}")
    _iso_timestamp(data["reviewed_at"], "project-profile.json 的 reviewed_at")
    _string_list(data["review_triggers"], "project-profile.json 的 review_triggers", allow_empty=False)
    workstreams = _validate_workstreams(data["workstreams"], risk_profile)
    return {**data, "workstreams": workstreams}


def load_project_profile(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = profile_path(root)
    if not path.exists() and not path.is_symlink():
        return None, f"缺少项目风险基线：{PROFILE_RELATIVE.as_posix()}"
    try:
        return validate_project_profile(_read_json(path, "project-profile.json")), None
    except (GovernanceError, RuntimeError) as exc:
        return None, str(exc)


def _registry_scalar(value: str) -> object:
    value = value.strip()
    if not value:
        return {}
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _registry_line_value(value: str) -> str:
    quoted = False
    quote = ""
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            if not quoted:
                quoted = True
                quote = char
            elif quote == char:
                quoted = False
        elif char == "#" and not quoted and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _parse_registry_subset(text: str) -> dict[str, Any]:
    """Parse the small Registry YAML mapping/sequence subset without PyYAML."""
    root: dict[str, Any] = {}
    lines = text.splitlines()
    stack: list[tuple[int, Any]] = [(-1, root)]
    for line_number, raw_line in enumerate(lines, 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise GovernanceError(f"registry.yaml 第 {line_number} 行不能使用 Tab 缩进")
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = _registry_line_value(raw_line[indent:])
        if not content:
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if content.startswith("-"):
            if not isinstance(parent, list):
                raise GovernanceError(f"registry.yaml 第 {line_number} 行列表位置无效")
            item = content[1:].strip()
            if not item:
                raise GovernanceError(f"registry.yaml 第 {line_number} 行列表项为空")
            parent.append(_registry_scalar(item))
            continue
        if ":" not in content or not isinstance(parent, dict):
            raise GovernanceError(f"registry.yaml 第 {line_number} 行不是受支持的映射字段")
        key, raw_value = (part.strip() for part in content.split(":", 1))
        if not key or not ID_RE.fullmatch(key):
            raise GovernanceError(f"registry.yaml 第 {line_number} 行字段名无效：{key}")
        if key in parent:
            raise GovernanceError(f"registry.yaml 第 {line_number} 行字段重复：{key}")
        if raw_value.strip():
            value = _registry_scalar(raw_value)
        else:
            next_indent = None
            next_content = ""
            for lookahead in lines[line_number:]:
                if not lookahead.strip() or lookahead.lstrip().startswith("#"):
                    continue
                next_indent = len(lookahead) - len(lookahead.lstrip(" "))
                next_content = _registry_line_value(lookahead[next_indent:])
                break
            value = [] if next_indent is not None and next_indent > indent and next_content.startswith("-") else {}
        parent[key] = value
        if not raw_value.strip():
            stack.append((indent, value))
    return root


def _read_registry(path: Path) -> dict[str, Any]:
    assert_no_reparse(path)
    if not path.is_file():
        raise GovernanceError(f"Registry 缺失或不是普通文件：{REGISTRY_RELATIVE.as_posix()}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GovernanceError(f"Registry 无法读取：{exc}") from exc
    return _parse_registry_subset(text)


def _safe_registry_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    value = value.strip()
    if any(ord(char) < 32 for char in value) or ":" in value:
        return False
    parts = value.split("/")
    if value.endswith("/"):
        parts.pop()
    return not value.startswith("/") and bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def validate_registry(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"schema_version", "standard_version", "revision", "sources", "artifacts", "dependencies", "critical_skills"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise GovernanceError(f"registry.yaml 包含未知字段：{', '.join(unknown)}")
    required = allowed
    missing = sorted(required - set(data))
    if missing:
        raise GovernanceError(f"registry.yaml 缺少字段：{', '.join(missing)}")
    if isinstance(data["schema_version"], bool) or data["schema_version"] != 1:
        raise GovernanceError("registry.yaml.schema_version 必须是 1")
    if not isinstance(data["standard_version"], str) or not STANDARD_VERSION_RE.fullmatch(data["standard_version"]):
        raise GovernanceError(f"registry.yaml.standard_version 无效：{data['standard_version']}")
    if isinstance(data["revision"], bool) or not isinstance(data["revision"], int) or data["revision"] < 1:
        raise GovernanceError("registry.yaml.revision 必须是正整数")
    sources = data["sources"]
    if not isinstance(sources, dict) or not sources:
        raise GovernanceError("registry.yaml.sources 必须是非空对象")
    required_source = {"domain", "path", "status", "load_policy"}
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            raise GovernanceError(f"registry.yaml.sources 的 source id 无效：{source_id}")
        if not isinstance(source, dict):
            raise GovernanceError(f"registry.yaml.sources.{source_id} 必须是对象")
        missing_source = sorted(required_source - set(source))
        if missing_source:
            raise GovernanceError(f"registry.yaml.sources.{source_id} 缺少字段：{', '.join(missing_source)}")
        if not _nonempty(source["domain"]):
            raise GovernanceError(f"registry.yaml.sources.{source_id}.domain 不能为空")
        if not _safe_registry_path(source["path"]):
            raise GovernanceError(f"registry.yaml.sources.{source_id}.path 不是安全的项目相对路径：{source['path']}")
        if source["status"] not in REGISTRY_STATUSES:
            raise GovernanceError(f"registry.yaml.sources.{source_id}.status 无效：{source['status']}")
        if source["load_policy"] not in REGISTRY_LOAD_POLICIES:
            raise GovernanceError(f"registry.yaml.sources.{source_id}.load_policy 无效：{source['load_policy']}")
        for optional in ("version", "last_verified"):
            if optional in source and source[optional] is not None and not _nonempty(source[optional]):
                raise GovernanceError(f"registry.yaml.sources.{source_id}.{optional} 不能为空")
    for field in ("artifacts", "dependencies", "critical_skills"):
        if not isinstance(data[field], dict):
            raise GovernanceError(f"registry.yaml.{field} 必须是对象")
    return data


def registry_problems(root: Path) -> list[str]:
    path = registry_path(root)
    if not path.exists() and not path.is_symlink():
        return [f"缺少 Registry：{REGISTRY_RELATIVE.as_posix()}（请按 `.ai/templates/registry.yaml` 修复）"]
    try:
        validate_registry(_read_registry(path))
        return []
    except (GovernanceError, OSError, UnicodeError, RuntimeError) as exc:
        return [str(exc)]


def _state_view(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GovernanceError(f"{label} 必须是对象")
    allowed = {"cycle", "stage", "stage_type", "stage_status", "gate_status"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GovernanceError(f"{label} 包含未知字段：{', '.join(unknown)}")
    required = {"cycle", "stage", "stage_type", "stage_status", "gate_status"}
    missing = sorted(required - set(value))
    if missing:
        raise GovernanceError(f"{label} 缺少字段：{', '.join(missing)}")
    cycle = value["cycle"]
    if not isinstance(cycle, str) or not CYCLE_RE.fullmatch(cycle):
        raise GovernanceError(f"{label}.cycle 无效：{cycle}")
    stage = value["stage"]
    if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= 23:
        raise GovernanceError(f"{label}.stage 必须是 1 到 23 的整数")
    stage_type = value["stage_type"]
    if stage_type not in STAGE_TYPES:
        raise GovernanceError(f"{label}.stage_type 无效：{stage_type}")
    stage_status = value["stage_status"]
    if stage_status not in STAGE_STATUSES:
        raise GovernanceError(f"{label}.stage_status 无效：{stage_status}")
    gate_status = value["gate_status"]
    if stage_type == "GATED" and gate_status not in GATE_STATUSES:
        raise GovernanceError(f"{label}.gate_status 无效：{gate_status}")
    if stage_type != "GATED" and gate_status is not None:
        raise GovernanceError(f"{label} 非 GATED Stage 的 gate_status 必须是 null")
    if stage_type == "GATED":
        if gate_status == "PASS" and stage_status != "COMPLETE":
            raise GovernanceError(f"{label} 的 Gate PASS 必须对应 COMPLETE Stage")
        if gate_status != "PASS" and stage_status == "COMPLETE":
            raise GovernanceError(f"{label} 的 COMPLETE Stage 必须对应 Gate PASS")
    return {key: value[key] for key in required}


def _validate_transition(record: dict[str, Any], index: int) -> dict[str, Any]:
    allowed = {"schema_version", "event_id", "recorded_at", "revision", "actor", "reason", "from_state", "to_state", "evidence_refs", "decision_refs", "change_refs", "adoption"}
    unknown = sorted(set(record) - allowed)
    if unknown:
        raise GovernanceError(f"Transition {index} 包含未知字段：{', '.join(unknown)}")
    required = {"schema_version", "event_id", "recorded_at", "revision", "actor", "reason", "from_state", "to_state", "evidence_refs"}
    missing = sorted(required - set(record))
    if missing:
        raise GovernanceError(f"Transition {index} 缺少字段：{', '.join(missing)}")
    if record["schema_version"] != TRANSITION_SCHEMA_VERSION:
        raise GovernanceError(f"Transition {index} 的 schema_version 无效")
    if not isinstance(record["event_id"], str) or not TRANSITION_ID_RE.fullmatch(record["event_id"]):
        raise GovernanceError(f"Transition {index} 的 event_id 无效")
    _iso_timestamp(record["recorded_at"], f"Transition {index} 的 recorded_at")
    revision = record["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise GovernanceError(f"Transition {index} 的 revision 必须是正整数")
    if not _nonempty(record["actor"]):
        raise GovernanceError(f"Transition {index} 的 actor 不能为空")
    if not _nonempty(record["reason"]):
        raise GovernanceError(f"Transition {index} 的 reason 不能为空")
    from_state = record["from_state"]
    if from_state is not None:
        _state_view(from_state, f"Transition {index} 的 from_state")
    to_state = _state_view(record["to_state"], f"Transition {index} 的 to_state")
    adoption = record.get("adoption", False)
    if not isinstance(adoption, bool):
        raise GovernanceError(f"Transition {index} 的 adoption 必须是布尔值")
    evidence_refs = _string_list(record["evidence_refs"], f"Transition {index} 的 evidence_refs")
    for key in ("decision_refs", "change_refs"):
        if key in record:
            _string_list(record[key], f"Transition {index} 的 {key}")
    normalized_from = _state_view(from_state, f"Transition {index} 的 from_state") if from_state is not None else None
    if adoption and normalized_from is not None:
        raise GovernanceError(f"Transition {index} 的 adoption 仅允许用于首条空状态记录")
    if normalized_from is not None and normalized_from == to_state:
        raise GovernanceError(f"Transition {index} 的 from_state 和 to_state 不能相同")
    if normalized_from is None or normalized_from != to_state:
        if not evidence_refs:
            raise GovernanceError(f"Transition {index} 的状态变更必须包含 evidence_refs")
    if normalized_from is not None and normalized_from["stage"] != to_state["stage"]:
        if normalized_from["stage_status"] != "COMPLETE":
            raise GovernanceError(f"Transition {index} 离开 Stage 前必须 COMPLETE")
        if normalized_from["stage_type"] == "GATED" and normalized_from["gate_status"] != "PASS":
            raise GovernanceError(f"Transition {index} 离开 GATED Stage 前必须 Gate PASS")
    if normalized_from is not None and normalized_from["cycle"] != to_state["cycle"]:
        if normalized_from["stage"] != 23 or normalized_from["stage_status"] != "COMPLETE" or (normalized_from["stage_type"] == "GATED" and normalized_from["gate_status"] != "PASS"):
            raise GovernanceError(f"Transition {index} 开始新 Cycle 前必须完成并通过 Stage 23")
        if to_state["stage"] != 1:
            raise GovernanceError(f"Transition {index} 新 Cycle 必须从 Stage 1 开始")
    return {**record, "from_state": normalized_from, "to_state": to_state, "adoption": adoption}


def validate_transition_log(root: Path, state: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    path = transitions_path(root)
    required = True
    if not path.exists() and not path.is_symlink():
        return [f"缺少 Transition 审计记录：{TRANSITIONS_RELATIVE.as_posix()}"] if required else []
    try:
        assert_no_reparse(path)
        if not path.is_file():
            return [f"Transition 审计路径不是普通文件：{TRANSITIONS_RELATIVE.as_posix()}"]
        records: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except (UnicodeError, json.JSONDecodeError) as exc:
                return [f"Transition 审计记录第 {index} 行无法解析：{exc}"]
            if not isinstance(value, dict):
                return [f"Transition 审计记录第 {index} 行必须是 JSON 对象"]
            records.append(_validate_transition(value, index))
        if not records:
            return [f"Transition 审计记录为空：{TRANSITIONS_RELATIVE.as_posix()}"] if required else []
        event_ids: set[str] = set()
        previous_revision = 0
        previous_time = ""
        previous_to: dict[str, Any] | None = None
        for index, record in enumerate(records, 1):
            if record["adoption"] and index != 1:
                return ["已有项目接管标记 adoption 只能出现在 Transition 审计首条记录"]
            if record["event_id"] in event_ids:
                return [f"Transition 审计记录 event_id 重复：{record['event_id']}"]
            event_ids.add(record["event_id"])
            if record["revision"] <= previous_revision:
                return [f"Transition 审计记录 revision 未单调递增：第 {index} 行"]
            if previous_time and record["recorded_at"] < previous_time:
                return [f"Transition 审计记录时间未单调递增：第 {index} 行"]
            if previous_to is not None and record["from_state"] != previous_to:
                return [f"Transition 审计链断裂：第 {index} 行 from_state 不等于上一条 to_state"]
            previous_revision = record["revision"]
            previous_time = record["recorded_at"]
            previous_to = record["to_state"]
        current = _state_view(
            {key: state.get(key) for key in ("cycle", "stage", "stage_type", "stage_status", "gate_status")},
            "当前 state",
        )
        if records[0]["from_state"] is not None:
            return ["Transition 审计链第一条记录必须从空状态开始"]
        if records[0]["to_state"]["stage"] != 1 and not records[0]["adoption"]:
            return ["Transition 审计链从非 Stage 1 开始必须显式标记 adoption: true"]
        if previous_to != current:
            return ["Transition 审计记录的最后状态与 `.ai/state.yaml` 不一致"]
        if records[-1]["revision"] > state["revision"]:
            return ["Transition 审计记录 revision 不能大于 `.ai/state.yaml` 的 revision"]
        return []
    except (OSError, UnicodeError, GovernanceError, RuntimeError) as exc:
        return [str(exc)]


def _validate_check(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise GovernanceError(f"{label} 必须是对象")
    allowed = {"status", "evidence_refs", "note"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GovernanceError(f"{label} 包含未知字段：{', '.join(unknown)}")
    if value.get("status") not in CHECK_STATUSES:
        raise GovernanceError(f"{label}.status 无效：{value.get('status')}")
    _string_list(value.get("evidence_refs"), f"{label}.evidence_refs", allow_empty=False)
    if "note" in value and value["note"] is not None and not _nonempty(value["note"]):
        raise GovernanceError(f"{label}.note 不能为空")


def validate_release_readiness(data: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    allowed = {"$schema", "schema_version", "release_id", "profile", "status", "target_environment", "checks", "workstream_refs", "reviewed_at", "approved_by"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise GovernanceError(f"release-readiness.json 包含未知字段：{', '.join(unknown)}")
    required = {"schema_version", "release_id", "profile", "status", "target_environment", "checks", "workstream_refs", "reviewed_at", "approved_by"}
    missing = sorted(required - set(data))
    if missing:
        raise GovernanceError(f"release-readiness.json 缺少字段：{', '.join(missing)}")
    if data["schema_version"] != RELEASE_SCHEMA_VERSION:
        raise GovernanceError(f"release-readiness.json 的 schema_version 必须是 {RELEASE_SCHEMA_VERSION}")
    if not isinstance(data["release_id"], str) or not RELEASE_ID_RE.fullmatch(data["release_id"]):
        raise GovernanceError(f"release-readiness.json 的 release_id 无效：{data['release_id']}")
    if data["profile"] != profile["risk_profile"]:
        raise GovernanceError("release-readiness.json 的 profile 与项目风险基线不一致")
    if data["status"] not in RELEASE_STATUSES:
        raise GovernanceError(f"release-readiness.json 的 status 无效：{data['status']}")
    if not _nonempty(data["target_environment"]):
        raise GovernanceError("release-readiness.json 的 target_environment 不能为空")
    if not isinstance(data["checks"], dict):
        raise GovernanceError("release-readiness.json 的 checks 必须是对象")
    for key, value in data["checks"].items():
        if not isinstance(key, str) or not ID_RE.fullmatch(key):
            raise GovernanceError(f"release-readiness.json 的 check 名称无效：{key}")
        _validate_check(value, f"release-readiness.json 的 check {key}")
    workstream_ids = {item["id"] for item in profile["workstreams"]}
    refs = _string_list(data["workstream_refs"], "release-readiness.json 的 workstream_refs")
    unknown_refs = sorted(set(refs) - workstream_ids)
    if unknown_refs:
        raise GovernanceError(f"release-readiness.json 引用了不存在的 workstream：{', '.join(unknown_refs)}")
    if data["reviewed_at"] is not None:
        _iso_timestamp(data["reviewed_at"], "release-readiness.json 的 reviewed_at")
    if data["approved_by"] is not None and not _nonempty(data["approved_by"]):
        raise GovernanceError("release-readiness.json 的 approved_by 不能为空")
    if profile["risk_profile"] in {"LARGE", "REGULATED"} and data["status"] in {"READY", "RELEASED"}:
        if data["reviewed_at"] is None or data["approved_by"] is None:
            raise GovernanceError("LARGE/REGULATED Release READY 必须填写 reviewed_at 和 approved_by")
    return data


def release_readiness_problems(root: Path, state: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    stage = state["stage"]
    gate = state["gate_status"]
    if stage < 20 or (stage == 20 and gate != "PASS"):
        return []
    path = release_readiness_path(root)
    if not path.exists() and not path.is_symlink():
        return [f"缺少 Release readiness：{RELEASE_READINESS_RELATIVE.as_posix()}"]
    try:
        data = _read_json(path, "release-readiness.json")
        validate_release_readiness(data, profile)
        required = PROFILE_RELEASE_CHECKS[profile["risk_profile"]]
        for check in required:
            value = data["checks"].get(check)
            if not isinstance(value, dict) or value.get("status") != "PASS":
                return [f"Release readiness 的必需检查未 PASS：{check}"]
        if data["status"] not in {"READY", "RELEASED"}:
            return [f"Release readiness 尚未 READY：当前状态 {data['status']}"]
        return []
    except (GovernanceError, OSError, UnicodeError, RuntimeError) as exc:
        return [str(exc)]


def prd_snapshot_problems(root: Path, state: dict[str, Any]) -> list[str]:
    stages_root = root / ".ai" / "cycles" / state["cycle"] / "stages"
    try:
        assert_no_reparse(stages_root)
        if not stages_root.is_dir():
            return []
        snapshots = list(stages_root.rglob("08_PRD_SNAPSHOT.md"))
    except (OSError, RuntimeError) as exc:
        return [f"无法扫描当前 Cycle 的 PRD Snapshot：{exc}"]
    problems: list[str] = []
    for path in snapshots:
        try:
            assert_no_reparse(path)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, RuntimeError) as exc:
            problems.append(f"PRD Snapshot 无法读取：{path.relative_to(root).as_posix()}（{exc}）")
            continue
        status = re.search(r"(?mi)^\s*-\s*Current Status\s*[：:]\s*(ACTIVE|DRAFT|SUPERSEDED)\s*$", text)
        if not status or status.group(1) != "ACTIVE":
            continue
        revision = re.search(r"(?mi)^\s*-\s*Source State Revision\s*[：:]\s*(\d+)\s*$", text)
        relative = path.relative_to(root).as_posix()
        if not revision:
            problems.append(f"PRD Snapshot 缺少 Source State Revision：{relative}")
        elif int(revision.group(1)) != state["revision"]:
            problems.append(f"PRD Snapshot 可能过期：{relative} 的 Source State Revision={revision.group(1)}，当前 state revision={state['revision']}")
    return problems


def runtime_governance_problems(root: Path, state: dict[str, Any]) -> tuple[dict[str, Any] | None, list[GovernanceProblem]]:
    profile, error = load_project_profile(root)
    if error:
        return None, [governance_problem("project_profile", error, PROFILE_RELATIVE.as_posix())]
    assert profile is not None
    problems = _wrap_problems("registry", registry_problems(root), REGISTRY_RELATIVE.as_posix())
    problems.extend(
        _wrap_problems(
            "transition_audit",
            validate_transition_log(root, state, profile),
            TRANSITIONS_RELATIVE.as_posix(),
        )
    )
    problems.extend(
        _wrap_problems(
            "release_readiness",
            release_readiness_problems(root, state, profile),
            RELEASE_READINESS_RELATIVE.as_posix(),
        )
    )
    problems.extend(_wrap_problems("prd_snapshot", prd_snapshot_problems(root, state)))
    return profile, problems


def profile_status(root: Path, state: dict[str, Any] | None) -> tuple[str, list[GovernanceProblem]]:
    profile, error = load_project_profile(root)
    if error:
        path = profile_path(root)
        if state is None and not path.exists() and not path.is_symlink():
            return "not initialized", []
        return "invalid", [governance_problem("project_profile", error, PROFILE_RELATIVE.as_posix())]
    assert profile is not None
    problems = (
        _wrap_problems("registry", registry_problems(root), REGISTRY_RELATIVE.as_posix())
        + _wrap_problems(
            "transition_audit",
            validate_transition_log(root, state, profile),
            TRANSITIONS_RELATIVE.as_posix(),
        )
        if state is not None
        else []
    )
    if state is not None:
        problems.extend(
            _wrap_problems(
                "release_readiness",
                release_readiness_problems(root, state, profile),
                RELEASE_READINESS_RELATIVE.as_posix(),
            )
        )
        problems.extend(_wrap_problems("prd_snapshot", prd_snapshot_problems(root, state)))
    return profile["risk_profile"], problems
