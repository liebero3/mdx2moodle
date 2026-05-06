from __future__ import annotations

import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .inspect import inspect_mbz


def extract_mdx_from_mbz(mbz_path: str | Path, output_path: str | Path) -> Path:
    source = Path(mbz_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = inspect_mbz(source)
    course_settings, format_options = _course_frontmatter_details(source)
    sections_by_id = {section["id"]: section for section in report.sections}
    activities_by_section: dict[str, list[dict]] = {}
    for activity in report.activities:
        activities_by_section.setdefault(activity["sectionid"], []).append(activity)

    lines: list[str] = [
        "---",
        "course:",
        f'  title: "{_quote(report.course["fullname"])}"',
        f'  shortname: "{_quote(report.course["shortname"])}"',
        f'  format: "{_quote(report.course["format"])}"',
    ]
    lines.extend(
        f"  {key}: {_yaml_scalar(value)}"
        for key, value in course_settings.items()
    )
    if format_options:
        lines.append("tiles:")
        lines.extend(
            f"  {name}: {_yaml_scalar(value)}"
            for name, value in format_options
        )
    lines.extend(
        [
        "backup:",
        f'  template: "{_quote(source.name)}"',
        f'  moodle_release: "{_quote(report.course["moodle_release"])}"',
        "---",
        "",
        ]
    )

    with tarfile.open(source, "r:gz") as archive:
        question_bank_entries = _question_bank_entries_by_id(archive)
        file_nodes = _file_nodes_by_component_and_filename(archive)
        for section in report.sections:
            section_id = section["id"]
            title = section["title"] or "Allgemeines"
            lines.append(
                f'# {_quote(title)} {{id="section_{section_id}" index={section["index"]} sectionid={section_id} moodle_title="{_quote(section["title"])}"}}'
            )
            if section["summary"]:
                lines.append(f'summary: {_quote(section["summary"])}')
            lines.append("")
            for activity in activities_by_section.get(section_id, []):
                lines.extend(
                    _activity_to_directive(
                        archive,
                        activity,
                        question_bank_entries,
                        file_nodes,
                        destination.parent,
                    )
                )
                lines.append("")

    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return destination


def _activity_to_directive(
    archive: tarfile.TarFile,
    activity: dict,
    question_bank_entries: dict[str, ET.Element],
    file_nodes: dict[tuple[str, str], ET.Element],
    output_dir: Path,
) -> list[str]:
    activity_type = activity["type"]
    moduleid = activity["moduleid"]
    directory = activity["directory"]
    attrs = (
        f'id="{activity_type}_{moduleid}" moduleid={moduleid} sectionid={activity["sectionid"]} '
        f'title="{_quote(activity["title"])}" source="{directory}/{activity_type}.xml" '
        f'module="{directory}/module.xml"'
    )
    if activity_type == "book":
        lines = [f"::::book{{{attrs}}}"]
        for page in _book_pages(archive, f"{directory}/book.xml"):
            lines.append(
                f':::page{{title="{_quote(page["title"])}" subchapter={page["subchapter"]}}}'
            )
            if page["content"]:
                lines.append(page["content"])
            lines.append(":::")
        lines.append("::::")
        return lines
    if activity_type == "quiz":
        lines = [f"::::quiz{{{attrs} questions=\"questions.xml\"}}"]
        lines.extend(_quiz_questions(archive, activity, question_bank_entries))
        lines.append("::::")
        return lines
    if activity_type == "folder":
        return _folder_directive(archive, activity, attrs, output_dir)
    if activity_type == "geogebra":
        return _geogebra_directive(archive, activity, attrs, file_nodes, output_dir)
    if activity_type == "assign":
        return _assign_directive(archive, activity, attrs)
    if activity_type == "forum":
        return [f":::forum{{{attrs}}}", _forum_intro(archive, f"{directory}/forum.xml"), ":::"]
    if activity_type == "label":
        return [f":::label{{{attrs}}}", _label_intro(archive, f"{directory}/label.xml"), ":::"]
    return [f":::{activity_type}{{{attrs}}}", "", ":::"]


def _course_frontmatter_details(mbz_path: Path) -> tuple[dict[str, object], list[tuple[str, object]]]:
    with tarfile.open(mbz_path, "r:gz") as archive:
        root = _read_xml(archive, "course/course.xml")
    settings: dict[str, object] = {}
    for key in ("startdate", "enddate"):
        value = root.findtext(key, "")
        if value != "":
            settings[key] = int(value)
    for key in ("visible", "enablecompletion"):
        value = root.findtext(key, "")
        if value != "":
            settings[key] = value != "0"
    format_options: list[tuple[str, object]] = []
    for option in root.findall("courseformatoptions/courseformatoption"):
        name = option.findtext("name", "")
        value = option.findtext("value", "")
        if name:
            format_options.append((name, _yaml_value(value)))
    return settings, format_options


def _assign_directive(archive: tarfile.TarFile, activity: dict, attrs: str) -> list[str]:
    root = _read_xml(archive, f'{activity["directory"]}/assign.xml')
    assign = root.find("assign")
    if assign is None:
        return [f":::assign{{{attrs}}}", "", ":::"]
    extra_attrs = [
        f"grade={assign.findtext('grade', '100')}",
        f"gradingduedate={assign.findtext('gradingduedate', '0')}",
        f"maxattempts={assign.findtext('maxattempts', '1')}",
        f'attemptreopenmethod="{_quote(assign.findtext("attemptreopenmethod", "none"))}"',
        f"completionsubmit={_bool_attr(assign.findtext('completionsubmit', '0') != '0')}",
        f"submission_onlinetext={_bool_attr(_assign_plugin_enabled(assign, 'onlinetext', 'assignsubmission'))}",
        f"submission_file={_bool_attr(_assign_plugin_enabled(assign, 'file', 'assignsubmission'))}",
        f"submission_comments={_bool_attr(_assign_plugin_enabled(assign, 'comments', 'assignsubmission'))}",
        f"feedback_comments={_bool_attr(_assign_plugin_enabled(assign, 'comments', 'assignfeedback'))}",
        f"feedback_editpdf={_bool_attr(_assign_plugin_enabled(assign, 'editpdf', 'assignfeedback'))}",
    ]
    return [
        f":::assign{{{attrs} {' '.join(extra_attrs)}}}",
        assign.findtext("intro", ""),
        ":::",
    ]


def _folder_directive(
    archive: tarfile.TarFile,
    activity: dict,
    attrs: str,
    output_dir: Path,
) -> list[str]:
    asset_paths = []
    for file_node in _folder_file_nodes(archive):
        asset_paths.append(_export_asset(archive, file_node, output_dir / "assets" / "folder"))
    lines = [f":::folder{{{attrs}}}", _folder_intro(archive, f'{activity["directory"]}/folder.xml')]
    if asset_paths:
        lines.append("")
        lines.extend(f"- {path}" for path in asset_paths)
    lines.append(":::")
    return lines


def _geogebra_directive(
    archive: tarfile.TarFile,
    activity: dict,
    attrs: str,
    file_nodes: dict[tuple[str, str], ET.Element],
    output_dir: Path,
) -> list[str]:
    root = _read_xml(archive, f'{activity["directory"]}/geogebra.xml')
    filename = root.findtext("geogebra/url", "")
    file_node = file_nodes.get(("mod_geogebra", filename))
    file_attr = ""
    if file_node is not None:
        asset_path = _export_asset(archive, file_node, output_dir / "assets" / "geogebra")
        file_attr = f' file="{_quote(asset_path)}"'
    width = root.findtext("geogebra/width", "")
    height = root.findtext("geogebra/height", "")
    size_attrs = f" width={width} height={height}" if width and height else ""
    return [
        f":::geogebra{{{attrs}{file_attr}{size_attrs}}}",
        root.findtext("geogebra/intro", ""),
        ":::",
    ]


def _question_bank_entries_by_id(archive: tarfile.TarFile) -> dict[str, ET.Element]:
    member = archive.extractfile("questions.xml")
    if member is None:
        return {}
    root = ET.fromstring(member.read())
    return {
        str(entry.get("id")): entry
        for entry in root.findall(".//question_bank_entry")
        if entry.get("id")
    }


def _file_nodes_by_component_and_filename(archive: tarfile.TarFile) -> dict[tuple[str, str], ET.Element]:
    member = archive.extractfile("files.xml")
    if member is None:
        return {}
    root = ET.fromstring(member.read())
    return {
        (file_node.findtext("component", ""), file_node.findtext("filename", "")): file_node
        for file_node in root.findall("file")
        if file_node.findtext("filename", "") not in {"", "."}
    }


def _quiz_questions(
    archive: tarfile.TarFile,
    activity: dict,
    question_bank_entries: dict[str, ET.Element],
) -> list[str]:
    member = archive.extractfile(f'{activity["directory"]}/quiz.xml')
    if member is None:
        return []
    root = ET.fromstring(member.read())
    lines: list[str] = []
    for question_instance in root.findall("quiz/question_instances/question_instance"):
        reference = question_instance.find("question_reference")
        if reference is None:
            continue
        bank_entry_id = reference.findtext("questionbankentryid", "")
        bank_entry = question_bank_entries.get(bank_entry_id)
        if bank_entry is None:
            continue
        question = bank_entry.find("question_version/question_versions/questions/question")
        if question is None:
            continue
        qtype = question.findtext("qtype", "")
        if qtype != "multichoice":
            raise ValueError(f"Sprint 3 supports only multichoice questions, got {qtype!r}")
        slot = int(question_instance.findtext("slot", "0") or "0")
        page = int(question_instance.findtext("page", str(slot)) or str(slot))
        multichoice = question.find("plugin_qtype_multichoice_question/multichoice")
        attrs = (
            f'id="{activity["type"]}_{activity["moduleid"]}_q{slot:02d}" '
            f'type="multichoice" name="{_quote(question.findtext("name", ""))}" '
            f"slot={slot} page={page} "
            f'defaultmark="{_quote(question.findtext("defaultmark", "1.0000000"))}" '
            f'penalty="{_quote(question.findtext("penalty", "0.3333333"))}" '
            f'maxmark="{_quote(question_instance.findtext("maxmark", "1.0000000"))}" '
            f"single={_bool_attr(_node_text(multichoice, 'single', '1') != '0')} "
            f"shuffleanswers={_bool_attr(_node_text(multichoice, 'shuffleanswers', '1') != '0')} "
            f'answernumbering="{_quote(_node_text(multichoice, "answernumbering", "none"))}"'
        )
        lines.append(f":::question{{{attrs}}}")
        question_text = question.findtext("questiontext", "")
        if question_text:
            lines.append(question_text)
        lines.append("")
        for answer in question.findall("plugin_qtype_multichoice_question/answers/answer"):
            marker = "x" if answer.findtext("fraction", "0.0000000") == "1.0000000" else " "
            lines.append(f"- [{marker}] {answer.findtext('answertext', '')}")
        lines.append(":::")
    return lines


def _book_pages(archive: tarfile.TarFile, path: str) -> list[dict[str, str]]:
    member = archive.extractfile(path)
    if member is None:
        return []
    root = ET.fromstring(member.read())
    return [
        {
            "title": chapter.findtext("title", ""),
            "content": chapter.findtext("content", ""),
            "subchapter": chapter.findtext("subchapter", "0") or "0",
        }
        for chapter in root.findall(".//chapter")
    ]


def _folder_file_nodes(archive: tarfile.TarFile) -> list[ET.Element]:
    member = archive.extractfile("files.xml")
    if member is None:
        return []
    root = ET.fromstring(member.read())
    file_nodes = []
    for file_node in root.findall("file"):
        if file_node.findtext("component") == "mod_folder":
            filename = file_node.findtext("filename", "")
            if filename and filename != ".":
                file_nodes.append(file_node)
    return file_nodes


def _folder_intro(archive: tarfile.TarFile, path: str) -> str:
    root = _read_xml(archive, path)
    return root.findtext("folder/intro", "")


def _forum_intro(archive: tarfile.TarFile, path: str) -> str:
    root = _read_xml(archive, path)
    return root.findtext("forum/intro", "")


def _label_intro(archive: tarfile.TarFile, path: str) -> str:
    member = archive.extractfile(path)
    if member is None:
        return ""
    root = ET.fromstring(member.read())
    return root.findtext("label/intro", "")


def _assign_plugin_enabled(assign: ET.Element, plugin: str, subtype: str) -> bool:
    for config in assign.findall("plugin_configs/plugin_config"):
        if (
            config.findtext("plugin", "") == plugin
            and config.findtext("subtype", "") == subtype
            and config.findtext("name", "") == "enabled"
        ):
            return config.findtext("value", "0") != "0"
    return False


def _export_asset(archive: tarfile.TarFile, file_node: ET.Element, output_dir: Path) -> str:
    contenthash = file_node.findtext("contenthash", "")
    filename = file_node.findtext("filename", "")
    if not contenthash or not filename:
        raise ValueError("Cannot export Moodle file without contenthash and filename")
    member = archive.extractfile(f"files/{contenthash[:2]}/{contenthash}")
    if member is None:
        raise FileNotFoundError(f"files/{contenthash[:2]}/{contenthash}")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / filename
    destination.write_bytes(member.read())
    return f"assets/{output_dir.name}/{filename}"


def _read_xml(archive: tarfile.TarFile, path: str) -> ET.Element:
    member = archive.extractfile(path)
    if member is None:
        raise FileNotFoundError(path)
    return ET.fromstring(member.read())


def _node_text(node: ET.Element | None, path: str, default: str) -> str:
    if node is None:
        return default
    return node.findtext(path, default) or default


def _bool_attr(value: bool) -> str:
    return "true" if value else "false"


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return f'"{_quote(value)}"'


def _yaml_value(value: str) -> object:
    if value.isdigit():
        return int(value)
    return value


def _quote(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
