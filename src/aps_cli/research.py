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
        raise ResearchError("APS project state directory not found; run Bootstrap first")
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
        raise ResearchError("research artifact must be a Markdown file under .ai/cycles/")
    if not candidate.is_file():
        raise ResearchError(f"research artifact not found: {candidate}")
    return candidate


def _brief_section(text: str) -> str:
    heading = re.search(r"(?mi)^##(?!#)\s+Research Brief\s*$", text)
    if not heading:
        raise ResearchError("research artifact must contain a `## Research Brief` section")
    rest = text[heading.end() :]
    next_heading = re.search(r"(?mi)^##(?!#)\s+", rest)
    section = rest[: next_heading.start() if next_heading else None].strip()
    if not section:
        raise ResearchError("Research Brief section is empty")
    missing = [aliases[0] for aliases in REQUIRED_FIELDS if not any(alias.lower() in section.lower() for alias in aliases)]
    if missing:
        raise ResearchError(f"Research Brief is missing: {', '.join(missing)}")
    return section


def render_brief(project: Path, artifact: Path) -> int:
    root = _project_root(project)
    path = _artifact_path(root, artifact)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResearchError(f"cannot read research artifact {path}: {exc}") from exc
    section = _brief_section(text)
    print(f"Research Brief: {path.relative_to(root).as_posix()}\n")
    print(section)
    return 0
