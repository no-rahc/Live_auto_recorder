#!/usr/bin/env python3
"""Prepare and validate Live Auto Recorder release metadata."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PACKAGE_FILE = ROOT / "package.json"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"
APP_ENTRY_FILE = ROOT / "app_entry.py"
DOCKER_WORKFLOW_FILE = ROOT / ".github" / "workflows" / "docker-publish.yml"

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_VERSION_RE = re.compile(
    r"(?m)^##\s+(v\d+\.\d+\.\d+)(?:\s+-\s+\d{4}-\d{2}-\d{2})?\s*$"
)

RELEASE_FILES = (
    "VERSION",
    "package.json",
    "CHANGELOG.md",
)


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def read_version() -> tuple[int, int, int]:
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    match = VERSION_RE.fullmatch(raw)
    if not match:
        fail(f"VERSION must use vMAJOR.MINOR.PATCH: {raw!r}")
    return tuple(int(part) for part in match.groups())


def format_version(parts: tuple[int, int, int]) -> str:
    return f"v{parts[0]}.{parts[1]}.{parts[2]}"


def bump_version(parts: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = parts
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def update_package(version: str) -> None:
    payload = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    payload["version"] = version.removeprefix("v")
    PACKAGE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_changelog(version: str, summaries: list[str]) -> None:
    text = (
        CHANGELOG_FILE.read_text(encoding="utf-8")
        if CHANGELOG_FILE.exists()
        else "# Changelog\n"
    )
    header = "# Changelog\n"
    if not text.startswith(header):
        fail("CHANGELOG.md must start with '# Changelog'")

    body = text[len(header) :].lstrip("\n")
    entry = [f"## {version} - {date.today().isoformat()}", ""]
    entry.extend(f"- {summary.strip()}" for summary in summaries if summary.strip())
    entry_text = "\n".join(entry).rstrip() + "\n\n"
    CHANGELOG_FILE.write_text(header + "\n" + entry_text + body, encoding="utf-8")


def check_release_metadata() -> None:
    version = format_version(read_version())
    errors: list[str] = []

    package_version = json.loads(PACKAGE_FILE.read_text(encoding="utf-8")).get(
        "version"
    )
    expected_package_version = version.removeprefix("v")
    if package_version != expected_package_version:
        errors.append(
            f"package.json={package_version!r}, expected {expected_package_version!r}"
        )

    changelog_text = CHANGELOG_FILE.read_text(encoding="utf-8")
    changelog_match = CHANGELOG_VERSION_RE.search(changelog_text)
    if not changelog_match or changelog_match.group(1) != version:
        errors.append(f"CHANGELOG.md first release heading must be {version}")

    app_entry = APP_ENTRY_FILE.read_text(encoding="utf-8")
    if 'VERSION_FILE = ROOT_DIR / "VERSION"' not in app_entry:
        errors.append("app_entry.py must read the root VERSION file")

    docker_workflow = DOCKER_WORKFLOW_FILE.read_text(encoding="utf-8")
    if "< VERSION" not in docker_workflow:
        errors.append("docker-publish.yml must read the root VERSION file")

    if errors:
        fail("Release metadata is out of sync:\n- " + "\n- ".join(errors))

    print(f"Release metadata is consistent: {version}")


def commit_release(version: str) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()

    changed = {line[3:] for line in status if len(line) > 3}
    unrelated = sorted(changed - set(RELEASE_FILES))
    if unrelated:
        fail(
            "Refusing to create a release commit with unrelated changes:\n- "
            + "\n- ".join(unrelated)
        )

    subprocess.run(["git", "add", *RELEASE_FILES], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore(release): {version}"],
        cwd=ROOT,
        check=True,
    )


def command_bump(args: argparse.Namespace) -> None:
    current = read_version()
    next_version = format_version(bump_version(current, args.level))

    update_package(next_version)
    update_changelog(next_version, args.summary)
    VERSION_FILE.write_text(next_version + "\n", encoding="utf-8")

    check_release_metadata()
    print(f"Prepared {next_version}")
    print(f"Release commit: chore(release): {next_version}")

    if args.commit:
        commit_release(next_version)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("check", help="validate synchronized release metadata")

    bump_parser = commands.add_parser(
        "bump", help="bump VERSION, package.json, and CHANGELOG.md together"
    )
    bump_parser.add_argument(
        "level",
        choices=("patch", "minor", "major"),
        nargs="?",
        default="patch",
        help="version segment to increment; patch is the default",
    )
    bump_parser.add_argument(
        "--summary",
        action="append",
        required=True,
        help="CHANGELOG item; repeat this option for multiple items",
    )
    bump_parser.add_argument(
        "--commit",
        action="store_true",
        help="create an isolated chore(release): vX.Y.Z commit",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "check":
        check_release_metadata()
    else:
        command_bump(args)


if __name__ == "__main__":
    main()
