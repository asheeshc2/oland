"""Unread instruction results must not be collateral to a bulky sibling result."""
import copy
import json
from unittest.mock import patch

import pytest

from agent.context_compressor import ContextCompressor, TAIL_MAX_CONTEXT_FRACTION, _estimate_msg_budget_tokens
from agent.model_metadata import estimate_messages_tokens_rough
from agent.tool_guardrails import ToolCallGuardrailConfig, ToolCallGuardrailController


def compressor():
    with patch("agent.context_compressor.get_model_context_length", return_value=32000):
        return ContextCompressor(model="test/model", config_context_length=32000,
                                 quiet_mode=True, protect_first_n=1, protect_last_n=8)


def call(cid, name, args):
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def transcript(name="skill_view", args=None, reverse=False, body_size=9000):
    args = args or {"name": "systematic-debugging"}
    calls = [call("skill", name, args), call("dump", "read_file", {"path": "large.log"})]
    results = [
        {"role": "tool", "tool_call_id": "skill", "content": "Required instructions\n" + "x" * body_size},
        {"role": "tool", "tool_call_id": "dump", "content": "Large log\n" + "y" * 180000},
    ]
    return [{"role": "system", "content": "system"},
            {"role": "user", "content": "Use the instructions and inspect the log."},
            {"role": "assistant", "content": None, "tool_calls": calls},
            *(reversed(results) if reverse else results)]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("name,args", [
    ("skill_view", {"name": "systematic-debugging"}),
    ("skill_view", {"name": "systematic-debugging", "file_path": "references/details.md"}),
    ("multi_tool_use.parallel", {"tool_uses": [{"recipient_name": "functions.skill_view",
                                              "parameters": {"name": "systematic-debugging"}}]}),
])
def test_fitting_unread_instructions_survive_oversized_sibling(name, args, reverse):
    c = compressor()
    messages = transcript(name, args, reverse)
    original = copy.deepcopy(messages)
    expected = next(m["content"] for m in messages if m.get("tool_call_id") == "skill")
    # A small skill fits the hard share; its batch does not. Force tail pressure.
    assert not c._spared_pending_tool_round(messages)
    out, count = c._prune_old_tool_results(messages, protect_tail_count=8, protect_tail_tokens=500)
    by_id = {m.get("tool_call_id"): m.get("content") for m in out}
    assert by_id["skill"] == expected
    assert len(by_id["dump"]) < 1000
    assert count >= 1
    assert messages == original
    assert out[2]["tool_calls"] == original[2]["tool_calls"]


def test_admitted_rows_and_arguments_stay_within_hard_share():
    c = compressor()
    messages = transcript()
    spared = c._spared_pending_tool_rows(messages)
    cost = _estimate_msg_budget_tokens(messages[2]) + sum(_estimate_msg_budget_tokens(messages[i]) for i in spared)
    assert spared
    assert cost <= int(c._effective_input_window(c.context_length, c.max_tokens) * TAIL_MAX_CONTEXT_FRACTION)
    messages[2]["tool_calls"][0]["function"]["arguments"] = json.dumps({"name": "x" * 180000})
    assert not c._spared_pending_tool_rows(messages)


def test_full_compression_preserves_fitting_unread_skill():
    c = compressor()
    c._generate_summary = lambda *a, **k: "Earlier investigation."
    messages = transcript()
    expected = messages[3]["content"]
    messages[2:2] = [
        {"role": role, "content": "Earlier work " * 100}
        for _ in range(8) for role in ("assistant", "user")
    ]
    out = c.compress(messages, current_tokens=estimate_messages_tokens_rough(messages), force=True)
    assert next(m["content"] for m in out if m.get("tool_call_id") == "skill") == expected
    assert estimate_messages_tokens_rough(out) < estimate_messages_tokens_rough(messages)


@pytest.mark.parametrize("legacy_policy", [True, False])
def test_reload_policy_reaches_guard_only_with_legacy_batch_admission(legacy_policy):
    c = compressor()
    if legacy_policy:
        # Reproduce old all-or-nothing admission without changing guardrails.
        c._spared_pending_tool_rows = lambda messages: set(c._spared_pending_tool_round(messages))
    guard = ToolCallGuardrailController(ToolCallGuardrailConfig(hard_stop_enabled=True))
    args = {"name": "systematic-debugging"}
    attempts = 0
    for _ in range(6):
        decision = guard.before_call("skill_view", args)
        if decision.action == "block":
            assert legacy_policy
            assert decision.code == "idempotent_no_progress_block"
            assert attempts == 5
            return
        messages = transcript()
        body = messages[3]["content"]
        guard.after_call("skill_view", args, body, failed=False)
        attempts += 1
        out, _ = c._prune_old_tool_results(messages, protect_tail_count=8, protect_tail_tokens=500)
        content = next(m["content"] for m in out if m.get("tool_call_id") == "skill")
        if content == body:
            assert not legacy_policy
            assert attempts == 1
            return
        assert "SKILL_PRUNED" in content
    pytest.fail("Neither consumed skill instructions nor reached unchanged guard")


def test_oversized_skill_itself_is_not_pinned():
    c = compressor()
    messages = transcript(body_size=180000)
    out, _ = c._prune_old_tool_results(messages, protect_tail_count=8, protect_tail_tokens=500)
    assert len(next(m["content"] for m in out if m.get("tool_call_id") == "skill")) < 1000


def test_grace_ends_after_assistant_has_consumed_result():
    c = compressor()
    messages = transcript() + [{"role": "assistant", "content": "I have read the instructions."}]
    out, _ = c._prune_old_tool_results(messages, protect_tail_count=8, protect_tail_tokens=500)
    assert len(next(m["content"] for m in out if m.get("tool_call_id") == "skill")) < 1000
