"""Independent review verdict parsing and acceptance decisions."""

import re
from typing import Any


_VERDICT_PATTERN = re.compile(
    r"^\s*VERDICT\s*:\s*(PASS|FAIL)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def evaluate_review_verdict(review_text: Any) -> dict[str, Any]:
    """Accept only an explicit, unambiguous reviewer verdict.

    A missing, empty, or malformed verdict fails closed.
    """
    if not isinstance(review_text, str) or not review_text.strip():
        return {
            "accepted": False,
            "review_status": "invalid",
            "review_reason": "Reviewer returned an empty response.",
        }

    matches = _VERDICT_PATTERN.findall(review_text)

    if len(matches) != 1:
        return {
            "accepted": False,
            "review_status": "invalid",
            "review_reason": "Expected exactly one explicit VERDICT: PASS or VERDICT: FAIL.",
        }

    verdict = matches[0].upper()

    if verdict == "PASS":
        return {
            "accepted": True,
            "review_status": "passed",
            "review_reason": "Reviewer explicitly returned PASS.",
        }

    return {
        "accepted": False,
        "review_status": "failed",
        "review_reason": "Reviewer explicitly returned FAIL.",
    }


def verify_expected_files(workspace: str, expected_files: list[str]) -> dict[str, Any]:
    """Verify expected deliverables exist inside the workspace.

    Reject invalid workspaces, absolute paths, traversal, symlinks escaping
    the workspace, and non-regular files. Never reads or executes file contents.
    """
    from pathlib import Path, PurePosixPath, PureWindowsPath

    checked_files: list[str] = []
    missing_files: list[str] = []
    invalid_paths: list[str] = []

    try:
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(str(root))
    except (OSError, RuntimeError, TypeError, ValueError):
        return {
            "files_valid": False,
            "checked_files": [],
            "missing_files": [],
            "invalid_paths": ["<invalid workspace>"],
        }

    if not isinstance(expected_files, list):
        return {
            "files_valid": False,
            "checked_files": [],
            "missing_files": [],
            "invalid_paths": ["<expected_files must be a list>"],
        }

    for item in expected_files:
        if not isinstance(item, str) or not item.strip():
            invalid_paths.append(str(item))
            continue

        posix = PurePosixPath(item)
        windows = PureWindowsPath(item)
        if (posix.is_absolute() or windows.is_absolute() or windows.drive
                or ".." in posix.parts or ".." in windows.parts):
            invalid_paths.append(item)
            continue

        try:
            candidate = (root / Path(item)).resolve(strict=True)
            candidate.relative_to(root)
        except FileNotFoundError:
            missing_files.append(item)
            continue
        except (OSError, ValueError, RuntimeError):
            invalid_paths.append(item)
            continue

        if not candidate.is_file():
            invalid_paths.append(item)
            continue

        checked_files.append(item)

    return {
        "files_valid": not missing_files and not invalid_paths,
        "checked_files": checked_files,
        "missing_files": missing_files,
        "invalid_paths": invalid_paths,
    }
