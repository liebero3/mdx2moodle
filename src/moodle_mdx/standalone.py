from __future__ import annotations

import gzip
import hashlib
import json
import mimetypes
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


COURSE_ID = "1"
COURSE_CONTEXT_ID = "1000"
SYSTEM_CONTEXT_ID = "1"
MOODLE_VERSION = "2024100710"
BACKUP_VERSION = "2024100700"
BACKUP_RELEASE = "4.5"
TIMESTAMP = "0"


def render_standalone_mbz(manifest: dict[str, Any], output_path: str | Path, source_dir: str | Path) -> None:
    source_base = Path(source_dir)
    _assign_question_ids(manifest)
    files: dict[str, bytes] = {
        ".ARCHIVE_INDEX": b"",
        "moodle_backup.xml": _moodle_backup_xml(manifest),
        "course/course.xml": _course_xml(manifest),
        "questions.xml": _questions_xml(manifest),
        "files.xml": b'<?xml version="1.0" encoding="UTF-8"?>\n<files />',
        "badges.xml": _empty_xml("badges"),
        "completion.xml": _empty_xml("course_completion"),
        "grade_history.xml": _empty_xml("grade_history"),
        "gradebook.xml": _gradebook_xml(),
        "groups.xml": _groups_xml(),
        "outcomes.xml": _empty_xml("outcomes_definition"),
        "roles.xml": _roles_xml(),
        "scales.xml": _empty_xml("scales_definition"),
        "moodle_backup.log": b"",
        "course/enrolments.xml": _enrolments_xml(),
        "course/filters.xml": _empty_xml("filters"),
        "course/roles.xml": _empty_xml("roles"),
        "course/inforef.xml": _empty_xml("inforef"),
        "course/competencies.xml": _empty_xml("course_competencies"),
        "course/completiondefaults.xml": _empty_xml("course_completion_defaults"),
        "course/contentbank.xml": _empty_xml("contents"),
    }
    file_pool = _FilePool()
    for section in manifest.get("sections", []):
        sectionid = str(section["sectionid"])
        files[f"sections/section_{sectionid}/section.xml"] = _section_xml(section)
        for item in section.get("items", []):
            directory = _activity_directory(item)
            files[f"{directory}/module.xml"] = _module_xml(section, item)
            files[f"{directory}/grades.xml"] = _activity_grades_xml()
            files[f"{directory}/grade_history.xml"] = _empty_xml("grade_history")
            files[f"{directory}/filters.xml"] = _empty_xml("filters")
            files[f"{directory}/roles.xml"] = _empty_xml("roles")
            files[f"{directory}/competencies.xml"] = _empty_xml("course_module_competencies")
            files[f"{directory}/{item['type']}.xml"] = _activity_xml(item, file_pool, source_base)
            files[f"{directory}/inforef.xml"] = _activity_inforef_xml(item, file_pool)
    file_xml, blob_files = file_pool.render()
    files["files.xml"] = file_xml
    files.update(blob_files)
    _write_deterministic_tar_gz(Path(output_path), files)


def _moodle_backup_xml(manifest: dict[str, Any]) -> bytes:
    root = ET.Element("moodle_backup")
    info = ET.SubElement(root, "information")
    course = manifest.get("course", {})
    settings = course.get("settings", {})
    _text(info, "name", "standalone-mdx2moodle.mbz")
    _text(info, "moodle_version", MOODLE_VERSION)
    _text(info, "moodle_release", str(manifest.get("backup", {}).get("moodle_release") or "4.5.10 (Build: 20260216)"))
    _text(info, "backup_version", BACKUP_VERSION)
    _text(info, "backup_release", BACKUP_RELEASE)
    _text(info, "backup_date", TIMESTAMP)
    _text(info, "mnet_remoteusers", "0")
    _text(info, "include_files", "1")
    _text(info, "include_file_references_to_external_content", "0")
    _text(info, "original_wwwroot", "https://standalone.mdx2moodle.local")
    _text(info, "original_site_identifier_hash", "standalone")
    _text(info, "original_course_id", COURSE_ID)
    _text(info, "original_course_format", str(course.get("format") or "topics"))
    _text(info, "original_course_fullname", str(course.get("title") or ""))
    _text(info, "original_course_shortname", str(course.get("shortname") or ""))
    _text(info, "original_course_startdate", _scalar(settings.get("startdate", 0)))
    _text(info, "original_course_enddate", _scalar(settings.get("enddate", 0)))
    _text(info, "original_course_contextid", COURSE_CONTEXT_ID)
    _text(info, "original_system_contextid", SYSTEM_CONTEXT_ID)
    details = ET.SubElement(info, "details")
    detail = ET.SubElement(details, "detail", {"backup_id": "standalone"})
    _text(detail, "type", "course")
    _text(detail, "format", "moodle2")
    _text(detail, "interactive", "1")
    _text(detail, "mode", "10")
    _text(detail, "execution", "1")
    _text(detail, "executiontime", "0")
    contents = ET.SubElement(info, "contents")
    activities = ET.SubElement(contents, "activities")
    for item in _manifest_items(manifest):
        activity = ET.SubElement(activities, "activity")
        _text(activity, "moduleid", str(item["moduleid"]))
        _text(activity, "sectionid", str(item["sectionid"]))
        _text(activity, "modulename", str(item["type"]))
        _text(activity, "title", str(item.get("title") or ""))
        _text(activity, "directory", _activity_directory(item))
        _text(activity, "insubsection", "")
    sections = ET.SubElement(contents, "sections")
    for section in manifest.get("sections", []):
        node = ET.SubElement(sections, "section")
        _text(node, "sectionid", str(section["sectionid"]))
        _text(node, "title", _backup_section_title(section))
        _text(node, "directory", f"sections/section_{section['sectionid']}")
        _text(node, "parentcmid", str(section.get("parentcmid") or ""))
        _text(node, "modname", str(section.get("parent_modname") or ""))
    backup_settings = ET.SubElement(info, "settings")
    _append_backup_settings(backup_settings, manifest)
    return _xml_bytes(root)


def _append_backup_settings(parent: ET.Element, manifest: dict[str, Any]) -> None:
    for name, value in {
        "filename": "standalone-mdx2moodle.mbz",
        "imscc11": "0",
        "users": "0",
        "anonymize": "0",
        "role_assignments": "0",
        "activities": "1",
        "blocks": "1",
        "files": "1",
        "filters": "1",
        "comments": "0",
        "badges": "1",
        "calendarevents": "0",
        "userscompletion": "0",
        "logs": "0",
        "grade_histories": "0",
        "questionbank": "1",
        "groups": "1",
        "competencies": "1",
        "customfield": "1",
        "contentbankcontent": "1",
        "xapistate": "0",
        "legacyfiles": "1",
    }.items():
        _backup_setting(parent, "root", name, value)
    for section in manifest.get("sections", []):
        section_key = f"section_{section['sectionid']}"
        _backup_setting(parent, "section", f"{section_key}_included", "1", target=section_key)
        _backup_setting(parent, "section", f"{section_key}_userinfo", "0", target=section_key)
        for item in section.get("items", []):
            activity_key = f"{item['type']}_{item['moduleid']}"
            _backup_setting(parent, "activity", f"{activity_key}_included", "1", target=activity_key)
            _backup_setting(parent, "activity", f"{activity_key}_userinfo", _activity_userinfo(item), target=activity_key)


def _activity_userinfo(item: dict[str, Any]) -> str:
    if item.get("type") != "board":
        return "0"
    for column in item.get("columns", []):
        if column.get("notes"):
            return "1"
    return "0"


def _backup_setting(
    parent: ET.Element,
    level: str,
    name: str,
    value: str,
    *,
    target: str | None = None,
) -> None:
    setting = ET.SubElement(parent, "setting")
    _text(setting, "level", level)
    if level == "section":
        _text(setting, "section", target or "")
    elif level == "activity":
        _text(setting, "activity", target or "")
    _text(setting, "name", name)
    _text(setting, "value", value)


def _course_xml(manifest: dict[str, Any]) -> bytes:
    course = manifest.get("course", {})
    settings = course.get("settings", {})
    root = ET.Element("course", {"id": COURSE_ID, "contextid": COURSE_CONTEXT_ID})
    _text(root, "shortname", str(course.get("shortname") or ""))
    _text(root, "fullname", str(course.get("title") or ""))
    _text(root, "idnumber", "")
    _text(root, "summary", "")
    _text(root, "summaryformat", "1")
    _text(root, "format", str(course.get("format") or "topics"))
    _text(root, "showgrades", "1")
    _text(root, "newsitems", "3")
    _text(root, "startdate", _scalar(settings.get("startdate", 0)))
    _text(root, "enddate", _scalar(settings.get("enddate", 0)))
    _text(root, "marker", "0")
    _text(root, "maxbytes", "0")
    _text(root, "legacyfiles", "0")
    _text(root, "showreports", "0")
    _text(root, "visible", _scalar(settings.get("visible", True)))
    _text(root, "groupmode", "0")
    _text(root, "groupmodeforce", "0")
    _text(root, "defaultgroupingid", "0")
    _text(root, "lang", "")
    _text(root, "theme", "")
    _text(root, "timecreated", TIMESTAMP)
    _text(root, "timemodified", TIMESTAMP)
    _text(root, "requested", "0")
    _text(root, "showactivitydates", "1")
    _text(root, "showcompletionconditions", "1")
    _text(root, "pdfexportfont", "$@NULL@$")
    _text(root, "enablecompletion", _scalar(settings.get("enablecompletion", True)))
    _text(root, "completionnotify", "0")
    category = ET.SubElement(root, "category", {"id": "1"})
    _text(category, "name", "Standalone")
    _text(category, "description", "")
    ET.SubElement(root, "tags")
    ET.SubElement(root, "customfields")
    options = ET.SubElement(root, "courseformatoptions")
    for option in course.get("format_options", []):
        option_node = ET.SubElement(options, "courseformatoption")
        _text(option_node, "format", str(option.get("format") or course.get("format") or "topics"))
        _text(option_node, "sectionid", str(option.get("sectionid", "0")))
        _text(option_node, "name", str(option.get("name") or ""))
        _text(option_node, "value", str(option.get("value", "")))
    return _xml_bytes(root)


def _section_xml(section: dict[str, Any]) -> bytes:
    root = ET.Element("section", {"id": str(section["sectionid"])})
    _text(root, "number", str(section.get("index", 0)))
    _text(root, "name", str(section.get("title") or "$@NULL@$"))
    _text(root, "summary", str(section.get("summary_html") or ""))
    _text(root, "summaryformat", "1")
    _text(root, "sequence", ",".join(str(item["moduleid"]) for item in section.get("items", [])))
    _text(root, "visible", "1")
    _text(root, "availabilityjson", "$@NULL@$")
    _text(root, "component", str(section.get("component") or "$@NULL@$"))
    _text(root, "itemid", str(section.get("itemid") or "$@NULL@$"))
    _text(root, "timemodified", TIMESTAMP)
    return _xml_bytes(root)


def _module_xml(section: dict[str, Any], item: dict[str, Any]) -> bytes:
    root = ET.Element("module", {"id": str(item["moduleid"]), "version": BACKUP_VERSION})
    _text(root, "modulename", str(item["type"]))
    _text(root, "sectionid", str(section["sectionid"]))
    _text(root, "sectionnumber", str(section.get("index", 0)))
    _text(root, "idnumber", "")
    _text(root, "added", TIMESTAMP)
    _text(root, "score", "0")
    _text(root, "indent", "0")
    visible = "1" if item.get("visible", True) else "0"
    _text(root, "visible", visible)
    _text(root, "visibleoncoursepage", visible)
    _text(root, "visibleold", visible)
    _text(root, "groupmode", "0")
    _text(root, "groupingid", "0")
    _text(root, "completion", "0")
    _text(root, "completiongradeitemnumber", "$@NULL@$")
    _text(root, "completionpassgrade", "0")
    _text(root, "completionview", "0")
    _text(root, "completionexpected", "0")
    _text(root, "availability", "$@NULL@$")
    _text(root, "showdescription", "0" if item["type"] in {"forum", "subsection", "board"} else "1")
    _text(root, "downloadcontent", "1")
    _text(root, "lang", "")
    ET.SubElement(root, "tags")
    return _xml_bytes(root)


def _activity_xml(item: dict[str, Any], file_pool: "_FilePool", source_base: Path) -> bytes:
    activity_id = _activity_instance_id(item)
    context_id = _activity_context_id(item)
    root = ET.Element("activity", {"id": activity_id, "moduleid": str(item["moduleid"]), "modulename": str(item["type"]), "contextid": context_id})
    if item["type"] == "label":
        label = ET.SubElement(root, "label", {"id": activity_id})
        _text(label, "name", str(item.get("title") or ""))
        _text(label, "intro", str(item.get("content_html") or ""))
        _text(label, "introformat", "1")
        _text(label, "timemodified", TIMESTAMP)
        return _xml_bytes(root)
    if item["type"] == "book":
        book = ET.SubElement(root, "book", {"id": activity_id})
        _text(book, "name", str(item.get("title") or ""))
        _text(book, "intro", "")
        _text(book, "introformat", "1")
        _text(book, "numbering", "1")
        _text(book, "navstyle", "1")
        _text(book, "customtitles", "0")
        _text(book, "timecreated", TIMESTAMP)
        _text(book, "timemodified", TIMESTAMP)
        chapters = ET.SubElement(book, "chapters")
        for index, page in enumerate(item.get("pages", []), start=1):
            chapter = ET.SubElement(chapters, "chapter", {"id": str(4100 + index)})
            _text(chapter, "pagenum", str(index))
            _text(chapter, "subchapter", str(int(page.get("subchapter", 0))))
            _text(chapter, "title", str(page.get("title") or f"Page {index}"))
            _text(chapter, "content", str(page.get("content_html") or ""))
            _text(chapter, "contentformat", "1")
            _text(chapter, "hidden", "0")
            _text(chapter, "timemodified", TIMESTAMP)
            _text(chapter, "importsrc", "")
        return _xml_bytes(root)
    if item["type"] == "quiz":
        quiz = ET.SubElement(root, "quiz", {"id": activity_id})
        _render_quiz(quiz, item, activity_id, context_id)
        return _xml_bytes(root)
    if item["type"] == "assign":
        assign = ET.SubElement(root, "assign", {"id": activity_id})
        _render_assign(assign, item)
        return _xml_bytes(root)
    if item["type"] == "forum":
        forum = ET.SubElement(root, "forum", {"id": activity_id})
        _render_forum(forum, item)
        return _xml_bytes(root)
    if item["type"] == "subsection":
        subsection = ET.SubElement(root, "subsection", {"id": activity_id})
        _text(subsection, "name", str(item.get("title") or ""))
        _text(subsection, "timemodified", TIMESTAMP)
        return _xml_bytes(root)
    if item["type"] == "choice":
        choice = ET.SubElement(root, "choice", {"id": activity_id})
        _render_choice(choice, item)
        return _xml_bytes(root)
    if item["type"] == "questionnaire":
        questionnaire = ET.SubElement(root, "questionnaire", {"id": activity_id})
        _render_questionnaire(questionnaire, item)
        return _xml_bytes(root)
    if item["type"] == "board":
        board = ET.SubElement(root, "board", {"id": activity_id})
        _render_board(board, item, activity_id)
        return _xml_bytes(root)
    if item["type"] == "folder":
        folder = ET.SubElement(root, "folder", {"id": activity_id})
        _text(folder, "name", str(item.get("title") or ""))
        _text(folder, "intro", str(item.get("content_html") or ""))
        _text(folder, "introformat", "1")
        _text(folder, "revision", "1")
        _text(folder, "timemodified", TIMESTAMP)
        _text(folder, "display", "0")
        _text(folder, "showexpanded", "1")
        _text(folder, "showdownloadfolder", "1")
        _text(folder, "forcedownload", "1")
        file_pool.add_directory(context_id, "mod_folder")
        for asset in item.get("files", []):
            file_pool.add_asset(context_id, "mod_folder", str(asset["path"]), source_base)
        return _xml_bytes(root)
    if item["type"] == "geogebra":
        geogebra = ET.SubElement(root, "geogebra", {"id": activity_id})
        _text(geogebra, "name", str(item.get("title") or ""))
        _text(geogebra, "intro", str(item.get("content_html") or ""))
        _text(geogebra, "introformat", "1")
        file_path = str(item.get("file_path") or "")
        _text(geogebra, "url", Path(file_path).name)
        _text(geogebra, "attributes", "enableRightClick=0&enableLabelDrags=1&showResetIcon=1&showMenuBar=0&showToolBar=0&showToolBarHelp=0&showAlgebraInput=0&useBrowserForJS=1&language=de")
        _text(geogebra, "urlggb", "")
        _text(geogebra, "seed", "0")
        settings = item.get("settings", {})
        _text(geogebra, "width", str(settings.get("width", "")))
        _text(geogebra, "height", str(settings.get("height", "")))
        _text(geogebra, "showsubmit", "0")
        _text(geogebra, "grade", "100")
        _text(geogebra, "autograde", "0")
        _text(geogebra, "maxattempts", "-1")
        _text(geogebra, "grademethod", "1")
        _text(geogebra, "timeavailable", "0")
        _text(geogebra, "timedue", "0")
        _text(geogebra, "timecreated", TIMESTAMP)
        _text(geogebra, "timemodified", TIMESTAMP)
        ET.SubElement(geogebra, "attempts")
        if file_path:
            file_pool.add_directory(context_id, "mod_geogebra")
            file_pool.add_asset(context_id, "mod_geogebra", file_path, source_base)
        return _xml_bytes(root)
    raise ValueError(f"Unsupported directive {item['type']!r}")


def _render_quiz(root: ET.Element, item: dict[str, Any], quiz_id: str, context_id: str) -> None:
    questions = item.get("questions", [])
    _text(root, "name", str(item.get("title") or ""))
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    for key, value in {
        "timeopen": "0",
        "timeclose": "0",
        "timelimit": "0",
        "overduehandling": "autosubmit",
        "graceperiod": "0",
        "preferredbehaviour": "deferredfeedback",
        "canredoquestions": "0",
        "attempts_number": "3",
        "attemptonlast": "0",
        "grademethod": "1",
        "decimalpoints": "2",
        "questiondecimalpoints": "-1",
        "reviewattempt": "69888",
        "reviewcorrectness": "4352",
        "reviewmaxmarks": "69888",
        "reviewmarks": "4352",
        "reviewspecificfeedback": "4352",
        "reviewgeneralfeedback": "4352",
        "reviewrightanswer": "4352",
        "reviewoverallfeedback": "4352",
        "questionsperpage": "1",
        "navmethod": "free",
        "shuffleanswers": "1",
        "sumgrades": f"{sum(float(question.get('maxmark', '1.0000000')) for question in questions):.5f}",
        "grade": "100.00000",
        "timecreated": TIMESTAMP,
        "timemodified": TIMESTAMP,
        "password": "",
        "subnet": "",
        "browsersecurity": "-",
        "delay1": "0",
        "delay2": "0",
        "showuserpicture": "0",
        "showblocks": "0",
        "completionattemptsexhausted": "0",
        "completionminattempts": "0",
        "allowofflineattempts": "0",
    }.items():
        _text(root, key, value)
    ET.SubElement(root, "subplugin_quizaccess_seb_quiz")
    ET.SubElement(root, "quiz_grade_items")
    instances = ET.SubElement(root, "question_instances")
    for index, question in enumerate(questions):
        instance = ET.SubElement(instances, "question_instance", {"id": str(6500 + index)})
        _text(instance, "quizid", quiz_id)
        _text(instance, "slot", str(question.get("slot", index + 1)))
        _text(instance, "page", str(question.get("page", index + 1)))
        _text(instance, "displaynumber", "$@NULL@$")
        _text(instance, "requireprevious", "0")
        _text(instance, "maxmark", str(question.get("maxmark", "1.0000000")))
        _text(instance, "quizgradeitemid", "$@NULL@$")
        reference = ET.SubElement(instance, "question_reference", {"id": str(6600 + index)})
        _text(reference, "usingcontextid", context_id)
        _text(reference, "component", "mod_quiz")
        _text(reference, "questionarea", "slot")
        _text(reference, "questionbankentryid", str(question.get("questionbankentryid", 6000 + index)))
        _text(reference, "version", "$@NULL@$")
    sections = ET.SubElement(root, "sections")
    section = ET.SubElement(sections, "section", {"id": "1"})
    _text(section, "firstslot", "1")
    _text(section, "heading", "")
    _text(section, "shufflequestions", "0")
    feedbacks = ET.SubElement(root, "feedbacks")
    feedback = ET.SubElement(feedbacks, "feedback", {"id": "1"})
    _text(feedback, "feedbacktext", "")
    _text(feedback, "feedbacktextformat", "1")
    _text(feedback, "mingrade", "0.00000")
    _text(feedback, "maxgrade", "101.00000")
    ET.SubElement(root, "overrides")
    ET.SubElement(root, "grades")
    ET.SubElement(root, "attempts")


def _questions_xml(manifest: dict[str, Any]) -> bytes:
    root = ET.Element("question_categories")
    category = ET.SubElement(root, "question_category", {"id": "5999"})
    _text(category, "name", "mdx2moodle")
    _text(category, "contextid", COURSE_CONTEXT_ID)
    _text(category, "contextlevel", "50")
    _text(category, "contextinstanceid", COURSE_ID)
    _text(category, "info", "")
    _text(category, "infoformat", "0")
    _text(category, "stamp", "standalone+mdx2moodle")
    _text(category, "parent", "0")
    _text(category, "sortorder", "999")
    _text(category, "idnumber", "$@NULL@$")
    entries = ET.SubElement(category, "question_bank_entries")
    for index, question in enumerate(_manifest_questions(manifest)):
        entry_id = str(question.get("questionbankentryid", 6000 + index))
        entry = ET.SubElement(entries, "question_bank_entry", {"id": entry_id})
        _text(entry, "questioncategoryid", "5999")
        _text(entry, "idnumber", "$@NULL@$")
        _text(entry, "ownerid", "$@NULL@$")
        version = ET.SubElement(entry, "question_version")
        versions = ET.SubElement(version, "question_versions", {"id": str(6100 + index)})
        _text(versions, "version", "1")
        _text(versions, "status", "ready")
        questions_node = ET.SubElement(versions, "questions")
        question_node = ET.SubElement(questions_node, "question", {"id": str(6300 + index)})
        _render_question(question_node, question, index)
    return _xml_bytes(root)


def _render_question(root: ET.Element, question: dict[str, Any], index: int) -> None:
    _text(root, "parent", "0")
    _text(root, "name", str(question.get("name") or f"Question {index + 1}"))
    _text(root, "questiontext", str(question.get("question_html") or ""))
    _text(root, "questiontextformat", "1")
    _text(root, "generalfeedback", "")
    _text(root, "generalfeedbackformat", "1")
    _text(root, "defaultmark", str(question.get("defaultmark", "1.0000000")))
    _text(root, "penalty", str(question.get("penalty", "0.3333333")))
    _text(root, "qtype", "multichoice")
    _text(root, "length", "1")
    _text(root, "stamp", f"standalone+question+{index}")
    _text(root, "timecreated", TIMESTAMP)
    _text(root, "timemodified", TIMESTAMP)
    _text(root, "createdby", "$@NULL@$")
    _text(root, "modifiedby", "$@NULL@$")
    plugin = ET.SubElement(root, "plugin_qtype_multichoice_question")
    answers = ET.SubElement(plugin, "answers")
    for answer_index, answer in enumerate(question.get("answers", [])):
        answer_node = ET.SubElement(answers, "answer", {"id": str(6400 + index * 100 + answer_index)})
        _text(answer_node, "answertext", str(answer.get("text_html") or ""))
        _text(answer_node, "answerformat", "1")
        _text(answer_node, "fraction", str(answer.get("fraction", "0.0000000")))
        _text(answer_node, "feedback", "")
        _text(answer_node, "feedbackformat", "1")
    multichoice = ET.SubElement(plugin, "multichoice", {"id": str(6700 + index)})
    _text(multichoice, "layout", "0")
    _text(multichoice, "single", "1" if question.get("single", True) else "0")
    _text(multichoice, "shuffleanswers", "1" if question.get("shuffleanswers", True) else "0")
    _text(multichoice, "correctfeedback", "")
    _text(multichoice, "correctfeedbackformat", "1")
    _text(multichoice, "partiallycorrectfeedback", "")
    _text(multichoice, "partiallycorrectfeedbackformat", "1")
    _text(multichoice, "incorrectfeedback", "")
    _text(multichoice, "incorrectfeedbackformat", "1")
    _text(multichoice, "answernumbering", str(question.get("answernumbering", "none")))
    _text(multichoice, "shownumcorrect", "0")
    _text(multichoice, "showstandardinstruction", "0")


def _render_assign(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    _text(root, "name", str(item.get("title") or ""))
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    _text(root, "alwaysshowdescription", "1")
    _text(root, "submissiondrafts", "0")
    _text(root, "sendnotifications", "0")
    _text(root, "sendlatenotifications", "0")
    _text(root, "sendstudentnotifications", "1")
    _text(root, "duedate", "0")
    _text(root, "cutoffdate", "0")
    _text(root, "gradingduedate", _scalar(settings.get("gradingduedate", 0)))
    _text(root, "allowsubmissionsfromdate", "0")
    _text(root, "grade", _scalar(settings.get("grade", 100)))
    _text(root, "timemodified", TIMESTAMP)
    _text(root, "completionsubmit", _scalar(settings.get("completionsubmit", False)))
    _text(root, "requiresubmissionstatement", "0")
    _text(root, "teamsubmission", "0")
    _text(root, "requireallteammemberssubmit", "0")
    _text(root, "teamsubmissiongroupingid", "0")
    _text(root, "blindmarking", "0")
    _text(root, "hidegrader", "0")
    _text(root, "revealidentities", "0")
    _text(root, "attemptreopenmethod", str(settings.get("attemptreopenmethod", "none")))
    _text(root, "maxattempts", _scalar(settings.get("maxattempts", 1)))
    ET.SubElement(root, "submissions")
    ET.SubElement(root, "grades")
    configs = ET.SubElement(root, "plugin_configs")
    plugin_defaults = {
        ("onlinetext", "assignsubmission"): settings.get("submission_onlinetext", False),
        ("file", "assignsubmission"): settings.get("submission_file", False),
        ("comments", "assignsubmission"): settings.get("submission_comments", False),
        ("comments", "assignfeedback"): settings.get("feedback_comments", False),
        ("editpdf", "assignfeedback"): settings.get("feedback_editpdf", False),
    }
    for index, ((plugin, subtype), enabled) in enumerate(plugin_defaults.items(), start=1):
        config = ET.SubElement(configs, "plugin_config", {"id": str(index)})
        _text(config, "plugin", plugin)
        _text(config, "subtype", subtype)
        _text(config, "name", "enabled")
        _text(config, "value", "1" if enabled else "0")


def _render_forum(root: ET.Element, item: dict[str, Any]) -> None:
    _text(root, "type", "news")
    _text(root, "name", str(item.get("title") or ""))
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    for key, value in {
        "duedate": "0",
        "cutoffdate": "0",
        "assessed": "0",
        "assesstimestart": "0",
        "assesstimefinish": "0",
        "scale": "0",
        "maxbytes": "0",
        "maxattachments": "1",
        "forcesubscribe": "1",
        "trackingtype": "1",
        "rsstype": "0",
        "rssarticles": "0",
        "timemodified": TIMESTAMP,
        "warnafter": "0",
        "blockafter": "0",
        "blockperiod": "0",
        "completiondiscussions": "0",
        "completionreplies": "0",
        "completionposts": "0",
        "displaywordcount": "0",
        "lockdiscussionafter": "0",
        "grade_forum": "0",
    }.items():
        _text(root, key, value)
    for tag in ("discussions", "subscriptions", "digests", "readposts", "trackedprefs", "poststags", "grades"):
        ET.SubElement(root, tag)


def _render_choice(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    _text(root, "name", str(item.get("title") or ""))
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    for key, value in {
        "publish": _scalar(settings.get("publish", 0)),
        "showresults": _scalar(settings.get("showresults", 0)),
        "display": _scalar(settings.get("display", 0)),
        "allowupdate": _scalar(settings.get("allowupdate", True)),
        "allowmultiple": _scalar(settings.get("allowmultiple", True)),
        "showunanswered": _scalar(settings.get("showunanswered", True)),
        "limitanswers": _scalar(settings.get("limitanswers", True)),
        "timeopen": _scalar(settings.get("timeopen", 0)),
        "timeclose": _scalar(settings.get("timeclose", 0)),
        "timemodified": TIMESTAMP,
        "completionsubmit": _scalar(settings.get("completionsubmit", False)),
        "showpreview": _scalar(settings.get("showpreview", True)),
        "includeinactive": _scalar(settings.get("includeinactive", False)),
        "showavailable": _scalar(settings.get("showavailable", True)),
    }.items():
        _text(root, key, value)
    options = ET.SubElement(root, "options")
    for index, option in enumerate(item.get("options", []), start=1):
        option_node = ET.SubElement(options, "option", {"id": str(8000 + index)})
        _text(option_node, "text", str(option.get("text") or ""))
        _text(option_node, "maxanswers", _scalar(option.get("maxanswers", index)))
        _text(option_node, "timemodified", TIMESTAMP)
    ET.SubElement(root, "answers")


def _render_questionnaire(root: ET.Element, item: dict[str, Any]) -> None:
    settings = item.get("settings", {})
    title = str(item.get("title") or "")
    _text(root, "course", COURSE_ID)
    _text(root, "name", title)
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    _text(root, "qtype", _scalar(settings.get("qtype", 1)))
    _text(root, "respondenttype", str(settings.get("respondenttype", "fullname")))
    _text(root, "resp_eligible", str(settings.get("resp_eligible", "all")))
    _text(root, "resp_view", _scalar(settings.get("resp_view", 2)))
    _text(root, "notifications", _scalar(settings.get("notifications", 2)))
    _text(root, "opendate", _scalar(settings.get("opendate", 0)))
    _text(root, "closedate", _scalar(settings.get("closedate", 0)))
    _text(root, "resume", _scalar(settings.get("resume", True)))
    _text(root, "navigate", _scalar(settings.get("navigate", True)))
    _text(root, "grade", _scalar(settings.get("grade", 0)))
    _text(root, "sid", _scalar(settings.get("sid", 1)))
    _text(root, "timemodified", TIMESTAMP)
    _text(root, "completionsubmit", _scalar(settings.get("completionsubmit", False)))
    _text(root, "autonum", _scalar(settings.get("autonum", 3)))
    _text(root, "removeafter", _scalar(settings.get("removeafter", 0)))
    surveys = ET.SubElement(root, "surveys")
    survey = ET.SubElement(surveys, "survey", {"id": _scalar(settings.get("sid", 1))})
    _text(survey, "name", title)
    _text(survey, "courseid", COURSE_ID)
    _text(survey, "realm", str(settings.get("realm", "private")))
    _text(survey, "status", _scalar(settings.get("status", 0)))
    _text(survey, "title", title)
    _text(survey, "email", str(settings.get("email", "")))
    _text(survey, "subtitle", str(settings.get("subtitle", "")))
    _text(survey, "info", str(settings.get("survey_info", settings.get("info", ""))))
    _text(survey, "theme", str(settings.get("theme", "")))
    _text(survey, "thanks_page", str(settings.get("thanks_page", "")))
    _text(survey, "thank_head", str(settings.get("thank_head", "")))
    _text(survey, "thank_body", str(settings.get("thank_body", "")))
    _text(survey, "feedbacksections", _scalar(settings.get("feedbacksections", 0)))
    _text(survey, "feedbacknotes", "")
    _text(survey, "feedbackscores", _scalar(settings.get("feedbackscores", 0)))
    _text(survey, "chart_type", str(settings.get("chart_type", "$@NULL@$")))
    questions = ET.SubElement(survey, "questions")
    survey_id = _scalar(settings.get("sid", 1))
    survey_questions = item.get("survey_questions", [])
    question_ids, choice_ids = _questionnaire_dependency_maps(survey_questions)
    for index, question in enumerate(survey_questions, start=1):
        _render_questionnaire_question(questions, question, index, survey_id, question_ids, choice_ids)
    ET.SubElement(survey, "fb_sections")
    ET.SubElement(root, "responses")


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


def _render_questionnaire_question(
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
    _text(node, "surveyid", survey_id)
    _text(node, "name", str(question.get("name") or "$@NULL@$"))
    _text(node, "type_id", str(QUESTIONNAIRE_TYPE_IDS.get(qtype, qtype)))
    _text(node, "result_id", "$@NULL@$")
    _text(node, "length", _scalar(question.get("length", _questionnaire_default_length(qtype))))
    _text(node, "precise", _scalar(question.get("precise", _questionnaire_default_precise(qtype))))
    _text(node, "position", _scalar(question.get("position", index)))
    _text(node, "content", str(question.get("content") or ("break" if qtype == "pagebreak" else "")))
    _text(node, "required", "y" if question.get("required", False) else "n")
    _text(node, "deleted", str(question.get("deleted", "n")))
    _text(node, "extradata", _questionnaire_extradata(question, qtype))
    choices = ET.SubElement(node, "quest_choices")
    for choice_index, choice in enumerate(question.get("choices", []), start=1):
        choice_node = ET.SubElement(choices, "quest_choice", {"id": str(9100 + index * 100 + choice_index)})
        _text(choice_node, "question_id", question_id)
        _text(choice_node, "content", str(choice.get("content") or ""))
        _text(choice_node, "value", _scalar(choice.get("value", "$@NULL@$")))
    dependencies = ET.SubElement(node, "quest_dependencies")
    _render_questionnaire_dependencies(dependencies, question, index, question_id, survey_id, question_ids, choice_ids)


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


def _render_questionnaire_dependencies(
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
        _text(dependency_node, "dependquestionid", dependquestionid)
        _text(dependency_node, "dependchoiceid", dependchoiceid)
        _text(dependency_node, "dependlogic", str(logics[min(dependency_index - 1, len(logics) - 1)]))
        _text(dependency_node, "questionid", question_id)
        _text(dependency_node, "surveyid", survey_id)
        _text(dependency_node, "dependandor", str(joins[min(dependency_index - 1, len(joins) - 1)]))


def _split_dependency_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _questionnaire_default_length(qtype: str) -> int:
    if qtype == "text":
        return 20
    if qtype == "textarea":
        return 20
    return 0


def _questionnaire_default_precise(qtype: str) -> int:
    if qtype == "textarea":
        return 25
    return 0


def _questionnaire_extradata(question: dict[str, Any], qtype: str) -> str:
    if question.get("extradata") is not None:
        return str(question["extradata"])
    if qtype == "rate":
        return "[]"
    if qtype == "pagebreak":
        return "$@NULL@$"
    if qtype == "slider":
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


def _render_board(root: ET.Element, item: dict[str, Any], board_id: str) -> None:
    settings = item.get("settings", {})
    _text(root, "course", COURSE_ID)
    _text(root, "name", str(item.get("title") or ""))
    _text(root, "timemodified", TIMESTAMP)
    _text(root, "intro", str(item.get("content_html") or ""))
    _text(root, "introformat", "1")
    _text(root, "historyid", _scalar(settings.get("historyid", int(board_id) + 750)))
    _text(root, "background_color", str(settings.get("background_color", "bdb7ff")))
    _text(root, "addrating", _scalar(settings.get("addrating", 0)))
    _text(root, "hideheaders", _scalar(settings.get("hideheaders", 0)))
    _text(root, "sortby", _scalar(settings.get("sortby", 3)))
    _text(root, "postby", _scalar(settings.get("postby", 0)))
    _text(root, "userscanedit", _scalar(settings.get("userscanedit", 0)))
    _text(root, "singleusermode", _scalar(settings.get("singleusermode", 0)))
    _text(root, "completionnotes", _scalar(settings.get("completionnotes", 0)))
    _text(root, "embed", _scalar(settings.get("embed", 0)))
    columns = ET.SubElement(root, "columns")
    for index, column in enumerate(item.get("columns", []), start=1):
        column_id = str(8100 + index)
        column_node = ET.SubElement(columns, "column", {"id": column_id})
        _text(column_node, "boardid", board_id)
        _text(column_node, "name", str(column.get("name") or ""))
        _text(column_node, "sortorder", _scalar(column.get("sortorder", index)))
        notes = ET.SubElement(column_node, "notes")
        for note_index, note in enumerate(column.get("notes", []), start=1):
            note_node = ET.SubElement(notes, "note", {"id": str(8200 + index * 100 + note_index)})
            _text(note_node, "columnid", column_id)
            _text(note_node, "ownerid", _scalar(note.get("ownerid", 2)))
            _text(note_node, "userid", _scalar(note.get("userid", 2)))
            _text(note_node, "groupid", _scalar(note.get("groupid", "")))
            _text(note_node, "content", str(note.get("content") or ""))
            _text(note_node, "heading", str(note.get("heading") or ""))
            _text(note_node, "type", _scalar(note.get("type", 0)))
            _text(note_node, "info", str(note.get("info") or ""))
            _text(note_node, "url", str(note.get("url") or ""))
            _text(note_node, "filename", str(note.get("filename") or ""))
            _text(note_node, "timecreated", TIMESTAMP)
            _text(note_node, "sortorder", _scalar(note.get("sortorder", note_index - 1)))
            _text(note_node, "deleted", _scalar(note.get("deleted", 0)))
            ET.SubElement(note_node, "comments")
            ET.SubElement(note_node, "ratings")


class _FilePool:
    def __init__(self) -> None:
        self._records: list[dict[str, str]] = []
        self._blobs: dict[str, bytes] = {}
        self._next_id = 7000

    def add_directory(self, contextid: str, component: str) -> None:
        self._records.append(
            {
                "id": str(self._next_id),
                "contenthash": hashlib.sha1(b"").hexdigest(),
                "contextid": contextid,
                "component": component,
                "filename": ".",
                "filesize": "0",
                "mimetype": "$@NULL@$",
                "source": "$@NULL@$",
                "userid": "2",
                "author": "$@NULL@$",
                "license": "$@NULL@$",
            }
        )
        self._next_id += 1

    def add_asset(self, contextid: str, component: str, asset_path: str, source_base: Path) -> None:
        path = Path(asset_path)
        if not path.is_absolute():
            path = source_base / path
        data = path.read_bytes()
        contenthash = hashlib.sha1(data).hexdigest()
        filename = path.name
        self._blobs[f"files/{contenthash[:2]}/{contenthash}"] = data
        self._records.append(
            {
                "id": str(self._next_id),
                "contenthash": contenthash,
                "contextid": contextid,
                "component": component,
                "filename": filename,
                "filesize": str(len(data)),
                "mimetype": _mimetype(filename),
                "source": filename,
                "userid": "2",
                "author": "Moodle MDX",
                "license": "allrightsreserved",
            }
        )
        self._next_id += 1

    def render(self) -> tuple[bytes, dict[str, bytes]]:
        root = ET.Element("files")
        for record in self._records:
            file_node = ET.SubElement(root, "file", {"id": record["id"]})
            _text(file_node, "contenthash", record["contenthash"])
            _text(file_node, "contextid", record["contextid"])
            _text(file_node, "component", record["component"])
            _text(file_node, "filearea", "content")
            _text(file_node, "itemid", "0")
            _text(file_node, "filepath", "/")
            _text(file_node, "filename", record["filename"])
            _text(file_node, "userid", record["userid"])
            _text(file_node, "filesize", record["filesize"])
            _text(file_node, "mimetype", record["mimetype"])
            _text(file_node, "status", "0")
            _text(file_node, "timecreated", TIMESTAMP)
            _text(file_node, "timemodified", TIMESTAMP)
            _text(file_node, "source", record["source"])
            _text(file_node, "author", record["author"])
            _text(file_node, "license", record["license"])
            _text(file_node, "sortorder", "0")
            _text(file_node, "repositorytype", "$@NULL@$")
            _text(file_node, "repositoryid", "$@NULL@$")
            _text(file_node, "reference", "$@NULL@$")
        return _xml_bytes(root), dict(self._blobs)

    def file_ids_for_context(self, contextid: str) -> list[str]:
        return [record["id"] for record in self._records if record["contextid"] == contextid]


def _manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for section in manifest.get("sections", []) for item in section.get("items", [])]


def _manifest_questions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [question for item in _manifest_items(manifest) if item.get("type") == "quiz" for question in item.get("questions", [])]


def _assign_question_ids(manifest: dict[str, Any]) -> None:
    for index, question in enumerate(_manifest_questions(manifest)):
        question["questionbankentryid"] = str(6000 + index)


def _activity_directory(item: dict[str, Any]) -> str:
    return f"activities/{item['type']}_{item['moduleid']}"


def _activity_instance_id(item: dict[str, Any]) -> str:
    return str(4000 + int(item["moduleid"]) - 3000)


def _activity_context_id(item: dict[str, Any]) -> str:
    return str(5000 + int(item["moduleid"]) - 3000)


def _activity_inforef_xml(item: dict[str, Any], file_pool: "_FilePool") -> bytes:
    root = ET.Element("inforef")
    if item.get("type") == "quiz" and item.get("questions"):
        categoryref = ET.SubElement(root, "question_categoryref")
        category = ET.SubElement(categoryref, "question_category")
        _text(category, "id", "5999")
    file_ids = file_pool.file_ids_for_context(_activity_context_id(item))
    if file_ids:
        fileref = ET.SubElement(root, "fileref")
        for file_id in file_ids:
            file_node = ET.SubElement(fileref, "file")
            _text(file_node, "id", file_id)
    return _xml_bytes(root)


def _backup_section_title(section: dict[str, Any]) -> str:
    if int(section.get("index", 0)) == 0 and not section.get("title"):
        return "0"
    return str(section.get("title") or "")


def _activity_grades_xml() -> bytes:
    root = ET.Element("activity_gradebook")
    ET.SubElement(root, "grade_items")
    ET.SubElement(root, "grade_letters")
    return _xml_bytes(root)


def _gradebook_xml() -> bytes:
    root = ET.Element("gradebook")
    ET.SubElement(root, "attributes")
    categories = ET.SubElement(root, "grade_categories")
    category = ET.SubElement(categories, "grade_category", {"id": "1"})
    _text(category, "parent", "$@NULL@$")
    _text(category, "depth", "1")
    _text(category, "path", "/1/")
    _text(category, "fullname", "?")
    _text(category, "aggregation", "13")
    _text(category, "timecreated", TIMESTAMP)
    _text(category, "timemodified", TIMESTAMP)
    ET.SubElement(root, "grade_items")
    ET.SubElement(root, "grade_letters")
    settings = ET.SubElement(root, "grade_settings")
    setting = ET.SubElement(settings, "grade_setting", {"id": ""})
    _text(setting, "name", "minmaxtouse")
    _text(setting, "value", "1")
    return _xml_bytes(root)


def _groups_xml() -> bytes:
    root = ET.Element("groups")
    ET.SubElement(root, "groupcustomfields")
    groupings = ET.SubElement(root, "groupings")
    ET.SubElement(groupings, "groupingcustomfields")
    return _xml_bytes(root)


def _roles_xml() -> bytes:
    root = ET.Element("roles_definition")
    role = ET.SubElement(root, "role", {"id": "5"})
    _text(role, "name", "Schüler*in")
    _text(role, "shortname", "student")
    _text(role, "nameincourse", "$@NULL@$")
    _text(role, "description", "")
    _text(role, "sortorder", "5")
    _text(role, "archetype", "student")
    return _xml_bytes(root)


def _enrolments_xml() -> bytes:
    root = ET.Element("enrolments")
    enrols = ET.SubElement(root, "enrols")
    enrol = ET.SubElement(enrols, "enrol", {"id": "1"})
    _text(enrol, "enrol", "manual")
    _text(enrol, "status", "0")
    _text(enrol, "name", "$@NULL@$")
    _text(enrol, "enrolperiod", "0")
    _text(enrol, "enrolstartdate", "0")
    _text(enrol, "enrolenddate", "0")
    _text(enrol, "roleid", "5")
    _text(enrol, "timecreated", TIMESTAMP)
    _text(enrol, "timemodified", TIMESTAMP)
    ET.SubElement(enrol, "user_enrolments")
    return _xml_bytes(root)


def _empty_xml(root_name: str) -> bytes:
    return _xml_bytes(ET.Element(root_name))


def _text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = value
    return node


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value)


def _mimetype(filename: str) -> str:
    if filename.lower().endswith(".ggb"):
        return "application/zip"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root,
        encoding="utf-8",
        short_empty_elements=False,
    )


def _write_deterministic_tar_gz(output_path: Path, files: dict[str, bytes]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    directories = _directories_for(files)
    with output_path.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as gz_out:
            with tarfile.open(fileobj=gz_out, mode="w") as archive:
                for directory in sorted(directories):
                    info = tarfile.TarInfo(directory)
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    archive.addfile(info)
                for path in sorted(files):
                    data = files[path]
                    info = tarfile.TarInfo(path)
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    info.size = len(data)
                    archive.addfile(info, _BytesReader(data))


def _directories_for(files: dict[str, bytes]) -> set[str]:
    directories: set[str] = set()
    for path in files:
        parent = Path(path).parent
        parts = parent.parts
        current = ""
        for part in parts:
            if part in {"", "."}:
                continue
            current = f"{current}/{part}" if current else part
            directories.add(current)
    return directories


class _BytesReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk
