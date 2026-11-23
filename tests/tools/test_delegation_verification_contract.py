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
