"""Tests for optional per-task delegation verification contracts."""

import pytest

from tools.delegate_tool_tasks import _normalize_task_list


def _normalize(tasks):
    return _normalize_task_list(
        goal=None,
        context=None,
        tasks=tasks,
        output_schema=None,
        top_role="leaf",
        max_children=2,
    )


def test_legacy_task_without_verification_remains_valid():
    tasks, error = _normalize([{"goal": "Implement a small Python utility"}])

    assert error is None
    assert tasks[0]["goal"] == "Implement a small Python utility"


def test_task_preserves_verification_contract():
    contract = {
        "expected_files": ["calculator.py"],
        "checks": ["Run the unit tests"],
    }
    tasks, error = _normalize([
        {
            "goal": "Implement a calculator",
            "verification": contract,
        }
    ])

    assert error is None
    assert tasks[0]["verification"] == contract


def test_invalid_verification_type_is_rejected():
    tasks, error = _normalize([
        {
            "goal": "Implement a calculator",
            "verification": "verify everything",
        }
    ])

    assert tasks is None
    assert "verification" in error.lower()


def test_delegate_schema_exposes_verification_contract():
    from tools.delegate_tool import DELEGATE_TASK_SCHEMA

    properties = DELEGATE_TASK_SCHEMA["parameters"]["properties"]["tasks"]["items"]["properties"]
    assert "verification" in properties
    assert "expected_files" in properties["verification"]["properties"]
    assert "checks" in properties["verification"]["properties"]


def test_verification_contract_is_optional_in_schema():
    from tools.delegate_tool import DELEGATE_TASK_SCHEMA

    required = DELEGATE_TASK_SCHEMA["parameters"]["properties"]["tasks"]["items"]["required"]
    assert "verification" not in required



def test_verification_rejects_empty_contract():
    tasks, error = _normalize([{
        "goal": "Implement a calculator",
        "verification": {},
    }])
    assert tasks is None
    assert "cannot be empty" in error


def test_verification_rejects_non_array_checks():
    tasks, error = _normalize([{
        "goal": "Implement a calculator",
        "verification": {"checks": "run tests"},
    }])
    assert tasks is None
    assert "verification.checks" in error


def test_verification_rejects_parent_traversal():
    tasks, error = _normalize([{
        "goal": "Implement a calculator",
        "verification": {"expected_files": ["../outside.py"]},
    }])
    assert tasks is None
    assert "unsafe expected file path" in error


def test_verification_rejects_windows_absolute_path():
    tasks, error = _normalize([{
        "goal": "Implement a calculator",
        "verification": {"expected_files": ["C:\\temp\\outside.py"]},
    }])
    assert tasks is None
    assert "unsafe expected file path" in error

def test_verification_contract_is_preserved_in_resume_spec():
    from types import SimpleNamespace

    from tools.delegate_tool_resumable import _spec

    contract = {"expected_files": ["calculator.py"], "checks": ["Review behavior"]}
    child = SimpleNamespace(
        _delegate_resume={"goal": "Implement calculator"},
        _delegate_verification=contract,
        session_id="child-session",
        model="test-model",
    )

    result = _spec(child)

    assert result["verification"] == contract

def test_verification_contract_is_preserved_in_in_memory_resume_spec():
    from types import SimpleNamespace

    from tools.delegate_tool_registry import _resume_spec

    contract = {"expected_files": ["calculator.py"]}
    child = SimpleNamespace(
        _delegate_resume={"goal": "Implement calculator", "route": object()},
        _delegate_verification=contract,
        session_id="child-session",
    )

    result = _resume_spec({"agent": child, "model": "test-model"})

    assert result["verification"] == contract

