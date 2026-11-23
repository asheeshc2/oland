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

def verify_expected_files_in_child(*, task_id: str, expected_files: list[str], child: Any) -> dict[str, Any]:
    """Verify expected files in the child's actual terminal environment.

    This read-only check uses the child's task id and profile scope so remote/container
    backends are checked where the child worked, not on the parent's host filesystem.
    """
    import base64
    import json
    import shlex

    if not isinstance(expected_files, list):
        return {
            "files_valid": False, "checked_files": [], "missing_files": [],
            "invalid_paths": ["<expected_files must be a list>"], "accepted": False,
            "verification_status": "failed",
        }
    if not expected_files:
        return {
            "files_valid": True, "checked_files": [], "missing_files": [], "invalid_paths": [],
            "accepted": False, "verification_status": "not_requested",
        }
    if not isinstance(task_id, str) or not task_id.strip():
        return {
            "files_valid": False, "checked_files": [], "missing_files": [],
            "invalid_paths": ["<invalid child task id>"], "accepted": False,
            "verification_status": "unavailable",
        }

    try:
        from tools.delegate_tool_routes import child_profile_scope
        from tools.terminal_tool import get_session_cwd, terminal_tool

        payload = base64.b64encode(json.dumps({"expected_files": expected_files}).encode("utf-8")).decode("ascii")
        body = (
            "for item in items:\n"
            " if not isinstance(item,str) or not item.strip(): invalid.append(str(item)); continue\n"
            " p=PurePosixPath(item); w=PureWindowsPath(item)\n"
            " if p.is_absolute() or w.is_absolute() or w.drive or '..' in p.parts or '..' in w.parts: invalid.append(item); continue\n"
            " try:\n"
            "  candidate=(root / item).resolve(strict=True); candidate.relative_to(root)\n"
            " except FileNotFoundError: missing.append(item); continue\n"
            " except (OSError,ValueError,RuntimeError): invalid.append(item); continue\n"
            " if not candidate.is_file(): invalid.append(item); continue\n"
            " checked.append(item)"
        )
        script = (
            "import base64,json,pathlib; from pathlib import PurePosixPath,PureWindowsPath; "
            "items=json.loads(base64.b64decode(" + json.dumps(payload) + ")).get('expected_files'); "
            "root=pathlib.Path.cwd().resolve(strict=True); checked=[]; missing=[]; invalid=[]; "
            "exec(" + json.dumps(body) + "); "
            "print(json.dumps({'files_valid':not missing and not invalid,'checked_files':checked,"
            "'missing_files':missing,'invalid_paths':invalid}))"
        )
        with child_profile_scope(child):
            workspace = get_session_cwd(task_id)
            if not isinstance(workspace, str) or not workspace.strip():
                raise RuntimeError("Child workspace is unavailable.")
            command = "python3 -c " + shlex.quote(script)
            raw = terminal_tool(command, task_id=task_id, workdir=workspace, timeout=30)
            envelope = json.loads(raw) if isinstance(raw, str) else {}
            if not isinstance(envelope, dict) or envelope.get("exit_code") != 0:
                command = "python -c " + shlex.quote(script)
                raw = terminal_tool(command, task_id=task_id, workdir=workspace, timeout=30)
                envelope = json.loads(raw) if isinstance(raw, str) else {}
            if not isinstance(envelope, dict) or envelope.get("exit_code") != 0:
                raise RuntimeError("Child terminal verification command failed.")
            result = json.loads(str(envelope.get("output") or "").strip())
            if not isinstance(result, dict):
                raise RuntimeError("Child terminal returned an invalid verification response.")
            result["accepted"] = result.get("files_valid") is True
            result["verification_status"] = "passed" if result["accepted"] else "failed"
            return result
    except Exception as exc:
        return {
            "files_valid": False, "checked_files": [], "missing_files": [],
            "invalid_paths": ["<verification unavailable>"], "accepted": False,
            "verification_status": "unavailable", "verification_error": str(exc),
        }

