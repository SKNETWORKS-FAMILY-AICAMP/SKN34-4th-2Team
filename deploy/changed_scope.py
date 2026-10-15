"""Conservative documentation-only gate for PR and push workflows."""

import json
import os
from pathlib import PurePosixPath
import re
import subprocess


def is_documentation(path):
    file = PurePosixPath(path)
    if file.name.lower() == "readme.md":
        return True
    if path.startswith("assets/readme_image/"):
        return file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    if path.startswith("docs/"):
        return file.suffix.lower() in {".md", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".xlsx"}
    # Markdown elsewhere can be an AI prompt or runtime input. Do not skip it.
    return False


def requires_verification(event_name, event, diff=None):
    if event_name == "workflow_dispatch":
        return True
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
        separator = "..."
    elif event_name == "push":
        base, head = event["before"], event["after"]
        separator = ".."
        if base == "0" * 40:
            return True
    else:
        return True
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base, head)):
        raise ValueError("Invalid event commit SHA")
    if diff is None:
        diff = lambda comparison: subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z", comparison, "--"]
        ).decode("utf-8")
    # --no-renames checks both the old and new path: code -> docs is still code removal.
    files = [path for path in diff(base + separator + head).split("\0") if path]
    return any(not is_documentation(path) for path in files)


if __name__ == "__main__":
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as stream:
        event = json.load(stream)
    required = requires_verification(os.environ["GITHUB_EVENT_NAME"], event)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"required={str(required).lower()}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write("Code/configuration change or manual run: full verification.\n" if required
                     else "Documentation-only change: application build and deployment skipped.\n")
