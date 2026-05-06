from __future__ import annotations

import hashlib
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .inspect import inspect_mbz


@dataclass(slots=True)
class CompareResult:
    matches: bool
    differences: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.matches:
            return "MBZ semantics match"
        return "\n".join(self.differences)


def compare_mbz_semantics(expected: str | Path, actual: str | Path) -> CompareResult:
    differences: list[str] = []
    expected_report = inspect_mbz(expected)
    actual_report = inspect_mbz(actual)

    for key in ("moodle_release", "backup_release", "format", "fullname", "shortname"):
        if expected_report.course.get(key) != actual_report.course.get(key):
            differences.append(
                f"course.{key}: expected {expected_report.course.get(key)!r}, got {actual_report.course.get(key)!r}"
            )

    expected_sections = [
        (
            section["index"],
            section["title"],
            section["summary"],
            section["sequence"],
            section.get("component", ""),
            section.get("itemid", ""),
            section.get("parentcmid", ""),
            section.get("modname", ""),
        )
        for section in expected_report.sections
    ]
    actual_sections = [
        (
            section["index"],
            section["title"],
            section["summary"],
            section["sequence"],
            section.get("component", ""),
            section.get("itemid", ""),
            section.get("parentcmid", ""),
            section.get("modname", ""),
        )
        for section in actual_report.sections
    ]
    if expected_sections != actual_sections:
        differences.append("section order/title/summary/sequence differs")

    expected_activities = [
        (item["sectionid"], item["moduleid"], item["type"], item["title"])
        for item in expected_report.activities
    ]
    actual_activities = [
        (item["sectionid"], item["moduleid"], item["type"], item["title"])
        for item in actual_report.activities
    ]
    if expected_activities != actual_activities:
        differences.append("activity section/module/type/title sequence differs")

    if expected_report.activity_counts != actual_report.activity_counts:
        differences.append(
            f"activity counts differ: expected {expected_report.activity_counts}, got {actual_report.activity_counts}"
        )

    expected_files = [(item["path"], item["sha1"], item["size"]) for item in expected_report.file_blobs]
    actual_files = [(item["path"], item["sha1"], item["size"]) for item in actual_report.file_blobs]
    if expected_files != actual_files:
        differences.append("file pool differs")

    if _course_xml_fingerprint(expected) != _course_xml_fingerprint(actual):
        differences.append("course XML fingerprint differs")

    if _backup_xml_fingerprint(expected) != _backup_xml_fingerprint(actual):
        differences.append("backup XML fingerprint differs")

    expected_questions = _question_fingerprint(expected)
    actual_questions = _question_fingerprint(actual)
    if expected_questions != actual_questions:
        differences.append("question bank fingerprint differs")

    expected_activity_xml = _activity_xml_fingerprint(expected)
    actual_activity_xml = _activity_xml_fingerprint(actual)
    if expected_activity_xml != actual_activity_xml:
        differences.append("activity XML content fingerprint differs")

    return CompareResult(matches=not differences, differences=differences)


def _question_fingerprint(path: str | Path) -> list[tuple[str, str, str, tuple[tuple[str, str], ...]]]:
    with tarfile.open(path, "r:gz") as archive:
        root = ET.fromstring(archive.extractfile("questions.xml").read())  # type: ignore[union-attr]
    questions: list[tuple[str, str, str, tuple[tuple[str, str], ...]]] = []
    for question in root.findall(".//question"):
        questions.append(
            (
                question.findtext("name", ""),
                question.findtext("qtype", ""),
                question.findtext("questiontext", ""),
                tuple(
                    (
                        answer.findtext("answertext", ""),
                        answer.findtext("fraction", ""),
                    )
                    for answer in question.findall("plugin_qtype_multichoice_question/answers/answer")
                ),
            )
        )
    return questions


def _course_xml_fingerprint(path: str | Path) -> tuple[Any, ...]:
    with tarfile.open(path, "r:gz") as archive:
        root = ET.fromstring(archive.extractfile("course/course.xml").read())  # type: ignore[union-attr]
    return (
        root.findtext("shortname", ""),
        root.findtext("fullname", ""),
        root.findtext("summary", ""),
        root.findtext("summaryformat", ""),
        root.findtext("format", ""),
        root.findtext("showgrades", ""),
        root.findtext("newsitems", ""),
        root.findtext("startdate", ""),
        root.findtext("enddate", ""),
        root.findtext("visible", ""),
        root.findtext("groupmode", ""),
        root.findtext("groupmodeforce", ""),
        root.findtext("showactivitydates", ""),
        root.findtext("showcompletionconditions", ""),
        root.findtext("enablecompletion", ""),
        [
            (
                option.findtext("format", ""),
                option.findtext("sectionid", ""),
                option.findtext("name", ""),
                option.findtext("value", ""),
            )
            for option in root.findall("courseformatoptions/courseformatoption")
        ],
    )


def _backup_xml_fingerprint(path: str | Path) -> tuple[Any, ...]:
    with tarfile.open(path, "r:gz") as archive:
        root = ET.fromstring(archive.extractfile("moodle_backup.xml").read())  # type: ignore[union-attr]
    return (
        root.findtext("information/moodle_version", ""),
        root.findtext("information/moodle_release", ""),
        root.findtext("information/backup_version", ""),
        root.findtext("information/backup_release", ""),
        root.findtext("information/include_files", ""),
        root.findtext("information/original_course_format", ""),
        root.findtext("information/original_course_fullname", ""),
        root.findtext("information/original_course_shortname", ""),
        root.findtext("information/original_course_startdate", ""),
        root.findtext("information/original_course_enddate", ""),
        [
            (
                activity.findtext("moduleid", ""),
                activity.findtext("sectionid", ""),
                activity.findtext("modulename", ""),
                activity.findtext("title", ""),
                activity.findtext("directory", ""),
            )
            for activity in root.findall("information/contents/activities/activity")
        ],
        [
            (
                section.findtext("sectionid", ""),
                section.findtext("title", ""),
                section.findtext("directory", ""),
                section.findtext("parentcmid", ""),
                section.findtext("modname", ""),
            )
            for section in root.findall("information/contents/sections/section")
        ],
    )


def _activity_xml_fingerprint(path: str | Path) -> dict[str, Any]:
    digest: dict[str, Any] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            parts = member.name.split("/")
            if len(parts) == 3 and parts[0] == "activities" and parts[2].endswith(".xml"):
                if parts[2] in {"module.xml", "grades.xml", "grade_history.xml", "filters.xml", "roles.xml", "inforef.xml", "competencies.xml", "grading.xml"}:
                    continue
                data = archive.extractfile(member).read()  # type: ignore[union-attr]
                if parts[2] == "label.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("label/name", ""),
                        root.findtext("label/intro", ""),
                        root.findtext("label/introformat", ""),
                    )
                    continue
                if parts[2] == "book.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("book/name", ""),
                        root.findtext("book/intro", ""),
                        root.findtext("book/introformat", ""),
                        root.findtext("book/numbering", ""),
                        root.findtext("book/navstyle", ""),
                        root.findtext("book/customtitles", ""),
                        [
                            (
                                chapter.findtext("pagenum", ""),
                                chapter.findtext("subchapter", ""),
                                chapter.findtext("title", ""),
                                chapter.findtext("content", ""),
                                chapter.findtext("contentformat", ""),
                                chapter.findtext("hidden", ""),
                                chapter.findtext("importsrc", ""),
                            )
                            for chapter in root.findall("book/chapters/chapter")
                        ],
                    )
                    continue
                if parts[2] == "quiz.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("quiz/name", ""),
                        root.findtext("quiz/intro", ""),
                        root.findtext("quiz/introformat", ""),
                        root.findtext("quiz/sumgrades", ""),
                        root.findtext("quiz/grade", ""),
                        [
                            (
                                instance.findtext("slot", ""),
                                instance.findtext("page", ""),
                                instance.findtext("displaynumber", ""),
                                instance.findtext("requireprevious", ""),
                                instance.findtext("maxmark", ""),
                                instance.findtext("quizgradeitemid", ""),
                                instance.findtext("question_reference/usingcontextid", ""),
                                instance.findtext("question_reference/component", ""),
                                instance.findtext("question_reference/questionarea", ""),
                                instance.findtext("question_reference/questionbankentryid", ""),
                                instance.findtext("question_reference/version", ""),
                            )
                            for instance in root.findall("quiz/question_instances/question_instance")
                        ],
                        [
                            (
                                section.findtext("firstslot", ""),
                                section.findtext("heading", ""),
                                section.findtext("shufflequestions", ""),
                            )
                            for section in root.findall("quiz/sections/section")
                        ],
                    )
                    continue
                if parts[2] == "folder.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("folder/name", ""),
                        root.findtext("folder/intro", ""),
                        root.findtext("folder/introformat", ""),
                        root.findtext("folder/display", ""),
                        root.findtext("folder/showexpanded", ""),
                        root.findtext("folder/showdownloadfolder", ""),
                        root.findtext("folder/forcedownload", ""),
                    )
                    continue
                if parts[2] == "geogebra.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("geogebra/name", ""),
                        root.findtext("geogebra/intro", ""),
                        root.findtext("geogebra/introformat", ""),
                        root.findtext("geogebra/url", ""),
                        root.findtext("geogebra/attributes", ""),
                        root.findtext("geogebra/width", ""),
                        root.findtext("geogebra/height", ""),
                        root.findtext("geogebra/showsubmit", ""),
                        root.findtext("geogebra/grade", ""),
                        root.findtext("geogebra/autograde", ""),
                        root.findtext("geogebra/maxattempts", ""),
                        root.findtext("geogebra/grademethod", ""),
                    )
                    continue
                if parts[2] == "assign.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("assign/name", ""),
                        root.findtext("assign/intro", ""),
                        root.findtext("assign/introformat", ""),
                        root.findtext("assign/alwaysshowdescription", ""),
                        root.findtext("assign/submissiondrafts", ""),
                        root.findtext("assign/sendnotifications", ""),
                        root.findtext("assign/sendlatenotifications", ""),
                        root.findtext("assign/sendstudentnotifications", ""),
                        root.findtext("assign/duedate", ""),
                        root.findtext("assign/cutoffdate", ""),
                        root.findtext("assign/gradingduedate", ""),
                        root.findtext("assign/allowsubmissionsfromdate", ""),
                        root.findtext("assign/grade", ""),
                        root.findtext("assign/completionsubmit", ""),
                        root.findtext("assign/requiresubmissionstatement", ""),
                        root.findtext("assign/attemptreopenmethod", ""),
                        root.findtext("assign/maxattempts", ""),
                        [
                            (
                                config.findtext("plugin", ""),
                                config.findtext("subtype", ""),
                                config.findtext("name", ""),
                                config.findtext("value", ""),
                            )
                            for config in root.findall("assign/plugin_configs/plugin_config")
                        ],
                    )
                    continue
                if parts[2] == "forum.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("forum/type", ""),
                        root.findtext("forum/name", ""),
                        root.findtext("forum/intro", ""),
                        root.findtext("forum/introformat", ""),
                        root.findtext("forum/duedate", ""),
                        root.findtext("forum/cutoffdate", ""),
                        root.findtext("forum/assessed", ""),
                        root.findtext("forum/scale", ""),
                        root.findtext("forum/maxattachments", ""),
                        root.findtext("forum/forcesubscribe", ""),
                        root.findtext("forum/trackingtype", ""),
                        root.findtext("forum/completiondiscussions", ""),
                        root.findtext("forum/completionreplies", ""),
                        root.findtext("forum/completionposts", ""),
                    )
                    continue
                if parts[2] == "subsection.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("subsection/name", ""),
                    )
                    continue
                if parts[2] == "choice.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("choice/name", ""),
                        root.findtext("choice/intro", ""),
                        root.findtext("choice/introformat", ""),
                        root.findtext("choice/publish", ""),
                        root.findtext("choice/showresults", ""),
                        root.findtext("choice/display", ""),
                        root.findtext("choice/allowupdate", ""),
                        root.findtext("choice/allowmultiple", ""),
                        root.findtext("choice/showunanswered", ""),
                        root.findtext("choice/limitanswers", ""),
                        root.findtext("choice/timeopen", ""),
                        root.findtext("choice/timeclose", ""),
                        root.findtext("choice/completionsubmit", ""),
                        root.findtext("choice/showpreview", ""),
                        root.findtext("choice/includeinactive", ""),
                        root.findtext("choice/showavailable", ""),
                        tuple(
                            (
                                option.findtext("text", ""),
                                option.findtext("maxanswers", ""),
                            )
                            for option in root.findall("choice/options/option")
                        ),
                    )
                    continue
                if parts[2] == "questionnaire.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("questionnaire/name", ""),
                        root.findtext("questionnaire/intro", ""),
                        root.findtext("questionnaire/introformat", ""),
                        root.findtext("questionnaire/qtype", ""),
                        root.findtext("questionnaire/respondenttype", ""),
                        root.findtext("questionnaire/resp_eligible", ""),
                        root.findtext("questionnaire/resp_view", ""),
                        root.findtext("questionnaire/notifications", ""),
                        root.findtext("questionnaire/opendate", ""),
                        root.findtext("questionnaire/closedate", ""),
                        root.findtext("questionnaire/resume", ""),
                        root.findtext("questionnaire/navigate", ""),
                        root.findtext("questionnaire/grade", ""),
                        root.findtext("questionnaire/completionsubmit", ""),
                        root.findtext("questionnaire/autonum", ""),
                        root.findtext("questionnaire/removeafter", ""),
                        tuple(
                            (
                                survey.findtext("name", ""),
                                survey.findtext("realm", ""),
                                survey.findtext("status", ""),
                                survey.findtext("title", ""),
                                survey.findtext("info", ""),
                                survey.findtext("thanks_page", ""),
                                survey.findtext("thank_head", ""),
                                survey.findtext("thank_body", ""),
                                survey.findtext("feedbacksections", ""),
                                survey.findtext("feedbackscores", ""),
                                survey.findtext("chart_type", ""),
                            )
                            for survey in root.findall("questionnaire/surveys/survey")
                        ),
                        tuple(
                            (
                                question.get("id", ""),
                                _null_to_empty(question.findtext("name", "")),
                                question.findtext("surveyid", ""),
                                question.findtext("type_id", ""),
                                question.findtext("result_id", ""),
                                question.findtext("length", ""),
                                question.findtext("precise", ""),
                                question.findtext("position", ""),
                                question.findtext("content", ""),
                                question.findtext("required", ""),
                                question.findtext("deleted", ""),
                                question.findtext("extradata", ""),
                                tuple(
                                    (
                                        dependency.findtext("dependquestionid", ""),
                                        dependency.findtext("dependchoiceid", ""),
                                        dependency.findtext("dependlogic", ""),
                                        dependency.findtext("questionid", ""),
                                        dependency.findtext("surveyid", ""),
                                        dependency.findtext("dependandor", ""),
                                    )
                                    for dependency in question.findall("quest_dependencies/quest_dependency")
                                ),
                                tuple(
                                    (
                                        choice.findtext("content", ""),
                                        _null_to_empty(choice.findtext("value", "")),
                                    )
                                    for choice in question.findall("quest_choices/quest_choice")
                                ),
                            )
                            for question in root.findall("questionnaire/surveys/survey/questions/question")
                        ),
                    )
                    continue
                if parts[2] == "board.xml":
                    root = ET.fromstring(data)
                    digest[member.name] = (
                        root.findtext("board/name", ""),
                        root.findtext("board/intro", ""),
                        root.findtext("board/introformat", ""),
                        root.findtext("board/background_color", ""),
                        root.findtext("board/addrating", ""),
                        root.findtext("board/hideheaders", ""),
                        root.findtext("board/sortby", ""),
                        root.findtext("board/postby", ""),
                        root.findtext("board/userscanedit", ""),
                        root.findtext("board/singleusermode", ""),
                        root.findtext("board/completionnotes", ""),
                        root.findtext("board/embed", ""),
                        tuple(
                            (
                                column.findtext("name", ""),
                                column.findtext("sortorder", ""),
                                tuple(
                                    (
                                        note.findtext("content", ""),
                                        note.findtext("heading", ""),
                                        note.findtext("type", ""),
                                        note.findtext("sortorder", ""),
                                        note.findtext("deleted", ""),
                                    )
                                    for note in column.findall("notes/note")
                                ),
                            )
                            for column in root.findall("board/columns/column")
                        ),
                    )
                    continue
                digest[member.name] = hashlib.sha256(data).hexdigest()
    return dict(sorted(digest.items()))


def _null_to_empty(value: str | None) -> str:
    if value in {None, "$@NULL@$"}:
        return ""
    return value
