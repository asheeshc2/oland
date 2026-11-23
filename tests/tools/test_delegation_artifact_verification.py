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
    assert "escape.txt" in result["missing_files"]


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
