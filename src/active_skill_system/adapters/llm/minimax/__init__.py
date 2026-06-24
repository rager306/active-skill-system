"""MiniMax LLM provider package (Anthropic-compatible gateway).

Public API (stable, re-exported here so importers don't reach into private
modules):

    MiniMaxProvider  — thinking-preserving provider for MiniMax-M3 via the
                       Anthropic-compatible gateway.
    load_env         — load the project ``.env`` carrying gateway credentials.

Internally split (each module ≤150 LOC, R006):

    _env       — environment loading (load_env, ENV_PATH, PROJECT_ROOT)
    _tokens    — count_tokens char/4 fallback
    _thinking  — thinking-preservation turn cache (_block_to_dict, ThinkingTurnCache)
    _provider  — MiniMaxProvider (lifecycle + complete)
"""

from __future__ import annotations

from active_skill_system.adapters.llm.minimax._env import load_env
from active_skill_system.adapters.llm.minimax._provider import MiniMaxProvider

__all__ = ["MiniMaxProvider", "load_env"]
