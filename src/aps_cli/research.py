from __future__ import annotations

import re
from pathlib import Path

from .installer import assert_no_reparse


class ResearchError(RuntimeError):
    pass


REQUIRED_FIELDS = (
    ("研究问题 / 范围", r"研究问题(?:\s*/\s*范围)?|Question\s*/\s*Scope"),
    ("方法与来源（含日期）", r"方法(?:与来源（含日期）)?|Method\s*/\s*Sources"),
    ("关键发现", r"关键发现|Key\s+Findings"),
    ("结论 / 建议", r"结论(?:\s*/\s*建议)?|Conclusion\s*/\s*Recommendation"),
    ("未确定项", r"未确定(?:项)?|Uncertainty\s*/\s*Unknowns"),
    ("待决策项", r"待决策(?:项)?|Pending\s+Decisions"),
)


def _project_root(project: Path) -> Path:
    candidate = project.expanduser()
    assert_no_reparse(candidate, allow_ancestor_links=True)
    root = candidate.resolve()
    if not root.is_dir() or not (root / ".ai").is_dir():
        raise ResearchError("APS 项目状态目录不存在；请先在 Agent Host 完成 Bootstrap")
    assert_no_reparse(root)
    assert_no_reparse(root / ".ai")
    return root


def _artifact_path(root: Path, artifact: Path) -> Path:
    candidate = artifact.expanduser()
    if not candidate.is_absolute():
        from_cwd = Path.cwd() / candidate
        assert_no_reparse(from_cwd, allow_ancestor_links=True)
        from_cwd = from_cwd.resolve()
        if from_cwd.is_file():
            candidate = from_cwd
        else:
            project_candidate = root / candidate
            assert_no_reparse(project_candidate)
            candidate = project_candidate.resolve()
    else:
        assert_no_reparse(candidate, allow_ancestor_links=True)
        candidate = candidate.resolve()
    assert_no_reparse(candidate)
    cycles_path = root / ".ai" / "cycles"
    assert_no_reparse(cycles_path)
    cycles = cycles_path.resolve()
    if cycles not in candidate.parents or candidate.suffix.lower() != ".md":
        raise ResearchError("Research Artifact 必须是 `.ai/cycles/` 下的 Markdown 文件")
    if not candidate.is_file():
        raise ResearchError(f"找不到 Research Artifact：{candidate}")
    return candidate


def _brief_section(text: str) -> tuple[str, list[str]]:
    heading = re.search(r"(?mi)^##(?!#)\s+Research Brief\s*$", text)
    if not heading:
        return text.strip(), ["缺少 `## Research Brief` 小节；将展示整个 Artifact"]
    rest = text[heading.end() :]
    next_heading = re.search(r"(?mi)^##(?!#)\s+", rest)
    section = rest[: next_heading.start() if next_heading else None].strip()
    if not section:
        return "", ["Research Brief 小节为空"]
    missing: list[str] = []
    for label, pattern in REQUIRED_FIELDS:
        matches = re.findall(
            rf"(?mi)^[ \t]*(?:[-*][ \t]+)?(?:{pattern})[ \t]*[:：][ \t]*(\S.*?)[ \t]*$",
            section,
        )
        if len(matches) > 1:
            raise ResearchError(f"Research Brief 字段重复：{label}；请只保留一个结构化字段")
        if not matches or not matches[0].strip():
            missing.append(label)
    if missing:
        return section, [f"Research Brief 缺少字段：{'、'.join(missing)}"]
    return section, []


def render_brief(project: Path, artifact: Path) -> int:
    root = _project_root(project)
    path = _artifact_path(root, artifact)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ResearchError(f"无法读取 Research Artifact {path}：{exc}") from exc
    section, warnings = _brief_section(text)
    print(f"Research Brief: {path.relative_to(root).as_posix()}（研究摘要）\n")
    for warning in warnings:
        print(f"WARN  {warning}")
    print(section or "（Artifact 暂无可展示内容）")
    print("\nNEXT  以上是当前 Artifact 的可用摘要；完整研究报告仍保留在 Stage Artifact。")
    return 0
