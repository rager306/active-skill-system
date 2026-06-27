"""Unit + property tests for the MiniMax provider adapter.

Offline suite (default): the adapter honors an explicit model, satisfies the
application's LLMProviderPort, is recognized as activegraph's LLMProvider, and
its thinking-preservation logic (cache + inject) works on fakes.

Gated suite (--runllm): real MiniMax calls — a single PONG and a full Diligence
tool-loop run that must produce claims + a memo with zero failures.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from active_skill_system.adapters.llm.minimax import MiniMaxProvider
from active_skill_system.application.ports.llm import LLMProviderPort


def _provider(model: str = "MiniMax-M3") -> MiniMaxProvider:
    return MiniMaxProvider(model=model)


@given(model=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()))
def test_explicit_model_is_honored(model: str) -> None:
    assert _provider(model).default_model == model


# ── extracted pure modules: _tokens.count_tokens_fallback ─────────────────


def test_count_tokens_fallback_floor_and_scaling() -> None:
    from active_skill_system.adapters.llm.minimax._tokens import count_tokens_fallback

    # empty input still returns at least 1 (cost gate needs a positive int)
    assert count_tokens_fallback(system="", messages=[], model="m") == 1
    # 4 chars -> 1 token (char/4 heuristic)
    assert count_tokens_fallback(system="abcd", messages=[], model="m") == 1
    assert count_tokens_fallback(system="abcdefgh", messages=[], model="m") == 2


def test_count_tokens_fallback_counts_messages_and_tool_calls() -> None:
    from activegraph.llm.types import LLMMessage, ToolCall

    from active_skill_system.adapters.llm.minimax._tokens import count_tokens_fallback

    msg = LLMMessage(
        role="assistant",
        content="abcd",  # 4 chars
        tool_calls=[ToolCall(id="t1", name="weather", args={"q": "SF"})],
    )
    n = count_tokens_fallback(system="abcd", messages=[msg], model="m")
    assert n >= 4  # system(1) + content(1) + tool name/args contribute


# ── extracted pure modules: _thinking.ThinkingTurnCache ───────────────────


def test_thinking_turn_cache_remember_and_restore() -> None:
    from active_skill_system.adapters.llm.minimax._thinking import ThinkingTurnCache

    cache = ThinkingTurnCache(limit=4)
    full = [
        {"type": "thinking", "thinking": "why", "signature": "s1"},
        {"type": "tool_use", "id": "toolu_1", "name": "g", "input": {}},
    ]
    cache.remember(["toolu_1"], full)
    assert list(cache.blocks) == ["toolu_1"]

    wire = [
        {"role": "assistant", "content": [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "toolu_1"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "r"}]},
    ]
    out = cache.restore(wire)
    assert out[0]["content"][0]["type"] == "thinking"  # restored
    assert out[1]["content"][0]["type"] == "tool_result"  # untouched


def test_thinking_turn_cache_evicts_when_over_limit() -> None:
    from active_skill_system.adapters.llm.minimax._thinking import ThinkingTurnCache

    cache = ThinkingTurnCache(limit=2)
    cache.remember(["a"], [{"type": "text", "text": "1"}])
    cache.remember(["b"], [{"type": "text", "text": "2"}])
    cache.remember(["c"], [{"type": "text", "text": "3"}])
    assert list(cache.blocks) == ["b", "c"]  # oldest evicted


@given(model=st.sampled_from(["MiniMax-M3", "MiniMax-M3-512k", "MiniMax-M2.7-highspeed"]))
def test_default_model_for_known_minimax(model: str) -> None:
    assert _provider(model).default_model == model


def test_falls_back_to_env_model_when_unspecified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "MiniMax-M3-test")
    assert MiniMaxProvider().default_model == "MiniMax-M3-test"


def test_satisfies_application_port() -> None:
    assert isinstance(_provider(), LLMProviderPort)


def test_is_activegraph_llm_provider() -> None:
    from activegraph.llm.provider import LLMProvider

    assert isinstance(_provider(), LLMProvider)


def test_complete_signature_present() -> None:
    assert callable(getattr(_provider(), "complete", None))


def test_count_tokens_is_heuristic_and_offline() -> None:
    # Must not hit the gateway (the MiniMax /count_tokens endpoint is unreliable);
    # it should return a positive int from content length alone.
    from activegraph.llm.types import LLMMessage

    p = _provider()
    n = p.count_tokens(
        system="hello world", messages=[LLMMessage(role="user", content="abc")], model="MiniMax-M3"
    )
    assert isinstance(n, int) and n > 0


# ── thinking-preservation logic (offline; fakes the SDK response) ───────────


class _Block:
    def __init__(self, type: str, **fields: object) -> None:
        self.type = type
        for k, v in fields.items():
            setattr(self, k, v)


class _Usage:
    def __init__(self, i: int, o: int) -> None:
        self.input_tokens = i
        self.output_tokens = o


class _Raw:
    def __init__(self, blocks: list, stop: str = "tool_use") -> None:
        self.content = blocks
        self.usage = _Usage(10, 5)
        self.stop_reason = stop
        self.model = "MiniMax-M3"


def test_block_to_dict_preserves_thinking_signature() -> None:
    from active_skill_system.adapters.llm.minimax._thinking import _block_to_dict

    b = _block_to_dict(_Block("thinking", thinking="reasoning", signature="sig-123"))
    assert b == {"type": "thinking", "thinking": "reasoning", "signature": "sig-123"}


def test_remember_turn_caches_full_blocks_by_tool_id() -> None:
    p = MiniMaxProvider(model="MiniMax-M3")
    raw = _Raw(
        [
            _Block("thinking", thinking="why", signature="s1"),
            _Block("text", text="calling"),
            _Block("tool_use", id="toolu_1", name="get_weather", input={"location": "SF"}),
        ]
    )
    p._remember_turn(raw)
    assert list(p._turn_blocks) == ["toolu_1"]
    blocks = p._turn_blocks["toolu_1"]
    assert blocks[0]["type"] == "thinking" and blocks[0]["signature"] == "s1"
    assert blocks[-1] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "get_weather",
        "input": {"location": "SF"},
    }


def test_restore_thinking_replaces_rebuilt_assistant_turn() -> None:
    """The rebuilt [text, tool_use] turn must be swapped for the cached
    [thinking, text, tool_use] so nothing is lost across the tool loop."""
    p = MiniMaxProvider(model="MiniMax-M3")
    p._turn_blocks["toolu_1"] = [
        {"type": "thinking", "thinking": "why", "signature": "s1"},
        {"type": "text", "text": "calling"},
        {"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"location": "SF"}},
    ]
    rebuilt = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "calling"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "get_weather",
                    "input": {"location": "SF"},
                },
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "24C"}],
        },
    ]
    out = p._restore_thinking(rebuilt)
    assistant_content = out[0]["content"]
    assert assistant_content[0]["type"] == "thinking"
    assert assistant_content[0]["signature"] == "s1"
    assert out[1]["content"][0]["type"] == "tool_result"  # tool_result untouched


# ── gated real LLM calls (skipped unless --runllm) ──────────────────────────


@pytest.mark.llm
def test_real_llm_pong() -> None:
    """uv run pytest --runllm -k real_llm_pong"""
    from activegraph.llm.types import LLMMessage

    from active_skill_system.adapters.llm.minimax import load_env

    load_env()
    p = MiniMaxProvider()
    r = p.complete(
        system="terse assistant",
        messages=[LLMMessage(role="user", content="Reply: PONG")],
        model=p.default_model,
        max_tokens=256,
        temperature=0.0,
        top_p=1.0,
        output_schema=None,
        timeout_seconds=60,
    )
    assert "PONG" in (getattr(r, "raw_text", "") or ""), (
        f"expected PONG in raw_text, got finish_reason={r.finish_reason!r} "
        f"raw_text={r.raw_text!r}"
    )


@pytest.mark.llm
def test_real_tool_loop_no_2013() -> None:
    """Gated: end-to-end Diligence on MiniMax-M3 must produce claims + a memo
    with zero behavior.failed (thinking preserved across the tool loop).
    uv run pytest --runllm -k real_tool_loop_no_2013

    Uses the Diligence fixture company (northwind robotics): the pack's
    fetch_company_docs tool serves recorded docs for fixture names only.
    """
    import sqlite3

    from activegraph import Graph, Runtime
    from activegraph.packs.diligence import DiligenceSettings
    from activegraph.packs.diligence import pack as diligence_pack

    from active_skill_system.adapters.llm.minimax import load_env

    load_env()
    db = "tests/_toolloop_smoke.db"
    rt = Runtime(
        Graph(),
        llm_provider=MiniMaxProvider(),
        persist_to=db,
        seed=0,
        budget={"max_llm_calls": 30, "max_tool_calls": 45, "max_cost_usd": "3.00"},
    )
    rt.load_pack(
        diligence_pack,
        settings=DiligenceSettings(
            llm_model=MiniMaxProvider().default_model,
            max_documents_per_company=2,
            max_claims_per_document=4,
            min_questions=3,
            max_questions=5,
        ),
    )
    rt.run_goal("Diligence: northwind robotics")  # fixture company
    rt.save_state()

    con = sqlite3.connect(db)

    def _count(obj_type: str) -> int:
        return con.execute(
            "select count(*) from events where type='object.created' "
            "and json_extract(payload, '$.object.type') = ?",
            (obj_type,),
        ).fetchone()[0]

    failed = con.execute("select count(*) from events where type='behavior.failed'").fetchone()[0]
    con.close()
    assert failed == 0, f"{failed} behavior.failed events — tool loop broken"
    assert _count("claim") > 0, "no claims produced — reasoning pipeline stalled"
    assert _count("memo") == 1, "no memo produced — synthesis did not complete"
