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
    assert_no_reparse(candidate)
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
        assert_no_reparse(from_cwd)
        from_cwd = from_cwd.resolve()
        candidate = from_cwd if from_cwd.is_file() else (root / candidate).resolve()
    else:
        assert_no_reparse(candidate)
        candidate = candidate.resolve()
    cycles_path = root / ".ai" / "cycles"
    assert_no_reparse(cycles_path)
    cycles = cycles_path.resolve()
    if cycles not in candidate.parents or candidate.suffix.lower() != ".md":
        raise ResearchError("Research Artifact 必须是 `.ai/cycles/` 下的 Markdown 文件")
    if not candidate.is_file():
        raise ResearchError(f"找不到 Research Artifact：{candidate}")
    return candidate


def _brief_section(text: str) -> str:
    heading = re.search(r"(?mi)^##(?!#)\s+Research Brief\s*$", text)
    if not heading:
        raise ResearchError("Research Artifact 必须包含稳定标识 `## Research Brief` 小节")
    rest = text[heading.end() :]
    next_heading = re.search(r"(?mi)^##(?!#)\s+", rest)
    section = rest[: next_heading.start() if next_heading else None].strip()
    if not section:
        raise ResearchError("Research Brief 小节为空；请补充研究摘要")
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
        fields = "、".join(missing)
        template = "\n".join(f"{label}：<请填写非空内容>" for label, _ in REQUIRED_FIELDS)
        raise ResearchError(
            f"Research Brief is missing: {fields}（研究摘要缺少字段；字段必须以标签开头并包含非空内容，请补齐后重试）\n"
            "请复制并填写以下修复模板：\n"
            "```markdown\n"
            f"{template}\n"
            "```"
        )
    return section


def render_brief(project: Path, artifact: Path) -> int:
    root = _project_root(project)
    path = _artifact_path(root, artifact)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ResearchError(f"无法读取 Research Artifact {path}：{exc}") from exc
    section = _brief_section(text)
    print(f"Research Brief: {path.relative_to(root).as_posix()}（研究摘要）\n")
    print(section)
    print("\nNEXT  以上是当前对话可展示的摘要；完整研究报告仍保留在 Stage Artifact。")
    return 0
