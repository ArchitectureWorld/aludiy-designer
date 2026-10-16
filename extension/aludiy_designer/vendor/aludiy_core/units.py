"""Safe parsing for Rhino-style precise length and polar input."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
import operator
import re

from .errors import InputParseError

_MAX_EXPRESSION_LENGTH = 128
_MAX_AST_NODES = 64
_MAX_ABS_VALUE = 1.0e12
_UNIT_FACTORS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
_UNIT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.])((?:\d+(?:\.\d*)?|\.\d+))\s*(mm|cm|m)\b",
    re.IGNORECASE,
)
_ALLOWED_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


@dataclass(frozen=True, slots=True)
class PolarInput:
    length_mm: float
    angle_deg: float


def _replace_units(expression: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        value = match.group(1)
        unit = match.group(2).lower()
        return f"({value}*{_UNIT_FACTORS_MM[unit]!r})"

    return _UNIT_TOKEN.sub(replacement, expression)


def _evaluate_numeric_expression(expression: str) -> float:
    if not isinstance(expression, str) or not expression.strip():
        raise InputParseError("numeric input is empty")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise InputParseError("numeric input is too long")
    normalized = _replace_units(expression.strip())
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise InputParseError(f"invalid numeric expression: {expression}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise InputParseError("numeric expression is too complex")

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise InputParseError("only numeric constants are allowed")
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY:
            left = evaluate(node.left)
            right = evaluate(node.right)
            try:
                value = _ALLOWED_BINARY[type(node.op)](left, right)
            except (ZeroDivisionError, OverflowError) as exc:
                raise InputParseError("invalid arithmetic operation") from exc
            return float(value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            return float(_ALLOWED_UNARY[type(node.op)](evaluate(node.operand)))
        raise InputParseError(
            f"unsupported token in numeric expression: {type(node).__name__}"
        )

    value = evaluate(tree)
    if not math.isfinite(value) or abs(value) > _MAX_ABS_VALUE:
        raise InputParseError("numeric result is not finite or is out of range")
    return value


def parse_distance_mm(text: str) -> float:
    """Parse a signed or zero-safe distance expression in millimeters."""

    return _evaluate_numeric_expression(text)


def parse_length_mm(text: str) -> float:
    """Parse a positive length and return millimeters.

    Plain numeric tokens are interpreted as millimeters. Explicit ``mm``,
    ``cm`` and ``m`` suffixes may be mixed in safe arithmetic expressions.
    """

    value = _evaluate_numeric_expression(text)
    if value <= 0.0:
        raise InputParseError("length must be greater than zero")
    return value


def parse_polar(text: str) -> PolarInput:
    """Parse ``@length<angle`` using millimeters and degrees."""

    candidate = str(text).strip()
    if not candidate.startswith("@") or "<" not in candidate[1:]:
        raise InputParseError("polar input must use @length<angle")
    length_text, angle_text = candidate[1:].split("<", 1)
    length_mm = parse_length_mm(length_text)
    angle_deg = _evaluate_numeric_expression(angle_text)
    return PolarInput(length_mm=length_mm, angle_deg=angle_deg)
