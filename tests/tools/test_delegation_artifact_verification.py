from tools.delegate_review import verify_expected_files


def test_expected_file_exists(tmp_path):
    (tmp_path / "calculator.py").write_text("print(1)")
    result = verify_expected_files(str(tmp_path), ["calculator.py"])
    assert result["files_valid"] is True
    assert result["checked_files"] == ["calculator.py"]


def test_missing_file_is_rejected(tmp_path):
    result = verify_expected_files(str(tmp_path), ["missing.py"])
    assert result["files_valid"] is False
    assert result["missing_files"] == ["missing.py"]


def test_path_traversal_is_rejected(tmp_path):
    result = verify_expected_files(str(tmp_path), ["../outside.py"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["../outside.py"]


def test_absolute_path_is_rejected(tmp_path):
    result = verify_expected_files(str(tmp_path), ["/etc/passwd"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["/etc/passwd"]


def test_directory_is_not_accepted_as_file(tmp_path):
    (tmp_path / "output").mkdir()
    result = verify_expected_files(str(tmp_path), ["output"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["output"]


def test_symlink_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside-review-test.txt"
    outside.write_text("outside")
    (tmp_path / "escape.txt").symlink_to(outside)

    result = verify_expected_files(str(tmp_path), ["escape.txt"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["escape.txt"]


def test_empty_expected_files_passes(tmp_path):
    result = verify_expected_files(str(tmp_path), [])
    assert result["files_valid"] is True



def test_invalid_workspace_fails_closed(tmp_path):
    result = verify_expected_files(str(tmp_path / "does-not-exist"), ["calculator.py"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["<invalid workspace>"]


def test_windows_absolute_path_is_rejected(tmp_path):
    result = verify_expected_files(str(tmp_path), ["C:\\Windows\\system.ini"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["C:\\Windows\\system.ini"]


def test_symlink_escape_is_classified_as_invalid_path(tmp_path):
    outside = tmp_path.parent / "outside-review-test-2.txt"
    outside.write_text("outside")
    (tmp_path / "escape.txt").symlink_to(outside)

    result = verify_expected_files(str(tmp_path), ["escape.txt"])
    assert result["files_valid"] is False
    assert result["invalid_paths"] == ["escape.txt"]

def test_child_terminal_verification_uses_child_task_workspace(monkeypatch):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    import tools.delegate_tool_routes
    import tools.terminal_tool
    from tools.delegate_review import verify_expected_files_in_child

    calls = []

    def fake_terminal(command, **kwargs):
        calls.append((command, kwargs))
        return json.dumps({
            "exit_code": 0,
            "output": json.dumps({
                "files_valid": True,
                "checked_files": ["calculator.py"],
                "missing_files": [],
                "invalid_paths": [],
            }),
        })

    monkeypatch.setattr(tools.delegate_tool_routes, "child_profile_scope", lambda child: nullcontext())
    monkeypatch.setattr(tools.terminal_tool, "terminal_tool", fake_terminal)

    result = verify_expected_files_in_child(
        task_id="child-123",
        workspace="/child/workspace",
        expected_files=["calculator.py"],
        child=SimpleNamespace(),
    )

    assert result["accepted"] is True
    assert result["verification_status"] == "passed"
    assert calls[0][1]["task_id"] == "child-123"
    assert calls[0][1]["workdir"] == "/child/workspace"


def test_child_terminal_verification_fails_closed_when_terminal_unavailable(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    import tools.delegate_tool_routes
    import tools.terminal_tool
    from tools.delegate_review import verify_expected_files_in_child

    monkeypatch.setattr(tools.delegate_tool_routes, "child_profile_scope", lambda child: nullcontext())
    monkeypatch.setattr(tools.terminal_tool, "get_session_cwd", lambda task_id: "/child/workspace")
    monkeypatch.setattr(
        tools.terminal_tool, "terminal_tool",
        lambda command, **kwargs: '{"exit_code": 1, "output": "command unavailable"}',
    )

    result = verify_expected_files_in_child(
        task_id="child-123",
        expected_files=["calculator.py"],
        child=SimpleNamespace(),
    )

    assert result["accepted"] is False
    assert result["verification_status"] == "unavailable"

