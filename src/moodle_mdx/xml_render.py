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
            if "component" in section:
                _set_text(root, "component", str(section["component"]))
            if "itemid" in section:
                _set_text(root, "itemid", str(section["itemid"]))
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
                    continue
                if item.get("type") == "subsection":
                    subsection_path = item.get("source_path")
                    if not subsection_path:
                        continue
                    subsection_root = _read_xml(archive, str(subsection_path))
                    _set_text(subsection_root, "subsection/name", str(item.get("title") or ""))
                    overrides[str(subsection_path)] = _xml_bytes(subsection_root)
                    continue
                if item.get("type") == "choice":
                    choice_path = item.get("source_path")
                    if not choice_path:
                        continue
                    choice_root = _read_xml(archive, str(choice_path))
                    _render_choice_xml(choice_root, item)
                    overrides[str(choice_path)] = _xml_bytes(choice_root)
                    continue
                if item.get("type") == "questionnaire":
                    questionnaire_path = item.get("source_path")
                    if not questionnaire_path:
                        continue
                    questionnaire_root = _read_xml(archive, str(questionnaire_path))
                    _render_questionnaire_xml(questionnaire_root, item)
                    overrides[str(questionnaire_path)] = _xml_bytes(questionnaire_root)
                    continue
                if item.get("type") == "board":
                    board_path = item.get("source_path")
                    if not board_path:
                        continue
                    board_root = _read_xml(archive, str(board_path))
                    _render_board_xml(board_root, item)
                    overrides[str(board_path)] = _xml_bytes(board_root)
                    continue
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
        if section_node.find("parentcmid") is not None:
            _set_text(section_node, "parentcmid", str(section.get("parentcmid") or ""))
        if section_node.find("modname") is not None:
            _set_text(section_node, "modname", str(section.get("parent_modname") or ""))

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
    for setting_node in root.findall("information/settings/setting"):
        name = setting_node.findtext("name", "")
        if not name.endswith("_userinfo"):
            continue
        activity_key = name.removesuffix("_userinfo")
        item = _item_by_activity_key(items_by_moduleid.values(), activity_key)
        if item is None:
            continue
        _set_text(setting_node, "value", _activity_userinfo(item))
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


def _item_by_activity_key(items: object, activity_key: str) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        if f"{item.get('type')}_{item.get('moduleid')}" == activity_key:
            return item
    return None


def _activity_userinfo(item: dict[str, Any]) -> str:
    if item.get("type") != "board":
        return "0"
    for column in item.get("columns", []):
        if column.get("notes"):
            return "1"
    return "0"


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


def _render_choice_xml(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    _set_text(root, "choice/name", str(item.get("title") or ""))
    if "content_html" in item:
        _set_text(root, "choice/intro", str(item["content_html"]))
    for key in (
        "publish",
        "showresults",
        "display",
        "allowupdate",
        "allowmultiple",
        "showunanswered",
        "limitanswers",
        "timeopen",
        "timeclose",
        "completionsubmit",
        "showpreview",
        "includeinactive",
        "showavailable",
    ):
        if key in settings:
            _set_text(root, f"choice/{key}", _moodle_scalar(settings[key]))
    option_nodes = root.findall("choice/options/option")
    options = item.get("options", [])
    if options and len(options) != len(option_nodes):
        raise ValueError(
            f"Choice option count changed from {len(option_nodes)} to {len(options)}; template mode keeps existing options"
        )
    for node, option in zip(option_nodes, options):
        _set_text(node, "text", str(option.get("text") or ""))
        _set_text(node, "maxanswers", _moodle_scalar(option.get("maxanswers", 0)))


def _render_questionnaire_xml(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    title = str(item.get("title") or "")
    _set_text(root, "questionnaire/name", title)
    _set_text(root, "questionnaire/surveys/survey/name", title)
    _set_text(root, "questionnaire/surveys/survey/title", title)
    if "content_html" in item:
        _set_text(root, "questionnaire/intro", str(item["content_html"]))
    for source, target in {
        "survey_info": "info",
        "info": "info",
        "thanks_page": "thanks_page",
        "thank_head": "thank_head",
        "thank_body": "thank_body",
    }.items():
        if source in settings:
            _set_text(root, f"questionnaire/surveys/survey/{target}", str(settings[source]))
    for key in (
        "qtype",
        "respondenttype",
        "resp_eligible",
        "resp_view",
        "notifications",
        "opendate",
        "closedate",
        "resume",
        "navigate",
        "grade",
        "sid",
        "completionsubmit",
        "autonum",
        "removeafter",
    ):
        if key in settings:
            _set_text(root, f"questionnaire/{key}", _moodle_scalar(settings[key]))
    questions_node = root.find("questionnaire/surveys/survey/questions")
    if questions_node is not None and item.get("survey_questions"):
        questions_node.clear()
        survey = root.find("questionnaire/surveys/survey")
        survey_id = str(settings.get("sid") or (survey.get("id") if survey is not None else "1"))
        survey_questions = item.get("survey_questions", [])
        question_ids, choice_ids = _questionnaire_dependency_maps(survey_questions)
        for index, question in enumerate(survey_questions, start=1):
            _add_questionnaire_question(questions_node, question, index, survey_id, question_ids, choice_ids)


QUESTIONNAIRE_TYPE_IDS = {
    "yesno": 1,
    "textarea": 2,
    "text": 3,
    "radio": 4,
    "checkbox": 5,
    "dropdown": 6,
    "rate": 8,
    "date": 9,
    "slider": 11,
    "pagebreak": 99,
    "sectiontext": 100,
    "label": 100,
}


def _add_questionnaire_question(
    parent: ET.Element,
    question: dict[str, Any],
    index: int,
    survey_id: str,
    question_ids: dict[str, str],
    choice_ids: dict[tuple[str, str], str],
) -> None:
    question_id = str(9000 + index)
    node = ET.SubElement(parent, "question", {"id": question_id})
    qtype = str(question.get("type") or "text")
    _add_text(node, "surveyid", survey_id)
    _add_text(node, "name", str(question.get("name") or "$@NULL@$"))
    _add_text(node, "type_id", str(QUESTIONNAIRE_TYPE_IDS.get(qtype, qtype)))
    _add_text(node, "result_id", "$@NULL@$")
    _add_text(node, "length", _moodle_scalar(question.get("length", 0)))
    _add_text(node, "precise", _moodle_scalar(question.get("precise", 0)))
    _add_text(node, "position", _moodle_scalar(question.get("position", index)))
    _add_text(node, "content", str(question.get("content") or ("break" if qtype == "pagebreak" else "")))
    _add_text(node, "required", "y" if question.get("required", False) else "n")
    _add_text(node, "deleted", str(question.get("deleted", "n")))
    _add_text(node, "extradata", _questionnaire_extradata(question, qtype))
    choices = ET.SubElement(node, "quest_choices")
    for choice_index, choice in enumerate(question.get("choices", []), start=1):
        choice_node = ET.SubElement(choices, "quest_choice", {"id": str(9100 + index * 100 + choice_index)})
        _add_text(choice_node, "question_id", question_id)
        _add_text(choice_node, "content", str(choice.get("content") or ""))
        _add_text(choice_node, "value", _moodle_scalar(choice.get("value", "$@NULL@$")))
    dependencies = ET.SubElement(node, "quest_dependencies")
    _add_questionnaire_dependencies(dependencies, question, index, question_id, survey_id, question_ids, choice_ids)


def _questionnaire_dependency_maps(questions: list[dict[str, Any]]) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    question_ids: dict[str, str] = {}
    choice_ids: dict[tuple[str, str], str] = {}
    for index, question in enumerate(questions, start=1):
        question_id = str(9000 + index)
        refs = _questionnaire_question_refs(question, index)
        for ref in refs:
            question_ids[ref] = question_id
        for choice_index, choice in enumerate(question.get("choices", []), start=1):
            choice_id = str(9100 + index * 100 + choice_index)
            for question_ref in refs:
                for choice_ref in _questionnaire_choice_refs(choice, choice_index):
                    choice_ids[(question_ref, choice_ref)] = choice_id
    return question_ids, choice_ids


def _questionnaire_question_refs(question: dict[str, Any], index: int) -> set[str]:
    refs = {
        str(question.get("id") or ""),
        str(question.get("name") or ""),
        str(question.get("position") or index),
        f"q{index}",
    }
    return {ref for ref in refs if ref}


def _questionnaire_choice_refs(choice: dict[str, Any], index: int) -> set[str]:
    settings = choice.get("settings", {})
    refs = {
        str(choice.get("id") or ""),
        str(choice.get("value") or ""),
        str(choice.get("content") or ""),
        str(settings.get("id") or ""),
        str(settings.get("value") or ""),
        str(index),
        f"c{index}",
    }
    return {ref for ref in refs if ref}


def _add_questionnaire_dependencies(
    parent: ET.Element,
    question: dict[str, Any],
    index: int,
    question_id: str,
    survey_id: str,
    question_ids: dict[str, str],
    choice_ids: dict[tuple[str, str], str],
) -> None:
    settings = question.get("settings", {})
    depends_on = question.get("depends_on", settings.get("depends_on", ""))
    if not depends_on:
        return
    dependencies = _split_dependency_values(depends_on)
    joins = _split_dependency_values(question.get("depends_join", settings.get("depends_join", "and")))
    logics = _split_dependency_values(question.get("depends_logic", settings.get("depends_logic", 1)))
    for dependency_index, dependency in enumerate(dependencies, start=1):
        question_ref, separator, choice_ref = dependency.partition(":")
        if not separator or not question_ref or not choice_ref:
            raise ValueError(f"Invalid questionnaire dependency {dependency!r}; expected 'question_id:choice_id'")
        dependquestionid = question_ids.get(question_ref)
        if dependquestionid is None:
            raise ValueError(f"Unknown questionnaire dependency question id: {question_ref}")
        dependchoiceid = choice_ids.get((question_ref, choice_ref))
        if dependchoiceid is None:
            raise ValueError(f"Unknown questionnaire dependency choice id: {question_ref}:{choice_ref}")
        dependency_node = ET.SubElement(parent, "quest_dependency", {"id": str(9200 + index * 100 + dependency_index)})
        _add_text(dependency_node, "dependquestionid", dependquestionid)
        _add_text(dependency_node, "dependchoiceid", dependchoiceid)
        _add_text(dependency_node, "dependlogic", str(logics[min(dependency_index - 1, len(logics) - 1)]))
        _add_text(dependency_node, "questionid", question_id)
        _add_text(dependency_node, "surveyid", survey_id)
        _add_text(dependency_node, "dependandor", str(joins[min(dependency_index - 1, len(joins) - 1)]))


def _split_dependency_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _questionnaire_extradata(question: dict[str, Any], qtype: str) -> str:
    if question.get("extradata") is not None:
        return str(question["extradata"])
    if qtype == "rate":
        return "[]"
    if qtype == "pagebreak":
        return "$@NULL@$"
    if qtype == "slider":
        import json

        settings = question.get("settings", {})
        data = {
            "minrange": str(question.get("minrange", settings.get("minrange", 0))),
            "maxrange": str(question.get("maxrange", settings.get("maxrange", 10))),
            "startingvalue": str(question.get("startingvalue", settings.get("startingvalue", 0))),
            "stepvalue": str(question.get("stepvalue", settings.get("stepvalue", 1))),
            "leftlabel": str(question.get("leftlabel", settings.get("leftlabel", ""))),
            "rightlabel": str(question.get("rightlabel", settings.get("rightlabel", ""))),
            "centerlabel": str(question.get("centerlabel", settings.get("centerlabel", ""))),
        }
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return "0"


def _render_board_xml(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    _set_text(root, "board/name", str(item.get("title") or ""))
    if "content_html" in item:
        _set_text(root, "board/intro", str(item["content_html"]))
    for key in (
        "background_color",
        "addrating",
        "hideheaders",
        "sortby",
        "postby",
        "userscanedit",
        "singleusermode",
        "completionnotes",
        "embed",
    ):
        if key in settings:
            _set_text(root, f"board/{key}", _moodle_scalar(settings[key]))
    column_nodes = root.findall("board/columns/column")
    columns = item.get("columns", [])
    if columns and len(columns) != len(column_nodes):
        raise ValueError(
            f"Board column count changed from {len(column_nodes)} to {len(columns)}; template mode keeps existing columns"
        )
    for node, column in zip(column_nodes, columns):
        _set_text(node, "name", str(column.get("name") or ""))
        if "sortorder" in column:
            _set_text(node, "sortorder", _moodle_scalar(column["sortorder"]))
        notes = node.find("notes")
        if notes is None:
            notes = ET.SubElement(node, "notes")
        notes.clear()
        for index, note in enumerate(column.get("notes", []), start=1):
            note_node = ET.SubElement(notes, "note", {"id": str(8200 + index)})
            _add_text(note_node, "columnid", node.get("id") or "")
            _add_text(note_node, "ownerid", _moodle_scalar(note.get("ownerid", 2)))
            _add_text(note_node, "userid", _moodle_scalar(note.get("userid", 2)))
            _add_text(note_node, "groupid", _moodle_scalar(note.get("groupid", "")))
            _add_text(note_node, "content", str(note.get("content") or ""))
            _add_text(note_node, "heading", str(note.get("heading") or ""))
            _add_text(note_node, "type", _moodle_scalar(note.get("type", 0)))
            _add_text(note_node, "info", str(note.get("info") or ""))
            _add_text(note_node, "url", str(note.get("url") or ""))
            _add_text(note_node, "filename", str(note.get("filename") or ""))
            _add_text(note_node, "timecreated", "0")
            _add_text(note_node, "sortorder", _moodle_scalar(note.get("sortorder", index - 1)))
            _add_text(note_node, "deleted", _moodle_scalar(note.get("deleted", 0)))
            ET.SubElement(note_node, "comments")
            ET.SubElement(note_node, "ratings")


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
