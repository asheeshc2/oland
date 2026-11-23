"""Tests for independent delegation review verdicts."""

from tools.delegate_review import evaluate_review_verdict


def test_explicit_pass_is_accepted():
    result = evaluate_review_verdict(
        "VERDICT: PASS\nAll required checks passed."
    )
    assert result["accepted"] is True
    assert result["review_status"] == "passed"


def test_explicit_fail_is_not_accepted():
    result = evaluate_review_verdict(
        "VERDICT: FAIL\nMissing required implementation."
    )
    assert result["accepted"] is False
    assert result["review_status"] == "failed"


def test_missing_verdict_fails_closed():
    result = evaluate_review_verdict(
        "The work looks good to me."
    )
    assert result["accepted"] is False
    assert result["review_status"] == "invalid"


def test_empty_review_fails_closed():
    result = evaluate_review_verdict("")
    assert result["accepted"] is False
    assert result["review_status"] == "invalid"


def test_unstructured_pass_word_is_not_accepted():
    result = evaluate_review_verdict(
        "PASS - maybe everything is fine."
    )
    assert result["accepted"] is False
    assert result["review_status"] == "invalid"
