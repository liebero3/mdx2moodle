from __future__ import annotations

from typing import Any

from .model import AnswerModel, CourseModel, MoodleItem, QuestionModel


def render_manifest(model: CourseModel) -> dict[str, Any]:
    backup = {
        key: value
        for key, value in model.backup.items()
        if value is not None
    }
    mode = "template" if backup.get("template") else "standalone"
    manifest = {
        "platform": "moodle",
        "build": {"mode": mode},
        "backup": backup,
        "course": {
            "title": model.course.get("title") or model.course.get("fullname") or "",
            "shortname": model.course.get("shortname", ""),
            "format": model.course.get("format", "topics"),
            "settings": {
                key: value
                for key, value in model.course.items()
                if key not in {"title", "fullname", "shortname", "format"}
            },
            "format_options": _render_format_options(model),
        },
        "sections": [
            {
                "id": section.id,
                "index": section.index,
                "sectionid": str(section.attrs.get("sectionid") or _sectionid_from_model_id(section.id)),
                "title": section.title,
                "summary_html": section.summary,
                "items": [_render_item(item) for item in section.items],
            }
            for section in model.sections
        ],
    }
    if mode == "standalone":
        _assign_standalone_paths(manifest)
    return manifest


def _render_item(item: MoodleItem) -> dict[str, Any]:
    rendered: dict[str, Any] = {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "visible": bool(item.attrs.get("visible", True)),
    }
    for source_key, target_key in {
        "source": "source_path",
        "module": "module_path",
        "file": "file_path",
        "questions": "question_source_path",
    }.items():
        if source_key in item.attrs:
            rendered[target_key] = item.attrs[source_key]
    if "moduleid" in item.attrs:
        rendered["moduleid"] = str(item.attrs["moduleid"])
    if "sectionid" in item.attrs:
        rendered["sectionid"] = str(item.attrs["sectionid"])
    if item.body.strip() and item.type not in {"book", "quiz"}:
        rendered["content_html"] = item.body if item.type == "label" else item.body.strip()
    if item.pages:
        rendered["pages"] = [
            {
                "title": page["title"],
                "content_html": page.get("content", ""),
                "subchapter": int(page.get("subchapter", 0)),
            }
            for page in item.pages
        ]
    if item.questions:
        rendered["questions"] = [_render_question(question) for question in item.questions]
    if item.files:
        rendered["files"] = [
            {
                "path": str(file["path"]),
                "filename": str(file.get("filename") or str(file["path"]).rsplit("/", 1)[-1]),
            }
            for file in item.files
        ]
    options = {
        key: value
        for key, value in item.attrs.items()
        if key
        not in {
            "id",
            "title",
            "source",
            "module",
            "file",
            "questions",
            "moduleid",
            "sectionid",
            "visible",
        }
    }
    if options:
        rendered["settings"] = options
    return rendered


def _render_format_options(model: CourseModel) -> list[dict[str, str]]:
    course_format = str(model.course.get("format", "topics"))
    return [
        {
            "format": course_format,
            "sectionid": "0",
            "name": str(name),
            "value": _manifest_scalar(value),
        }
        for name, value in model.format_options.items()
    ]


def _render_question(question: QuestionModel) -> dict[str, Any]:
    return {
        "id": question.id,
        "type": question.qtype,
        "name": question.name,
        "question_html": question.question_html,
        "slot": question.slot,
        "page": question.page,
        "defaultmark": question.defaultmark,
        "penalty": question.penalty,
        "maxmark": question.maxmark,
        "single": question.single,
        "shuffleanswers": question.shuffleanswers,
        "answernumbering": question.answernumbering,
        "answers": [_render_answer(answer) for answer in question.answers],
    }


def _render_answer(answer: AnswerModel) -> dict[str, str]:
    return {
        "text_html": answer.text_html,
        "fraction": answer.fraction,
    }


def _manifest_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value)


def _sectionid_from_model_id(section_id: str) -> str:
    if section_id.startswith("section_"):
        return section_id.removeprefix("section_")
    return section_id


def _assign_standalone_paths(manifest: dict[str, Any]) -> None:
    moduleid = 3000
    for section_index, section in enumerate(manifest.get("sections", [])):
        section["sectionid"] = str(2000 + section_index)
        for item in section.get("items", []):
            current_moduleid = str(moduleid)
            moduleid += 1
            item["moduleid"] = current_moduleid
            item["sectionid"] = str(section["sectionid"])
            directory = f"activities/{item['type']}_{current_moduleid}"
            item["source_path"] = f"{directory}/{item['type']}.xml"
            item["module_path"] = f"{directory}/module.xml"
            if item["type"] == "quiz":
                item["question_source_path"] = "questions.xml"
