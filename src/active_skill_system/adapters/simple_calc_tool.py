"""L3 Adapter — SimpleCalcTool (M009 S03).

A deterministic arithmetic tool for unit tests and dev. Supports +, -, *, /
on integers/floats. Uses a restricted AST-based evaluator (no ``eval`` of
arbitrary code). Implements ``ToolPort``.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolResult,
)

# Supported binary operators (AST node → Python operator).
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

# Supported unary operators.
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> int | float:
    """Recursively evaluate a restricted arithmetic AST."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        # pyrefly: ignore [bad-argument-type]
        op_fn = _BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op_fn(left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        # pyrefly: ignore [bad-argument-type]
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"unsupported unary op: {type(node.op).__name__}")
        return op_fn(operand)
    raise ValueError(f"unsupported AST node: {type(node).__name__}")


class SimpleCalcTool:
    """Deterministic arithmetic tool (no external API).

    capabilities: {compute}
    invoke({'expression': '2+2'}) → ToolResult(text='4', ...)
    """

    name = "simple_calc"
    capabilities = frozenset({ToolCapability.COMPUTE})

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        expression = args.get("expression", "")
        if not isinstance(expression, str) or not expression.strip():
            return ToolResult(text="", evidence_id=None, success=False)
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = _eval_node(tree.body)
            # Format: int if whole, else float.
            text = str(int(result)) if isinstance(result, float) and result.is_integer() else str(result)
            return ToolResult(text=text, evidence_id=expression, success=True)
        except Exception:  # noqa: BLE001
            return ToolResult(text="", evidence_id=expression, success=False)
