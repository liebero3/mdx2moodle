from __future__ import annotations

import re
import shlex
from typing import Any

from .model import AnswerModel, CourseModel, MoodleItem, MoodleSection, QuestionModel


_DIRECTIVE_RE = re.compile(r"^(?P<fence>:{3,})(?P<type>[A-Za-z][\w-]*)(?P<attrs>\{.*\})?\s*$")
_HEADING_RE = re.compile(r"^# (?P<title>.*?)(?:\s+(?P<attrs>\{.*\}))?\s*$")
_SUBSECTION_RE = re.compile(r"^## (?P<title>.*?)(?:\s+(?P<attrs>\{.*\}))?\s*$")
_ANSWER_RE = re.compile(r"^\s*-\s+\[(?P<mark>[ xX])\]\s+(?P<text>.*)$")
_ASSET_RE = re.compile(r"^\s*-\s+(?P<path>.+?)\s*$")
_ENTRY_RE = re.compile(r"^\s*-\s+(?P<text>.*?)(?:\s+(?P<attrs>\{.*\}))?\s*$")
_BOARD_COLUMN_RE = re.compile(r"^-\s+(?P<text>.*?)(?:\s+(?P<attrs>\{.*\}))?\s*$")
_BOARD_NOTE_RE = re.compile(r"^\s+-\s+(?P<text>.*?)(?:\s+(?P<attrs>\{.*\}))?\s*$")


def parse_mdx(source: str) -> CourseModel:
    frontmatter, body = _split_frontmatter(source)
    meta = _parse_simple_yaml(frontmatter)
    course = dict(meta.get("course") or {})
    backup = dict(meta.get("backup") or {})
    format_options = dict(meta.get("tiles") or {})
    sections = _parse_sections(body)
    return CourseModel(course=course, backup=backup, sections=sections, format_options=format_options)


def _split_frontmatter(source: str) -> tuple[str, str]:
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("MDX source must start with YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    raise ValueError("Frontmatter is not closed with ---")


def _parse_sections(body: str) -> list[MoodleSection]:
    lines = body.splitlines()
    sections: list[MoodleSection] = []
    current: MoodleSection | None = None
    index = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING_RE.match(line)
        if heading:
            attrs = _parse_attrs(heading.group("attrs") or "")
            index = int(attrs["index"]) if "index" in attrs else index + 1
            title = str(attrs.get("moodle_title") if "moodle_title" in attrs else heading.group("title").strip())
            section_id = str(attrs.get("id") or f"section-{index:02d}")
            current = MoodleSection(id=section_id, index=index, title=title, attrs=attrs)
            sections.append(current)
            i += 1
            continue
        subsection = _SUBSECTION_RE.match(line)
        if subsection and current is not None:
            attrs = _parse_attrs(subsection.group("attrs") or "")
            index = int(attrs["index"]) if "index" in attrs else index + 1
            title = str(attrs.get("moodle_title") if "moodle_title" in attrs else subsection.group("title").strip())
            section_id = str(attrs.get("id") or f"subsection-{index:02d}")
            item_id = str(attrs.get("item_id") or attrs.get("itemid") or f"subsection_{_start_line_id(i)}")
            item_attrs = dict(attrs)
            item_attrs["target_section_id"] = section_id
            current.items.append(MoodleItem(id=item_id, type="subsection", title=title, attrs=item_attrs))
            section_attrs = dict(attrs)
            section_attrs["subsection"] = True
            section_attrs["parent_item_id"] = item_id
            sections.append(MoodleSection(id=section_id, index=index, title=title, attrs=section_attrs))
            i += 1
            continue
        if current is None:
            i += 1
            continue
        if line.startswith("summary:"):
            current.summary = line.partition(":")[2].strip()
            i += 1
            continue
        directive = _DIRECTIVE_RE.match(line)
        if directive:
            item, i = _parse_directive(lines, i)
            if item.type == "sectionSummary":
                current.summary = item.body.strip()
            else:
                current.items.append(item)
            continue
        i += 1
    return sections


def _parse_directive(lines: list[str], start: int) -> tuple[MoodleItem, int]:
    match = _DIRECTIVE_RE.match(lines[start])
    if match is None:
        raise ValueError(f"Expected directive at line {start + 1}")
    fence = match.group("fence")
    item_type = match.group("type")
    attrs = _parse_attrs(match.group("attrs") or "")
    end = start + 1
    body_lines: list[str] = []
    while end < len(lines):
        if lines[end].strip() == fence:
            break
        body_lines.append(lines[end])
        end += 1
    if end >= len(lines):
        raise ValueError(f"Directive {item_type} starting at line {start + 1} is not closed")
    body = "\n".join(body_lines)
    item_id = str(attrs.get("id") or f"{item_type}_{start + 1}")
    title = str(attrs.get("title") or item_id)
    item = MoodleItem(id=item_id, type=item_type, title=title, attrs=attrs, body=body)
    if item_type == "book":
        item.pages = _parse_book_pages(body)
    if item_type == "quiz":
        item.questions = _parse_quiz_questions(body)
    if item_type == "folder":
        item.body, item.files = _parse_folder_body(body)
    if item_type == "choice":
        item.body, item.options = _parse_entry_body(body, default_key="maxanswers", default_start=1)
    if item_type == "board":
        item.body, item.columns = _parse_board_body(body)
    if item_type == "questionnaire":
        item.body, item.survey_questions = _parse_questionnaire_body(body)
    return item, end + 1


def _start_line_id(line_index: int) -> str:
    return f"{line_index + 1:02d}"


def _parse_book_pages(body: str) -> list[dict[str, Any]]:
    lines = body.splitlines()
    pages: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        match = _DIRECTIVE_RE.match(lines[i])
        if match and match.group("type") == "page":
            fence = match.group("fence")
            attrs = _parse_attrs(match.group("attrs") or "")
            end = i + 1
            body_lines: list[str] = []
            while end < len(lines):
                if lines[end].strip() == fence:
                    break
                body_lines.append(lines[end])
                end += 1
            if end >= len(lines):
                raise ValueError(f"Book page starting at nested line {i + 1} is not closed")
            page = dict(attrs)
            page["title"] = str(attrs.get("title") or f"Page {len(pages) + 1}")
            page["content"] = "\n".join(body_lines)
            page["subchapter"] = int(attrs.get("subchapter", 0))
            pages.append(page)
            i = end + 1
            continue
        i += 1
    return pages


def _parse_quiz_questions(body: str) -> list[QuestionModel]:
    lines = body.splitlines()
    questions: list[QuestionModel] = []
    i = 0
    while i < len(lines):
        match = _DIRECTIVE_RE.match(lines[i])
        if match and match.group("type") == "question":
            fence = match.group("fence")
            attrs = _parse_attrs(match.group("attrs") or "")
            end = i + 1
            body_lines: list[str] = []
            while end < len(lines):
                if lines[end].strip() == fence:
                    break
                body_lines.append(lines[end])
                end += 1
            if end >= len(lines):
                raise ValueError(f"Quiz question starting at nested line {i + 1} is not closed")
            questions.append(_question_from_attrs_and_body(attrs, body_lines, len(questions) + 1))
            i = end + 1
            continue
        i += 1
    return questions


def _parse_folder_body(body: str) -> tuple[str, list[dict[str, Any]]]:
    intro_lines: list[str] = []
    files: list[dict[str, Any]] = []
    for line in body.splitlines():
        match = _ASSET_RE.match(line)
        if match:
            path = match.group("path").strip()
            files.append({"path": path, "filename": path.rsplit("/", 1)[-1]})
            continue
        if files and not line.strip():
            continue
        intro_lines.append(line)
    return "\n".join(intro_lines).strip(), files


def _parse_entry_body(
    body: str,
    *,
    default_key: str | None = None,
    default_start: int = 1,
) -> tuple[str, list[dict[str, Any]]]:
    intro_lines: list[str] = []
    entries: list[dict[str, Any]] = []
    for line in body.splitlines():
        match = _ENTRY_RE.match(line)
        if match:
            entry = _parse_attrs(match.group("attrs") or "")
            entry["text"] = match.group("text").strip()
            if default_key is not None and default_key not in entry:
                entry[default_key] = default_start + len(entries)
            entries.append(entry)
            continue
        if entries and not line.strip():
            continue
        intro_lines.append(line)
    return "\n".join(intro_lines).strip(), entries


def _parse_board_body(body: str) -> tuple[str, list[dict[str, Any]]]:
    intro_lines: list[str] = []
    columns: list[dict[str, Any]] = []
    for line in body.splitlines():
        note_match = _BOARD_NOTE_RE.match(line)
        if note_match and columns:
            note = _parse_attrs(note_match.group("attrs") or "")
            note["content"] = note_match.group("text").strip()
            columns[-1].setdefault("notes", []).append(note)
            continue
        column_match = _BOARD_COLUMN_RE.match(line)
        if column_match:
            column = _parse_attrs(column_match.group("attrs") or "")
            column["text"] = column_match.group("text").strip()
            column["notes"] = []
            columns.append(column)
            continue
        if columns and not line.strip():
            continue
        intro_lines.append(line)
    return "\n".join(intro_lines).strip(), columns


def _parse_questionnaire_body(body: str) -> tuple[str, list[dict[str, Any]]]:
    lines = body.splitlines()
    intro_lines: list[str] = []
    questions: list[dict[str, Any]] = []
    i = 0
    seen_question = False
    while i < len(lines):
        match = _DIRECTIVE_RE.match(lines[i])
        if match and match.group("type") == "q":
            seen_question = True
            fence = match.group("fence")
            attrs = _parse_attrs(match.group("attrs") or "")
            end = i + 1
            body_lines: list[str] = []
            while end < len(lines):
                if lines[end].strip() == fence:
                    break
                body_lines.append(lines[end])
                end += 1
            if end >= len(lines):
                raise ValueError(f"Questionnaire question starting at nested line {i + 1} is not closed")
            questions.append(_questionnaire_question_from_attrs_and_body(attrs, body_lines, len(questions) + 1))
            i = end + 1
            continue
        if not seen_question:
            intro_lines.append(lines[i])
        i += 1
    return "\n".join(intro_lines).strip(), questions


def _questionnaire_question_from_attrs_and_body(
    attrs: dict[str, Any],
    body_lines: list[str],
    fallback_position: int,
) -> dict[str, Any]:
    content_lines: list[str] = []
    choices: list[dict[str, Any]] = []
    seen_choice = False
    for line in body_lines:
        match = _ENTRY_RE.match(line)
        if match:
            seen_choice = True
            choice = _parse_attrs(match.group("attrs") or "")
            choice["content"] = match.group("text").strip()
            choices.append(choice)
            continue
        if seen_choice and not line.strip():
            continue
        if not seen_choice:
            content_lines.append(line)
    qtype = str(attrs.get("type") or "text")
    question = {
        "id": str(attrs.get("id") or f"questionnaire_q_{fallback_position:02d}"),
        "type": qtype,
        "name": str(attrs.get("name") or ""),
        "content": "\n".join(content_lines).strip() or str(attrs.get("content") or ""),
        "position": int(attrs.get("position", fallback_position)),
        "required": bool(attrs.get("required", False)),
        "length": int(attrs.get("length", 0)),
        "precise": int(attrs.get("precise", 0)),
        "deleted": str(attrs.get("deleted", "n")),
        "extradata": attrs.get("extradata"),
        "choices": choices,
    }
    for key, value in attrs.items():
        if key not in question and key not in {"title"}:
            question[key] = value
    return question


def _question_from_attrs_and_body(
    attrs: dict[str, Any],
    body_lines: list[str],
    fallback_index: int,
) -> QuestionModel:
    question_lines: list[str] = []
    answers: list[AnswerModel] = []
    seen_answer = False
    for line in body_lines:
        answer_match = _ANSWER_RE.match(line)
        if answer_match:
            seen_answer = True
            fraction = "1.0000000" if answer_match.group("mark").lower() == "x" else "0.0000000"
            answers.append(AnswerModel(text_html=answer_match.group("text"), fraction=fraction))
            continue
        if not seen_answer:
            question_lines.append(line)
    slot = int(attrs.get("slot", fallback_index))
    page = int(attrs.get("page", slot))
    qtype = str(attrs.get("type") or "multichoice")
    if qtype != "multichoice":
        raise ValueError(f"Sprint 3 supports only multichoice questions, got {qtype!r}")
    return QuestionModel(
        id=str(attrs.get("id") or f"question_{slot:02d}"),
        qtype=qtype,
        name=str(attrs.get("name") or attrs.get("title") or f"Question {slot}"),
        question_html="\n".join(question_lines).strip(),
        slot=slot,
        page=page,
        defaultmark=str(attrs.get("defaultmark", "1.0000000")),
        penalty=str(attrs.get("penalty", "0.3333333")),
        maxmark=str(attrs.get("maxmark", attrs.get("defaultmark", "1.0000000"))),
        single=bool(attrs.get("single", True)),
        shuffleanswers=bool(attrs.get("shuffleanswers", True)),
        answernumbering=str(attrs.get("answernumbering", "none")),
        answers=answers,
    )


def _parse_attrs(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    content = raw.strip()
    if not (content.startswith("{") and content.endswith("}")):
        raise ValueError(f"Invalid directive attributes: {raw}")
    lexer = shlex.shlex(content[1:-1], posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    attrs: dict[str, Any] = {}
    for token in lexer:
        if "=" not in token:
            attrs[token] = True
            continue
        key, value = token.split("=", 1)
        attrs[key] = _coerce_scalar(value)
    return attrs


def _parse_simple_yaml(source: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in source.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and raw_line.endswith(":"):
            current_key = raw_line[:-1].strip()
            root[current_key] = {}
            continue
        if raw_line.startswith("  ") and current_key:
            key, sep, value = raw_line.strip().partition(":")
            if not sep:
                raise ValueError(f"Invalid frontmatter line: {raw_line}")
            root[current_key][key] = _coerce_scalar(value.strip())
            continue
        key, sep, value = raw_line.partition(":")
        if not sep:
            raise ValueError(f"Invalid frontmatter line: {raw_line}")
        root[key.strip()] = _coerce_scalar(value.strip())
        current_key = None
    return root


def _coerce_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value
