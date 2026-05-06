from __future__ import annotations

import hashlib
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ArchiveOverrides:
    files: dict[str, bytes] = field(default_factory=dict)
    removed_paths: set[str] = field(default_factory=set)


def render_template_xml_overrides(
    template: str | Path,
    manifest: dict[str, Any],
    source_dir: str | Path | None = None,
) -> ArchiveOverrides:
    overrides: dict[str, bytes] = {}
    removed_paths: set[str] = set()
    with tarfile.open(template, "r:gz") as archive:
        overrides["course/course.xml"] = _render_course_xml_override(archive, manifest)
        overrides["moodle_backup.xml"] = _render_moodle_backup_xml_override(archive, manifest)
        question_updates: dict[str, dict[str, Any]] = {}
        question_source_path = "questions.xml"
        for section in manifest.get("sections", []):
            sectionid = str(section["sectionid"])
            path = f"sections/section_{sectionid}/section.xml"
            root = _read_xml(archive, path)
            _set_text(root, "number", str(section["index"]))
            _set_text(root, "name", section.get("title") or "$@NULL@$")
            _set_text(root, "summary", section.get("summary_html") or "")
            sequence = ",".join(
                str(item["moduleid"])
                for item in section.get("items", [])
                if "moduleid" in item
            )
            _set_text(root, "sequence", sequence)
            overrides[path] = _xml_bytes(root)

            for item in section.get("items", []):
                if item.get("type") == "label":
                    label_path = item.get("source_path")
                    if not label_path:
                        continue
                    label_root = _read_xml(archive, str(label_path))
                    _set_text(label_root, "label/name", str(item.get("title") or ""))
                    if "content_html" in item:
                        _set_text(label_root, "label/intro", str(item["content_html"]))
                    overrides[str(label_path)] = _xml_bytes(label_root)
                    continue
                if item.get("type") == "book":
                    book_path = item.get("source_path")
                    if not book_path:
                        continue
                    book_root = _read_xml(archive, str(book_path))
                    _set_text(book_root, "book/name", str(item.get("title") or ""))
                    _replace_book_chapters(book_root, item.get("pages", []))
                    overrides[str(book_path)] = _xml_bytes(book_root)
                    continue
                if item.get("type") == "quiz":
                    quiz_path = item.get("source_path")
                    if not quiz_path:
                        continue
                    quiz_root = _read_xml(archive, str(quiz_path))
                    _set_text(quiz_root, "quiz/name", str(item.get("title") or ""))
                    _replace_quiz_question_instances(quiz_root, item.get("questions", []))
                    overrides[str(quiz_path)] = _xml_bytes(quiz_root)
                    if item.get("question_source_path"):
                        question_source_path = str(item["question_source_path"])
                    question_updates.update(_question_updates_for_quiz(quiz_root, item.get("questions", [])))
                    continue
                if item.get("type") == "folder":
                    folder_path = item.get("source_path")
                    if not folder_path:
                        continue
                    folder_root = _read_xml(archive, str(folder_path))
                    _set_text(folder_root, "folder/name", str(item.get("title") or ""))
                    if "content_html" in item:
                        _set_text(folder_root, "folder/intro", str(item["content_html"]))
                    overrides[str(folder_path)] = _xml_bytes(folder_root)
                    continue
                if item.get("type") == "geogebra":
                    geogebra_path = item.get("source_path")
                    if not geogebra_path:
                        continue
                    geogebra_root = _read_xml(archive, str(geogebra_path))
                    _set_text(geogebra_root, "geogebra/name", str(item.get("title") or ""))
                    if "content_html" in item:
                        _set_text(geogebra_root, "geogebra/intro", str(item["content_html"]))
                    if item.get("file_path"):
                        _set_text(geogebra_root, "geogebra/url", Path(str(item["file_path"])).name)
                    settings = item.get("settings", {})
                    if "width" in settings:
                        _set_text(geogebra_root, "geogebra/width", str(settings["width"]))
                    if "height" in settings:
                        _set_text(geogebra_root, "geogebra/height", str(settings["height"]))
                    overrides[str(geogebra_path)] = _xml_bytes(geogebra_root)
                    continue
                if item.get("type") == "assign":
                    assign_path = item.get("source_path")
                    if not assign_path:
                        continue
                    assign_root = _read_xml(archive, str(assign_path))
                    _render_assign_xml(assign_root, item)
                    overrides[str(assign_path)] = _xml_bytes(assign_root)
                    continue
                if item.get("type") == "forum":
                    forum_path = item.get("source_path")
                    if not forum_path:
                        continue
                    forum_root = _read_xml(archive, str(forum_path))
                    _set_text(forum_root, "forum/name", str(item.get("title") or ""))
                    if "content_html" in item:
                        _set_text(forum_root, "forum/intro", str(item["content_html"]))
                    overrides[str(forum_path)] = _xml_bytes(forum_root)
        if question_updates:
            question_root = _read_xml(archive, question_source_path)
            _replace_questions(question_root, question_updates)
            overrides[question_source_path] = _xml_bytes(question_root)
        if source_dir is not None:
            file_overrides, file_removed = _render_file_pool_overrides(archive, manifest, Path(source_dir))
            overrides.update(file_overrides)
            removed_paths.update(file_removed)
    return ArchiveOverrides(files=overrides, removed_paths=removed_paths)


def render_section_and_label_xml(template: str | Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    return render_template_xml_overrides(template, manifest).files


def _render_course_xml_override(archive: tarfile.TarFile, manifest: dict[str, Any]) -> bytes:
    root = _read_xml(archive, "course/course.xml")
    course = manifest.get("course", {})
    settings = course.get("settings", {})
    _set_text(root, "fullname", str(course.get("title") or ""))
    _set_text(root, "shortname", str(course.get("shortname") or ""))
    _set_text(root, "format", str(course.get("format") or "topics"))
    for key in ("startdate", "enddate", "visible", "enablecompletion"):
        if key in settings:
            _set_text(root, key, _moodle_scalar(settings[key]))
    _replace_course_format_options(root, course)
    return _xml_bytes(root)


def _replace_course_format_options(root: ET.Element, course: dict[str, Any]) -> None:
    format_options = {
        str(option.get("name")): option
        for option in course.get("format_options", [])
        if option.get("name")
    }
    if not format_options:
        return
    course_format = str(course.get("format") or "topics")
    for node in root.findall("courseformatoptions/courseformatoption"):
        name = node.findtext("name", "")
        option = format_options.get(name)
        if option is None:
            continue
        _set_text(node, "format", course_format)
        _set_text(node, "sectionid", str(option.get("sectionid", "0")))
        _set_text(node, "value", str(option.get("value", "")))


def _render_moodle_backup_xml_override(archive: tarfile.TarFile, manifest: dict[str, Any]) -> bytes:
    root = _read_xml(archive, "moodle_backup.xml")
    course = manifest.get("course", {})
    settings = course.get("settings", {})
    _set_text(root, "information/original_course_format", str(course.get("format") or "topics"))
    _set_text(root, "information/original_course_fullname", str(course.get("title") or ""))
    _set_text(root, "information/original_course_shortname", str(course.get("shortname") or ""))
    if "startdate" in settings:
        _set_text(root, "information/original_course_startdate", _moodle_scalar(settings["startdate"]))
    if "enddate" in settings:
        _set_text(root, "information/original_course_enddate", _moodle_scalar(settings["enddate"]))

    sections_by_id = {
        str(section.get("sectionid")): section
        for section in manifest.get("sections", [])
    }
    for section_node in root.findall("information/contents/sections/section"):
        section = sections_by_id.get(section_node.findtext("sectionid", ""))
        if section is None:
            continue
        _set_text(section_node, "title", _backup_section_title(section))

    items_by_moduleid = {
        str(item.get("moduleid")): item
        for section in manifest.get("sections", [])
        for item in section.get("items", [])
        if item.get("moduleid")
    }
    for activity_node in root.findall("information/contents/activities/activity"):
        item = items_by_moduleid.get(activity_node.findtext("moduleid", ""))
        if item is None:
            continue
        _set_text(activity_node, "sectionid", str(item.get("sectionid") or ""))
        _set_text(activity_node, "modulename", str(item.get("type") or ""))
        _set_text(activity_node, "title", str(item.get("title") or ""))
    return _xml_bytes(root)


def _backup_section_title(section: dict[str, Any]) -> str:
    if int(section.get("index", 0)) == 0 and not section.get("title"):
        return "0"
    return str(section.get("title") or "")


def _render_assign_xml(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    _set_text(root, "assign/name", str(item.get("title") or ""))
    if "content_html" in item:
        _set_text(root, "assign/intro", str(item["content_html"]))
    for key in ("grade", "gradingduedate", "maxattempts", "attemptreopenmethod", "completionsubmit"):
        if key in settings:
            _set_text(root, f"assign/{key}", _moodle_scalar(settings[key]))
    plugin_keys = {
        "submission_onlinetext": ("onlinetext", "assignsubmission"),
        "submission_file": ("file", "assignsubmission"),
        "submission_comments": ("comments", "assignsubmission"),
        "feedback_comments": ("comments", "assignfeedback"),
        "feedback_editpdf": ("editpdf", "assignfeedback"),
    }
    for setting_key, (plugin, subtype) in plugin_keys.items():
        if setting_key in settings:
            _set_assign_plugin_enabled(root, plugin, subtype, bool(settings[setting_key]))


def _set_assign_plugin_enabled(root: ET.Element, plugin: str, subtype: str, enabled: bool) -> None:
    for config in root.findall("assign/plugin_configs/plugin_config"):
        if (
            config.findtext("plugin", "") == plugin
            and config.findtext("subtype", "") == subtype
            and config.findtext("name", "") == "enabled"
        ):
            _set_text(config, "value", "1" if enabled else "0")
            return
    raise ValueError(f"Assign plugin config {subtype}/{plugin}/enabled not found")


def _render_file_pool_overrides(
    archive: tarfile.TarFile,
    manifest: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, bytes], set[str]]:
    root = _read_xml(archive, "files.xml")
    overrides: dict[str, bytes] = {}
    removed_paths: set[str] = set()
    for item in _manifest_items(manifest):
        if item.get("type") == "folder" and item.get("files"):
            folder_nodes = _file_nodes(root, component="mod_folder")
            folder_files = item.get("files", [])
            if len(folder_files) != len(folder_nodes):
                raise ValueError(
                    f"Folder file count changed from {len(folder_nodes)} to {len(folder_files)}; Sprint 4 keeps existing slots"
                )
            for template_node, asset in zip(folder_nodes, folder_files):
                _apply_asset_file(template_node, str(asset["path"]), source_dir, overrides, removed_paths)
            continue
        if item.get("type") == "geogebra" and item.get("file_path"):
            geogebra_path = item.get("source_path")
            if not geogebra_path:
                continue
            geogebra_root = _read_xml(archive, str(geogebra_path))
            contextid = geogebra_root.get("contextid", "")
            geogebra_nodes = _file_nodes(root, component="mod_geogebra", contextid=contextid)
            if len(geogebra_nodes) != 1:
                raise ValueError(f"GeoGebra activity {item.get('id')} needs exactly one file slot, got {len(geogebra_nodes)}")
            _apply_asset_file(geogebra_nodes[0], str(item["file_path"]), source_dir, overrides, removed_paths)
    if overrides:
        overrides["files.xml"] = _xml_bytes(root)
    return overrides, removed_paths


def _manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for section in manifest.get("sections", [])
        for item in section.get("items", [])
    ]


def _file_nodes(root: ET.Element, *, component: str, contextid: str | None = None) -> list[ET.Element]:
    nodes = []
    for file_node in root.findall("file"):
        if file_node.findtext("component", "") != component:
            continue
        if contextid is not None and file_node.findtext("contextid", "") != contextid:
            continue
        if file_node.findtext("filename", "") in {"", "."}:
            continue
        nodes.append(file_node)
    return nodes


def _apply_asset_file(
    file_node: ET.Element,
    asset_path: str,
    source_dir: Path,
    overrides: dict[str, bytes],
    removed_paths: set[str],
) -> None:
    source_path = Path(asset_path)
    if not source_path.is_absolute():
        source_path = source_dir / source_path
    data = source_path.read_bytes()
    contenthash = hashlib.sha1(data).hexdigest()
    filename = source_path.name
    old_hash = file_node.findtext("contenthash", "")
    if old_hash:
        old_path = f"files/{old_hash[:2]}/{old_hash}"
        if old_hash != contenthash:
            removed_paths.add(old_path)
    new_path = f"files/{contenthash[:2]}/{contenthash}"
    overrides[new_path] = data
    _set_text(file_node, "contenthash", contenthash)
    _set_text(file_node, "filename", filename)
    _set_text(file_node, "filesize", str(len(data)))
    _set_text(file_node, "source", filename)


def _replace_book_chapters(root: ET.Element, pages: list[dict[str, Any]]) -> None:
    chapters = root.find("book/chapters")
    if chapters is None:
        raise ValueError(f"XML node 'book/chapters' not found in {root.tag}")
    template_chapters = list(chapters.findall("chapter"))
    chapters.clear()
    for index, page in enumerate(pages):
        template = template_chapters[index] if index < len(template_chapters) else None
        chapter = ET.Element("chapter")
        chapter.set("id", _template_attr(template, "id", str(index + 1)))
        _add_text(chapter, "pagenum", _template_text(template, "pagenum", str(index + 1)))
        _add_text(chapter, "subchapter", str(int(page.get("subchapter", 0))))
        _add_text(chapter, "title", str(page.get("title") or f"Page {index + 1}"))
        _add_text(chapter, "content", str(page.get("content_html") or ""))
        _add_text(chapter, "contentformat", _template_text(template, "contentformat", "1"))
        _add_text(chapter, "hidden", _template_text(template, "hidden", "0"))
        _add_text(chapter, "timemodified", _template_text(template, "timemodified", "0"))
        _add_text(chapter, "importsrc", _template_text(template, "importsrc", ""))
        chapters.append(chapter)


def _replace_quiz_question_instances(root: ET.Element, questions: list[dict[str, Any]]) -> None:
    instances = root.find("quiz/question_instances")
    if instances is None:
        raise ValueError(f"XML node 'quiz/question_instances' not found in {root.tag}")
    template_instances = list(instances.findall("question_instance"))
    if questions and len(questions) != len(template_instances):
        raise ValueError(
            f"Quiz question count changed from {len(template_instances)} to {len(questions)}; Sprint 3 keeps existing slots"
        )
    for index, question in enumerate(questions):
        instance = template_instances[index]
        _set_text(instance, "slot", str(int(question.get("slot", index + 1))))
        _set_text(instance, "page", str(int(question.get("page", question.get("slot", index + 1)))))
        _set_text(instance, "maxmark", str(question.get("maxmark", "1.0000000")))


def _question_updates_for_quiz(
    quiz_root: ET.Element,
    questions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {}
    instances = quiz_root.findall("quiz/question_instances/question_instance")
    for index, question in enumerate(questions):
        if index >= len(instances):
            break
        bank_entry_id = instances[index].findtext("question_reference/questionbankentryid", "")
        if bank_entry_id:
            updates[bank_entry_id] = question
    return updates


def _replace_questions(root: ET.Element, updates: dict[str, dict[str, Any]]) -> None:
    for entry in root.findall(".//question_bank_entry"):
        entry_id = entry.get("id")
        if not entry_id or entry_id not in updates:
            continue
        question_data = updates[entry_id]
        question = entry.find("question_version/question_versions/questions/question")
        if question is None:
            raise ValueError(f"Question bank entry {entry_id} has no question")
        qtype = question.findtext("qtype", "")
        if qtype != "multichoice" or question_data.get("type") != "multichoice":
            raise ValueError(f"Sprint 3 supports only multichoice questions, got {qtype!r}")
        _set_text(question, "name", str(question_data.get("name") or ""))
        _set_text(question, "questiontext", str(question_data.get("question_html") or ""))
        _set_text(question, "defaultmark", str(question_data.get("defaultmark", "1.0000000")))
        _set_text(question, "penalty", str(question_data.get("penalty", "0.3333333")))
        multichoice = question.find("plugin_qtype_multichoice_question/multichoice")
        if multichoice is None:
            raise ValueError(f"Question bank entry {entry_id} has no multichoice settings")
        _set_text(multichoice, "single", "1" if bool(question_data.get("single", True)) else "0")
        _set_text(multichoice, "shuffleanswers", "1" if bool(question_data.get("shuffleanswers", True)) else "0")
        _set_text(multichoice, "answernumbering", str(question_data.get("answernumbering", "none")))
        _replace_multichoice_answers(question, question_data.get("answers", []), entry_id)


def _replace_multichoice_answers(
    question: ET.Element,
    answers: list[dict[str, Any]],
    entry_id: str,
) -> None:
    answer_nodes = question.findall("plugin_qtype_multichoice_question/answers/answer")
    if len(answers) != len(answer_nodes):
        raise ValueError(
            f"Question bank entry {entry_id} answer count changed from {len(answer_nodes)} to {len(answers)}; Sprint 3 keeps existing answers"
        )
    for answer_node, answer in zip(answer_nodes, answers):
        _set_text(answer_node, "answertext", str(answer.get("text_html") or ""))
        _set_text(answer_node, "fraction", str(answer.get("fraction", "0.0000000")))


def _read_xml(archive: tarfile.TarFile, path: str) -> ET.Element:
    member = archive.extractfile(path)
    if member is None:
        raise FileNotFoundError(path)
    return ET.fromstring(member.read())


def _set_text(root: ET.Element, path: str, value: str) -> None:
    node = root.find(path)
    if node is None:
        raise ValueError(f"XML node {path!r} not found in {root.tag}")
    node.text = value


def _add_text(root: ET.Element, tag: str, value: str) -> ET.Element:
    node = ET.SubElement(root, tag)
    node.text = value
    return node


def _template_text(template: ET.Element | None, path: str, default: str) -> str:
    if template is None:
        return default
    return template.findtext(path, default) or default


def _template_attr(template: ET.Element | None, name: str, default: str) -> str:
    if template is None:
        return default
    return template.get(name) or default


def _xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _moodle_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value)
