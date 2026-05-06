from __future__ import annotations

import gzip
import json
import tarfile
from pathlib import Path

from .inspect import inspect_mbz
from .parser import parse_mdx
from .render import render_manifest
from .standalone import render_standalone_mbz
from .validate import validate_mdx_file_or_raise
from .xml_render import ArchiveOverrides, render_template_xml_overrides


def build_mbz_from_mdx(
    mdx_path: str | Path,
    output_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> dict:
    source_path = Path(mdx_path)
    validate_mdx_file_or_raise(source_path)
    model = parse_mdx(source_path.read_text(encoding="utf-8"))
    manifest = render_manifest(model)
    build_mode = manifest.get("build", {}).get("mode", "template")
    if build_mode == "template":
        _validate_manifest_against_template(source_path, manifest)

    if build_mode == "standalone":
        render_standalone_mbz(manifest, output_path, source_path.parent)
        if manifest_path is not None:
            _write_manifest(manifest, Path(manifest_path))
        return manifest

    if manifest_path is not None:
        _write_manifest(manifest, Path(manifest_path))

    template = _template_path(source_path, manifest)
    overrides = render_template_xml_overrides(template, manifest, source_path.parent)
    _copy_template_as_deterministic_tar_gz(template, Path(output_path), overrides=overrides)
    return manifest


def _write_manifest(manifest: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _template_path(source_path: Path, manifest: dict) -> Path:
    template_value = manifest.get("backup", {}).get("template")
    if not template_value:
        raise ValueError("Frontmatter backup.template is required for MBZ rendering")
    template = Path(str(template_value))
    if not template.is_absolute():
        template = source_path.parent / template
    if not template.exists():
        raise FileNotFoundError(template)
    return template


def _validate_manifest_against_template(source_path: Path, manifest: dict) -> None:
    template = _template_path(source_path, manifest)
    report = inspect_mbz(template)
    section_count = len(manifest.get("sections", []))
    if section_count != len(report.sections):
        raise ValueError(f"MDX has {section_count} sections, template has {len(report.sections)}")
    manifest_items = [
        item
        for section in manifest.get("sections", [])
        for item in section.get("items", [])
    ]
    if len(manifest_items) != len(report.activities):
        raise ValueError(f"MDX has {len(manifest_items)} activities, template has {len(report.activities)}")
    manifest_types = [item["type"] for item in manifest_items]
    report_types = [item["type"] for item in report.activities]
    if manifest_types != report_types:
        raise ValueError("MDX activity type sequence does not match template")


def _copy_template_as_deterministic_tar_gz(
    template: Path,
    output_path: Path,
    *,
    overrides: ArchiveOverrides | dict[str, bytes] | None = None,
) -> None:
    if overrides is None:
        override_files: dict[str, bytes] = {}
        removed_paths: set[str] = set()
    elif isinstance(overrides, ArchiveOverrides):
        override_files = dict(overrides.files)
        removed_paths = set(overrides.removed_paths)
    else:
        override_files = dict(overrides)
        removed_paths = set()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(template, "r:gz") as source:
        members = source.getmembers()
        existing_names = {member.name for member in members}
        with output_path.open("wb") as raw_out:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as gz_out:
                with tarfile.open(fileobj=gz_out, mode="w") as target:
                    for member in members:
                        if member.name in removed_paths:
                            continue
                        info = tarfile.TarInfo(member.name)
                        info.type = member.type
                        info.mode = member.mode
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = 0
                        if member.isdir():
                            target.addfile(info)
                            continue
                        fileobj = source.extractfile(member)
                        if fileobj is None:
                            target.addfile(info)
                            continue
                        data = override_files.pop(member.name, None)
                        if data is None:
                            data = fileobj.read()
                        info.size = len(data)
                        target.addfile(info, _BytesReader(data))
                    _add_new_override_files(target, override_files, existing_names)


def _add_new_override_files(
    target: tarfile.TarFile,
    override_files: dict[str, bytes],
    existing_names: set[str],
) -> None:
    added_dirs: set[str] = set()
    for path in sorted(override_files):
        parent = str(Path(path).parent)
        if parent not in {"", "."} and parent not in existing_names and parent not in added_dirs:
            info = tarfile.TarInfo(parent)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            target.addfile(info)
            added_dirs.add(parent)
        data = override_files[path]
        info = tarfile.TarInfo(path)
        info.mode = 0o644
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        info.size = len(data)
        target.addfile(info, _BytesReader(data))


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
