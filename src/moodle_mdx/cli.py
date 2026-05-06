from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compare import compare_mbz_semantics
from .extract import extract_mdx_from_mbz
from .inspect import inspect_mbz
from .mbz import build_mbz_from_mdx
from .validate import validate_mdx_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mdx2moodle")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = subcommands.add_parser("inspect-mbz")
    inspect_cmd.add_argument("mbz")

    extract_cmd = subcommands.add_parser("extract-mdx")
    extract_cmd.add_argument("mbz")
    extract_cmd.add_argument("output")

    build_cmd = subcommands.add_parser("build")
    build_cmd.add_argument("mdx")
    build_cmd.add_argument("output")
    build_cmd.add_argument("--manifest", default=None)

    validate_cmd = subcommands.add_parser("validate")
    validate_cmd.add_argument("mdx")

    compare_cmd = subcommands.add_parser("compare")
    compare_cmd.add_argument("expected")
    compare_cmd.add_argument("actual")

    args = parser.parse_args(argv)
    if args.command == "inspect-mbz":
        report = inspect_mbz(Path(args.mbz))
        print(json.dumps(_report_to_json(report), ensure_ascii=False, indent=2))
        return 0
    if args.command == "extract-mdx":
        extract_mdx_from_mbz(Path(args.mbz), Path(args.output))
        return 0
    if args.command == "build":
        build_mbz_from_mdx(Path(args.mdx), Path(args.output), manifest_path=args.manifest)
        return 0
    if args.command == "validate":
        issues = validate_mdx_file(Path(args.mdx))
        if issues:
            for issue in issues:
                print(issue)
            return 1
        print("MDX validation passed")
        return 0
    if args.command == "compare":
        result = compare_mbz_semantics(Path(args.expected), Path(args.actual))
        print(result.describe())
        return 0 if result.matches else 1
    raise AssertionError(args.command)


def _report_to_json(report) -> dict:
    return {
        "course": report.course,
        "sections": report.sections,
        "activities": report.activities,
        "activity_counts": report.activity_counts,
        "file_blobs": report.file_blobs,
        "path_count": len(report.paths),
    }


if __name__ == "__main__":
    raise SystemExit(main())
