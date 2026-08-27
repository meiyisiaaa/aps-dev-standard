from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .installer import atomic_write


DECISION_ID_RE = re.compile(r"^DEC-[A-Z0-9][A-Z0-9_-]*$")
CYCLE_RE = re.compile(r"^CYCLE-[0-9]{3,}$")
INPUT_TYPES = {
    "single_select",
    "multi_select",
    "free_text",
    "number",
    "ranking",
    "approval",
    "matrix",
}
STATE_ORDER = [
    "schema_version",
    "standard_version",
    "revision",
    "cycle",
    "stage",
    "stage_type",
    "stage_status",
    "gate_status",
    "current_goal",
    "scope_ref",
    "blockers",
    "pending_decision_refs",
    "active_change_refs",
    "major_risk_refs",
    "next_action",
    "updated_at",
    "updated_by",
]


class DecisionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("#"):
        return None
    if value in {"null", "~"}:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith('"') or value.startswith("'"):
        try:
            return json.loads(value) if value.startswith('"') else value[1:-1].replace("''", "'")
        except json.JSONDecodeError:
            return value.strip('"\'')
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return [item.strip().strip('"\'') for item in value[1:-1].split(",") if item.strip()]
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if re.fullmatch(r"-?[0-9]+\.[0-9]+", value):
        return float(value)
    return value


def _parse_state(text: str) -> dict[str, Any]:
    # ponytail: parse only the constrained APS state shape; refuse unknown nested YAML instead of guessing and risking governance data loss.
    lines = text.splitlines()
    data: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1].isspace():
            raise DecisionError("state.yaml 顶层缩进格式不受支持")
        key, separator, raw = line.partition(":")
        if not separator or not key.strip():
            raise DecisionError(f"state.yaml 存在无效行：{line}")
        key = key.strip()
        raw = raw.strip()
        if raw:
            data[key] = _parse_scalar(raw)
            index += 1
            continue

        items: list[Any] = []
        cursor = index + 1
        while cursor < len(lines):
            child = lines[cursor]
            if not child.strip() or child.lstrip().startswith("#"):
                cursor += 1
                continue
            indentation = len(child) - len(child.lstrip(" "))
            if indentation == 0:
                break
            if indentation != 2 or not child.lstrip().startswith("-"):
                raise DecisionError(f"state.yaml 的 {key} 包含不受支持的嵌套数据")
            item_raw = child.lstrip()[1:].strip()
            if not item_raw:
                raise DecisionError(f"state.yaml 的 {key} 存在空列表项")
            if ":" not in item_raw:
                items.append(_parse_scalar(item_raw))
                cursor += 1
                continue
            item_key, item_separator, item_value = item_raw.partition(":")
            if not item_separator or not item_key.strip():
                raise DecisionError(f"state.yaml 的 {key} 存在无效列表项")
            item: dict[str, Any] = {item_key.strip(): _parse_scalar(item_value)}
            cursor += 1
            while cursor < len(lines):
                nested = lines[cursor]
                if not nested.strip() or nested.lstrip().startswith("#"):
                    cursor += 1
                    continue
                nested_indent = len(nested) - len(nested.lstrip(" "))
                if nested_indent <= 2:
                    break
                if nested_indent != 4:
                    raise DecisionError(f"state.yaml 的 {key} 包含不受支持的 blocker 嵌套数据")
                nested_key, nested_separator, nested_value = nested.strip().partition(":")
                if not nested_separator or not nested_key:
                    raise DecisionError(f"state.yaml 的 {key} 包含无效 blocker 字段")
                item[nested_key.strip()] = _parse_scalar(nested_value)
                cursor += 1
            items.append(item)
        data[key] = items
        index = cursor
    return data


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:+-]+", text) and text.lower() not in {"null", "true", "false"}:
        return text
    return json.dumps(text, ensure_ascii=False)


def _dump_state(data: dict[str, Any]) -> str:
    keys = [key for key in STATE_ORDER if key in data]
    keys += [key for key in data if key not in keys]
    lines: list[str] = []
    for key in keys:
        value = data[key]
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    item_keys = list(item)
                    first = item_keys[0]
                    lines.append(f"  - {first}: {_yaml_scalar(item[first])}")
                    for item_key in item_keys[1:]:
                        item_value = item[item_key]
                        if isinstance(item_value, (dict, list)):
                            lines.append(f"    {item_key}: {json.dumps(item_value, ensure_ascii=False)}")
                        else:
                            lines.append(f"    {item_key}: {_yaml_scalar(item_value)}")
                else:
                    lines.append(f"  - {_yaml_scalar(item)}")
            continue
        if isinstance(value, (dict, list)):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def _load_state(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / ".ai" / "state.yaml"
    if not path.is_file():
        raise DecisionError("项目运行状态缺失；请先完成 Bootstrap")
    try:
        data = _parse_state(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DecisionError(f"无法读取 state.yaml：{exc}") from exc
    required = {"revision", "cycle", "stage", "stage_type", "stage_status", "gate_status", "blockers", "pending_decision_refs"}
    missing = sorted(required - set(data))
    if missing:
        raise DecisionError(f"state.yaml 缺少必需字段：{', '.join(missing)}")
    if not isinstance(data["revision"], int) or data["revision"] < 1:
        raise DecisionError("state.yaml 的 revision 必须是正整数")
    if not isinstance(data["blockers"], list) or not isinstance(data["pending_decision_refs"], list):
        raise DecisionError("state.yaml 的 blockers 和 pending_decision_refs 必须是列表")
    return path, data


def load_runtime_state(project: Path) -> dict[str, Any]:
    root = _root(project)
    _, data = _load_state(root)
    return data


@contextmanager
def _decision_lock(root: Path) -> Iterator[None]:
    path = root / ".ai" / ".decision.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
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
            raise DecisionError("另一个 APS 决策更新正在进行") from exc
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


def _root(project: Path) -> Path:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise DecisionError(f"项目目录不存在：{root}")
    if not (root / ".ai").is_dir():
        raise DecisionError(f"APS 项目状态目录不存在：{root / '.ai'}")
    return root


def _validate_request(data: Any, *, pending_only: bool = True) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DecisionError("Decision Request 必须是 JSON 对象")
    ref = data.get("id")
    if not isinstance(ref, str) or not DECISION_ID_RE.fullmatch(ref):
        raise DecisionError("Decision Request 的 id 必须匹配 DEC-*")
    schema_version = data.get("schema_version")
    if schema_version not in {1, 2}:
        raise DecisionError("Decision Request 的 schema_version 必须是 1 或 2")
    status = data.get("status")
    if status not in {"PENDING", "RESOLVED", "CANCELLED"}:
        raise DecisionError("Decision Request 的 status 无效")
    if pending_only and status != "PENDING":
        raise DecisionError("只有 status=PENDING 的 Decision Request 才能登记")
    if not isinstance(data.get("cycle"), str) or not CYCLE_RE.fullmatch(data["cycle"]):
        raise DecisionError("Decision Request 的 cycle 无效")
    if not isinstance(data.get("stage"), int) or not 1 <= data["stage"] <= 23:
        raise DecisionError("Decision Request 的 stage 必须在 1 到 23 之间")
    for key in ("question", "why_now"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise DecisionError(f"Decision Request 缺少必需字段：{key}")
    input_type = data.get("input_type")
    if input_type not in INPUT_TYPES:
        raise DecisionError(f"不支持的 decision input_type：{input_type}")
    options = data.get("options")
    if not isinstance(options, list):
        raise DecisionError("Decision Request 的 options 必须是数组")
    option_ids: list[str] = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("id"), str) or not isinstance(option.get("title"), str):
            raise DecisionError("每个决策选项都必须包含 id 和 title")
        option_id = option["id"]
        if option_id in option_ids:
            raise DecisionError(f"决策选项 id 重复：{option_id}")
        option_ids.append(option_id)
        if schema_version == 2:
            tradeoffs = option.get("tradeoffs")
            valid_tradeoffs = (
                isinstance(tradeoffs, str) and bool(tradeoffs.strip())
            ) or (
                isinstance(tradeoffs, list)
                and bool(tradeoffs)
                and all(isinstance(item, str) and item.strip() for item in tradeoffs)
            )
            if not valid_tradeoffs:
                raise DecisionError(f"决策选项 {option_id} 必须包含 tradeoffs（取舍）")
    if input_type in {"single_select", "multi_select", "ranking", "approval"} and not option_ids:
        raise DecisionError(f"decision input_type {input_type} 必须包含 options")
    recommended = data.get("recommended")
    if recommended is not None and recommended not in option_ids:
        raise DecisionError("Decision Request 的 recommended option 不在 options 中")
    if schema_version == 2:
        if "recommended" not in data:
            raise DecisionError("schema_version=2 的 Decision Request 必须包含 recommended option")
        card = data.get("decision_card")
        if not isinstance(card, dict):
            raise DecisionError("schema_version=2 的 Decision Request 必须包含 decision_card")
        impact = card.get("impact")
        if not isinstance(impact, dict) or any(
            not isinstance(impact.get(key), str) or not impact[key].strip()
            for key in ("code", "documentation", "time")
        ):
            raise DecisionError("decision_card.impact 必须包含 code、documentation 和 time")
        if not isinstance(card.get("confirmation_method"), str) or not card["confirmation_method"].strip():
            raise DecisionError("decision_card 必须包含 confirmation_method")
    for key in ("evidence_refs", "affected_areas"):
        if key in data and (not isinstance(data[key], list) or not all(isinstance(item, str) for item in data[key])):
            raise DecisionError(f"Decision Request 的 {key} 必须是字符串数组")
    return data


def _request_path(root: Path, path: Path) -> Path:
    resolved = path.expanduser().resolve()
    cycles = (root / ".ai" / "cycles").resolve()
    if cycles not in resolved.parents or resolved.suffix.lower() != ".json":
        raise DecisionError("Decision Request 必须是 `.ai/cycles/` 下的 JSON 文件")
    return resolved


def _read_request(path: Path, *, pending_only: bool = True) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionError(f"无法读取 Decision Request {path}：{exc}") from exc
    return _validate_request(data, pending_only=pending_only)


def _find_request(root: Path, ref: str) -> Path:
    if not DECISION_ID_RE.fullmatch(ref):
        raise DecisionError("决策引用必须匹配 DEC-*")
    cycles = (root / ".ai" / "cycles").resolve()
    matches = sorted(cycles.glob(f"**/decision-requests/{ref}.json"))
    if not matches:
        raise DecisionError(f"找不到 Decision Request：{ref}")
    if len(matches) > 1:
        raise DecisionError(f"Decision Request 重复：{ref}")
    return _request_path(root, matches[0])


def _blocker_ref(item: Any) -> str | None:
    return item.get("ref") if isinstance(item, dict) and isinstance(item.get("ref"), str) else None


def _save_state(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, _dump_state(data).encode("utf-8"))


def _bump_state(data: dict[str, Any], actor: str) -> None:
    data["revision"] += 1
    data["updated_at"] = _now()
    data["updated_by"] = actor


def register_request(project: Path, request_file: Path) -> int:
    root = _root(project)
    path = _request_path(root, request_file)
    with _decision_lock(root):
        request = _read_request(path)
        state_path, state = _load_state(root)
        if request["cycle"] != state.get("cycle") or request["stage"] != state.get("stage"):
            raise DecisionError("Decision Request 与当前 active Cycle/Stage 不匹配")
        refs = [ref for ref in state["pending_decision_refs"] if isinstance(ref, str)]
        if request["id"] in refs:
            print(f"OK    decision already pending（决策已登记）: {request['id']}")
            print(f"NEXT  在当前对话运行 `aps decision show {request['id']}`，确认 Decision Card 后再回答。")
            return 0
        if any(_blocker_ref(item) == request["id"] for item in state["blockers"]):
            raise DecisionError(f"Decision Request 已存在 blocker，但 state 没有 pending 引用：{request['id']}")
        refs.append(request["id"])
        state["pending_decision_refs"] = refs
        state["blockers"].append({"type": "user_decision", "ref": request["id"]})
        if state["stage_type"] == "GATED":
            state["gate_status"] = "PENDING"
        else:
            state["stage_status"] = "BLOCKED"
        _bump_state(state, "aps-decision")
        _save_state(state_path, state)
    print(f"OK    decision pending（已登记待决策）: {request['id']}")
    print(
        "NEXT  当前对话下一步：先展示 decision card（说明 why now、每个选项的 pros/cons、代码/文档/时间影响和确认方式），"
        f"再运行 `aps decision answer {request['id']} <ANSWER>`。"
    )
    print("WARN  用户选择不等于 Gate PASS；仍需完成对应 Artifact、Validation 和当前 Gate 条件。")
    return 0


def _display_answer(request: dict[str, Any], answer: str) -> tuple[list[str], str]:
    answer = answer.strip()
    if not answer:
        raise DecisionError("决策回答不能为空")
    input_type = request["input_type"]
    option_ids = [option["id"] for option in request["options"]]
    if input_type in {"single_select", "approval"}:
        selected = [answer]
        if answer not in option_ids:
            if request.get("allow_custom"):
                return [], f"自定义: {answer}"
            raise DecisionError(f"回答必须是以下选项之一：{', '.join(option_ids)}")
        return selected, answer
    if input_type in {"multi_select", "ranking"}:
        selected = [item.strip() for item in answer.split(",") if item.strip()]
        if not selected or len(set(selected)) != len(selected) or any(item not in option_ids for item in selected):
            raise DecisionError(f"回答必须是逗号分隔的选项列表：{', '.join(option_ids)}")
        return selected, ", ".join(selected)
    if input_type == "number":
        try:
            float(answer)
        except ValueError as exc:
            raise DecisionError("数字型决策回答必须是数字") from exc
    return [], answer


def _decision_exists(log_path: Path, ref: str) -> bool:
    if not log_path.is_file():
        return False
    return bool(re.search(rf"(?m)^##\s+{re.escape(ref)}\s*$", log_path.read_text(encoding="utf-8")))


def _decision_entry(request: dict[str, Any], selected: list[str], display: str, reason: str, date: str) -> str:
    options = "\n".join(
        f"- {option['id']}: {option['title']}" + (f" — {option['summary']}" if option.get("summary") else "")
        for option in request["options"]
    )
    affected = ", ".join(request.get("affected_areas", [])) or "未指定"
    reason_text = reason.strip() or f"用户确认：{display}"
    tradeoff_items: list[str] = []
    for option in request["options"]:
        if option["id"] not in selected:
            continue
        value = option.get("tradeoffs")
        if isinstance(value, list):
            tradeoff_items.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            tradeoff_items.append(str(value).strip())
    tradeoff = "; ".join(tradeoff_items) or "见对应 Stage Artifact"
    card = request.get("decision_card")
    card_lines = ""
    if isinstance(card, dict) and isinstance(card.get("impact"), dict):
        impact = card["impact"]
        card_lines = (
            f"Impact: Code: {impact.get('code', '未指定')}; "
            f"Documentation: {impact.get('documentation', '未指定')}; "
            f"Time: {impact.get('time', '未指定')}\n"
            f"Confirmation: {card.get('confirmation_method', '未指定')}\n"
        )
    return (
        f"## {request['id']}\n\n"
        f"Date: {date}\n"
        f"Problem: {request['question']}\n\n"
        f"Options:\n{options}\n\n"
        f"Decision: {display}\n"
        f"Reason: {reason_text}\n"
        f"Trade-off: {tradeoff}\n"
        f"{card_lines}"
        f"Affected Areas: {affected}\n"
        f"Revisit Condition: 由 Change Control 或新的有效证据触发。\n\n"
    )


def answer_request(project: Path, ref: str, answer: str, reason: str = "") -> int:
    root = _root(project)
    request_path = _find_request(root, ref)
    log_path = root / ".ai" / "decisions.md"
    with _decision_lock(root):
        request = _read_request(request_path)
        selected, display = _display_answer(request, answer)
        state_path, state = _load_state(root)
        pending = [item for item in state["pending_decision_refs"] if isinstance(item, str)]
        if ref not in pending:
            if _decision_exists(log_path, ref):
                print(f"OK    decision already recorded（决策已记录）；需要清理 state：{ref}")
            else:
                raise DecisionError(f"state.yaml 中没有待处理的 Decision Request：{ref}")

        date = _now()
        if not _decision_exists(log_path, ref):
            old = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
            separator = "\n" if old.endswith("\n") else "\n\n"
            atomic_write(log_path, (old + separator + _decision_entry(request, selected, display, reason, date)).encode("utf-8"))

        request["status"] = "RESOLVED"
        request["selected_option_ids"] = selected
        request["answer"] = answer
        request["reason"] = reason
        request["resolved_at"] = date
        atomic_write(request_path, (json.dumps(request, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

        state["pending_decision_refs"] = [item for item in pending if item != ref]
        state["blockers"] = [item for item in state["blockers"] if _blocker_ref(item) != ref]
        if state["stage_type"] != "GATED" and not state["blockers"]:
            state["stage_status"] = "ACTIVE"
        _bump_state(state, "aps-decision")
        _save_state(state_path, state)
    print(f"OK    decision recorded（已记录回答）: {ref} = {display}")
    print("WARN  用户选择不等于 Gate PASS；决策只解除对应 blocker，不自动通过 Gate。")
    print("NEXT  完成对应 Artifact 和 Validation 后运行 `aps status`，按当前 Transition Contract 更新 Gate。")
    return 0


def cancel_request(project: Path, ref: str, reason: str = "") -> int:
    root = _root(project)
    request_path = _find_request(root, ref)
    log_path = root / ".ai" / "decisions.md"
    with _decision_lock(root):
        request = _read_request(request_path)
        state_path, state = _load_state(root)
        pending = [item for item in state["pending_decision_refs"] if isinstance(item, str)]
        if ref not in pending:
            raise DecisionError(f"state.yaml 中没有待处理的 Decision Request：{ref}")

        date = _now()
        cancellation_reason = reason.strip() or "用户取消该决策请求"
        if not _decision_exists(log_path, ref):
            old = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
            separator = "\n" if old.endswith("\n") else "\n\n"
            entry = _decision_entry(request, [], "CANCELLED", cancellation_reason, date)
            atomic_write(log_path, (old + separator + entry).encode("utf-8"))

        request["status"] = "CANCELLED"
        request["reason"] = cancellation_reason
        request["cancelled_at"] = date
        atomic_write(request_path, (json.dumps(request, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

        state["pending_decision_refs"] = [item for item in pending if item != ref]
        state["blockers"] = [item for item in state["blockers"] if _blocker_ref(item) != ref]
        if state["stage_type"] != "GATED" and not state["blockers"]:
            state["stage_status"] = "ACTIVE"
        _bump_state(state, "aps-decision")
        _save_state(state_path, state)
    print(f"OK    decision cancelled（已取消决策）: {ref}")
    print("NEXT  如果决策仍然需要，创建新的 Decision Request；否则运行 `aps status` 确认剩余 blocker。")
    return 0


def list_requests(project: Path) -> int:
    root = _root(project)
    _, state = _load_state(root)
    refs = [ref for ref in state["pending_decision_refs"] if isinstance(ref, str)]
    if not refs:
        print("No pending decisions（没有待处理决策）。")
        print("NEXT  如果当前 Stage 需要用户选择，创建并登记新的 Decision Request。")
        return 0
    for ref in refs:
        path = _find_request(root, ref)
        request = _read_request(path)
        print(f"{ref}: {request['question']} [{request['input_type']}]")
    return 0


def show_request(project: Path, ref: str) -> int:
    root = _root(project)
    path = _find_request(root, ref)
    print(json.dumps(_read_request(path, pending_only=False), ensure_ascii=False, indent=2))
    return 0
