from __future__ import annotations

import re
from pathlib import Path

from .parser import parse_mdx


_DIRECTIVE_RE = re.compile(r"^(?P<fence>:{3,})(?P<type>[A-Za-z][\w-]*)(?P<attrs>\{.*\})?\s*$")
_TOP_LEVEL_DIRECTIVES = {"label", "book", "quiz", "folder", "geogebra", "assign", "forum", "sectionSummary"}
_ALL_DIRECTIVES = _TOP_LEVEL_DIRECTIVES | {"page", "question"}


def validate_mdx_file(path: str | Path) -> list[str]:
    source_path = Path(path)
    return validate_mdx_source(source_path.read_text(encoding="utf-8"), base_dir=source_path.parent)


def validate_mdx_source(source: str, *, base_dir: str | Path) -> list[str]:
    issues = _validate_directive_nesting(source)
    try:
        model = parse_mdx(source)
    except ValueError as exc:
        issues.append(str(exc))
        return issues

    base = Path(base_dir)
    for section in model.sections:
        for item in section.items:
            if item.type not in _TOP_LEVEL_DIRECTIVES:
                issues.append(f"Unsupported directive '{item.type}'")
            if item.type == "folder":
                for file_item in item.files:
                    _validate_asset_path(base, str(file_item["path"]), issues)
            if item.type == "geogebra" and item.attrs.get("file"):
                _validate_asset_path(base, str(item.attrs["file"]), issues)
    return _dedupe(issues)


def validate_mdx_file_or_raise(path: str | Path) -> None:
    issues = validate_mdx_file(path)
    if issues:
        raise ValueError(_format_issues(issues))


def _validate_asset_path(base_dir: Path, asset_path: str, issues: list[str]) -> None:
    path = Path(asset_path)
    if not path.is_absolute():
        path = base_dir / path
    if not path.exists():
        issues.append(f"Asset file does not exist: {asset_path}")


def _validate_directive_nesting(source: str) -> list[str]:
    issues: list[str] = []
    stack: list[tuple[str, str]] = []
    for line in source.splitlines():
        stripped = line.strip()
        while stack and stripped == stack[-1][1]:
            stack.pop()
        match = _DIRECTIVE_RE.match(line)
        if match is None:
            continue
        directive_type = match.group("type")
        parent = stack[-1][0] if stack else None
        if directive_type not in _ALL_DIRECTIVES:
            issues.append(f"Unsupported directive '{directive_type}'")
        if directive_type == "page" and parent != "book":
            issues.append("'page' directives are only allowed inside 'book'")
        if directive_type == "question" and parent != "quiz":
            issues.append("'question' directives are only allowed inside 'quiz'")
        if parent == "book" and directive_type != "page":
            issues.append(f"'{directive_type}' directives are not allowed inside 'book'")
        if parent == "quiz" and directive_type != "question":
            issues.append(f"'{directive_type}' directives are not allowed inside 'quiz'")
        stack.append((directive_type, match.group("fence")))
    return issues


def _dedupe(issues: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for issue in issues:
        if issue in seen:
            continue
        seen.add(issue)
        result.append(issue)
    return result


def _format_issues(issues: list[str]) -> str:
    return "MDX validation failed:\n" + "\n".join(f"- {issue}" for issue in issues)
