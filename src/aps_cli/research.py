from __future__ import annotations

import re
from pathlib import Path


class ResearchError(RuntimeError):
    pass


REQUIRED_FIELDS = (
    ("研究问题", "Question", "Scope"),
    ("方法", "Method", "Sources"),
    ("关键发现", "Key Findings", "Findings"),
    ("结论", "Conclusion", "Recommendation"),
    ("未确定", "Uncertainty", "Unknowns"),
    ("待决策", "Pending Decisions", "Decisions"),
)


def _project_root(project: Path) -> Path:
    root = project.expanduser().resolve()
    if not root.is_dir() or not (root / ".ai").is_dir():
        raise ResearchError("APS 项目状态目录不存在；请先在 Agent Host 完成 Bootstrap")
    return root


def _artifact_path(root: Path, artifact: Path) -> Path:
    candidate = artifact.expanduser()
    if not candidate.is_absolute():
        from_cwd = (Path.cwd() / candidate).resolve()
        candidate = from_cwd if from_cwd.is_file() else (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    cycles = (root / ".ai" / "cycles").resolve()
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
    missing = [aliases[0] for aliases in REQUIRED_FIELDS if not any(alias.lower() in section.lower() for alias in aliases)]
    if missing:
        fields = ", ".join(missing)
        raise ResearchError(f"Research Brief is missing: {fields}（研究摘要缺少字段，请补齐后重试）")
    return section


def render_brief(project: Path, artifact: Path) -> int:
    root = _project_root(project)
    path = _artifact_path(root, artifact)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResearchError(f"无法读取 Research Artifact {path}：{exc}") from exc
    section = _brief_section(text)
    print(f"Research Brief: {path.relative_to(root).as_posix()}（研究摘要）\n")
    print(section)
    print("\nNEXT  以上是当前对话可展示的摘要；完整研究报告仍保留在 Stage Artifact。")
    return 0
