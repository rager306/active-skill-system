"""Mock tests for MiniMaxProvider + SimpleCalcTool AST edge-cases (M010 S03).

Coverage boost for the main adapter gap (_provider.py was 40%).
NO real LLM calls — all paths covered with mocks and pure-function tests.
"""

from __future__ import annotations

import pytest

from active_skill_system.adapters.llm.minimax._thinking import (
    ThinkingTurnCache,
    _block_to_dict,
)
from active_skill_system.adapters.simple_calc_tool import SimpleCalcTool
from active_skill_system.application.ports.llm import LLMMessage, LLMToolCall
from active_skill_system.application.ports.tool import ToolResult


# ── _to_activegraph_messages conversion ──────────────────────────────────


def test_to_activegraph_messages_basic() -> None:
    """Local LLMMessage → activegraph LLMMessage: role+content preserved."""
    from active_skill_system.adapters.llm.minimax._provider import MiniMaxProvider

    # Create provider without real client.
    p = MiniMaxProvider.__new__(MiniMaxProvider)
    messages = [LLMMessage(role="user", content="hello")]
    ag = MiniMaxProvider._to_activegraph_messages(messages)
    assert len(ag) == 1
    assert ag[0].role == "user"
    assert ag[0].content == "hello"


def test_to_activegraph_messages_with_tool_calls() -> None:
    from active_skill_system.adapters.llm.minimax._provider import MiniMaxProvider

    p = MiniMaxProvider.__new__(MiniMaxProvider)
    messages = [
        LLMMessage(
            role="assistant",
            content="calling tool",
            tool_calls=(LLMToolCall(id="t1", name="search", args={"q": "x"}),),
        )
    ]
    ag = MiniMaxProvider._to_activegraph_messages(messages)
    assert ag[0].tool_calls is not None
    assert ag[0].tool_calls[0].id == "t1"
    assert ag[0].tool_calls[0].name == "search"


def test_to_activegraph_messages_tool_result_role() -> None:
    from active_skill_system.adapters.llm.minimax._provider import MiniMaxProvider

    messages = [
        LLMMessage(role="tool", content="result", tool_call_id="t1", tool_name="search")
    ]
    ag = MiniMaxProvider._to_activegraph_messages(messages)
    assert ag[0].role == "tool"
    assert ag[0].tool_use_id == "t1"


# ── thinking cache round-trip ────────────────────────────────────────────


def test_thinking_cache_remember_and_restore_roundtrip() -> None:
    cache = ThinkingTurnCache()
    blocks = [
        {"type": "thinking", "thinking": "why", "signature": "s1"},
        {"type": "text", "text": "answer"},
        {"type": "tool_use", "id": "toolu_1", "name": "g", "input": {}},
    ]
    cache.remember(["toolu_1"], blocks)
    wire = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "rebuilt"},
                {"type": "tool_use", "id": "toolu_1", "name": "g", "input": {}},
            ],
        }
    ]
    restored = cache.restore(wire)
    assert restored[0]["content"][0]["type"] == "thinking"


def test_thinking_cache_eviction() -> None:
    cache = ThinkingTurnCache(limit=2)
    cache.remember(["a"], [{"type": "text", "text": "1"}])
    cache.remember(["b"], [{"type": "text", "text": "2"}])
    cache.remember(["c"], [{"type": "text", "text": "3"}])
    assert "a" not in cache.blocks
    assert "c" in cache.blocks


# ── _block_to_dict edge-cases ─────────────────────────────────────────────


def test_block_to_dict_text() -> None:
    class _B:
        type = "text"
        text = "hello"

    assert _block_to_dict(_B()) == {"type": "text", "text": "hello"}


def test_block_to_dict_tool_use_with_str_input() -> None:
    class _B:
        type = "tool_use"
        id = "t1"
        name = "search"
        input = '{"q": "x"}'  # string input (some SDKs send this)

    result = _block_to_dict(_B())
    assert result["input"] == {"q": "x"}


def test_block_to_dict_tool_use_with_invalid_str_input() -> None:
    class _B:
        type = "tool_use"
        id = "t1"
        name = "search"
        input = "not json"

    result = _block_to_dict(_B())
    assert result["input"] == {"_raw": "not json"}


def test_block_to_dict_unknown_type_returns_none() -> None:
    class _B:
        type = "unknown"

    assert _block_to_dict(_B()) is None


# ── SimpleCalcTool AST edge-cases ────────────────────────────────────────


def test_calc_negative_number() -> None:
    assert SimpleCalcTool().invoke({"expression": "-5"}) .text == "-5"


def test_calc_parentheses() -> None:
    result = SimpleCalcTool().invoke({"expression": "(2+3)*4"})
    assert result.text == "20"


def test_calc_division_by_zero_returns_failure() -> None:
    result = SimpleCalcTool().invoke({"expression": "1/0"})
    assert result.success is False


def test_calc_rejects_function_call() -> None:
    result = SimpleCalcTool().invoke({"expression": "abs(-5)"})
    assert result.success is False


def test_calc_rejects_attribute_access() -> None:
    result = SimpleCalcTool().invoke({"expression": "1.real"})
    assert result.success is False


def test_calc_rejects_variable_name() -> None:
    result = SimpleCalcTool().invoke({"expression": "x+1"})
    assert result.success is False


def test_calc_rejects_string_constant() -> None:
    result = SimpleCalcTool().invoke({"expression": "'hello'"})
    assert result.success is False


def test_calc_float_result() -> None:
    result = SimpleCalcTool().invoke({"expression": "7/2"})
    assert result.text == "3.5"
