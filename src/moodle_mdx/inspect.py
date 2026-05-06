from __future__ import annotations

import hashlib
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class MbzReport:
    course: dict[str, Any]
    sections: list[dict[str, Any]]
    activities: list[dict[str, Any]]
    activity_counts: dict[str, int]
    file_blobs: list[dict[str, Any]]
    paths: list[str]


def _read_xml(archive: tarfile.TarFile, name: str) -> ET.Element:
    member = archive.extractfile(name)
    if member is None:
        raise FileNotFoundError(name)
    return ET.fromstring(member.read())


def inspect_mbz(path: str | Path) -> MbzReport:
    mbz_path = Path(path)
    with tarfile.open(mbz_path, "r:gz") as archive:
        paths = archive.getnames()
        backup = _read_xml(archive, "moodle_backup.xml")
        info = backup.find("information")
        if info is None:
            raise ValueError("moodle_backup.xml has no information element")
        course_xml = _read_xml(archive, "course/course.xml")

        course = {
            "moodle_release": info.findtext("moodle_release", ""),
            "moodle_version": info.findtext("moodle_version", ""),
            "backup_release": info.findtext("backup_release", ""),
            "backup_version": info.findtext("backup_version", ""),
            "original_course_id": info.findtext("original_course_id", ""),
            "format": course_xml.findtext("format", ""),
            "fullname": course_xml.findtext("fullname", ""),
            "shortname": course_xml.findtext("shortname", ""),
        }

        sections: list[dict[str, Any]] = []
        for name in paths:
            if name.startswith("sections/section_") and name.endswith("/section.xml"):
                root = _read_xml(archive, name)
                sections.append(
                    {
                        "id": root.attrib.get("id", ""),
                        "index": int(root.findtext("number", "0")),
                        "title": _null_to_empty(root.findtext("name", "")),
                        "summary": root.findtext("summary", ""),
                        "sequence": root.findtext("sequence", ""),
                        "path": name,
                    }
                )
        sections.sort(key=lambda section: section["index"])

        activities: list[dict[str, Any]] = []
        for activity in backup.findall("information/contents/activities/activity"):
            moduleid = activity.findtext("moduleid", "")
            modulename = activity.findtext("modulename", "")
            activities.append(
                {
                    "moduleid": moduleid,
                    "sectionid": activity.findtext("sectionid", ""),
                    "type": modulename,
                    "title": activity.findtext("title", ""),
                    "directory": activity.findtext("directory", ""),
                    "module_xml": f"activities/{modulename}_{moduleid}/module.xml",
                    "activity_xml": f"activities/{modulename}_{moduleid}/{modulename}.xml",
                }
            )

        counts = dict(sorted(Counter(item["type"] for item in activities).items()))

        file_blobs: list[dict[str, Any]] = []
        for name in paths:
            parts = name.split("/")
            if len(parts) == 3 and parts[0] == "files" and len(parts[1]) == 2:
                data = archive.extractfile(name)
                if data is None:
                    continue
                blob = data.read()
                file_blobs.append(
                    {
                        "path": name,
                        "sha1": hashlib.sha1(blob).hexdigest(),
                        "size": len(blob),
                    }
                )
        file_blobs.sort(key=lambda item: item["path"])

    return MbzReport(course, sections, activities, counts, file_blobs, paths)


def _null_to_empty(value: str | None) -> str:
    if value in (None, "$@NULL@$"):
        return ""
    return value
