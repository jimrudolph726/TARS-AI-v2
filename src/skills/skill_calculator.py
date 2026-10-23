"""Skill: calculator — bounded arithmetic without eval or exec."""

from __future__ import annotations

import ast
import math
import operator
import statistics
from collections.abc import Callable

SKILL = {
    "name": "calculator",
    "required_params": ["expression"],
    "followup": True,
    "description": "Safely evaluate a bounded mathematical expression",
    "prompt": """calculator
   Triggers: Use when a user's request needs exact arithmetic or a standard
   mathematical/statistical function.
   Parameters:
     {{"expression": "<math expression>"}}
   The expression may contain numbers, +, -, *, /, //, %, **, parentheses,
   numeric lists, and these names: pi, e, tau, abs, round, min, max, sum,
   sqrt, sin, cos, tan, asin, acos, atan, log, log10, exp, floor, ceil,
   factorial, mean, median, stdev, pstdev.
   Do not send Python statements, imports, assignments, attributes, loops,
   comprehensions, strings, or code. Convert percentages into arithmetic.
   Example: {{"function": "calculator", "parameters":
   {{"expression": "15 / 100 * 240"}}}}""",
    "examples": [
        """Example - exact calculation:
User: "What is 15 percent of 240?"
Response: {{"reply": "Let me calculate that.", "function_calls": [{{"function":
"calculator", "parameters": {{"expression": "15 / 100 * 240"}}}}],
"new_memories": []}}""",
        """Example - statistics:
User: "What is the mean of 12, 17, 21, and 30?"
Response: {{"reply": "Calculating it now.", "function_calls": [{{"function":
"calculator", "parameters": {{"expression": "mean([12, 17, 21, 30])"}}}}],
"new_memories": []}}""",
    ],
    "order": 50,
}


class CalculationError(ValueError):
    """Raised when an expression is unsupported or exceeds a safety bound."""


_MAX_EXPRESSION_CHARS = 500
_MAX_AST_NODES = 128
_MAX_CONTAINER_ITEMS = 128
_MAX_POWER_EXPONENT = 100
_MAX_INTEGER_BITS = 4096
_MAX_ABS_FLOAT = 1e100
_MAX_OUTPUT_CHARS = 1000

_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_BINARY_OPERATORS: dict[type[ast.operator], Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _factorial(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalculationError("factorial requires an integer")
    if not 0 <= value <= 500:
        raise CalculationError("factorial input must be between 0 and 500")
    return math.factorial(value)


def _round(value, digits=0):
    if isinstance(digits, bool) or not isinstance(digits, int):
        raise CalculationError("round precision must be an integer")
    if not -100 <= digits <= 100:
        raise CalculationError("round precision must be between -100 and 100")
    return round(value, digits)


_FUNCTIONS: dict[str, Callable] = {
    "abs": abs,
    "round": _round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": _factorial,
    "mean": statistics.mean,
    "median": statistics.median,
    "stdev": statistics.stdev,
    "pstdev": statistics.pstdev,
}


def _validate_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculationError("only real numeric values are supported")
    if isinstance(value, int) and value.bit_length() > _MAX_INTEGER_BITS:
        raise CalculationError("integer result is too large")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalculationError("result must be finite")
        if abs(value) > _MAX_ABS_FLOAT:
            raise CalculationError("floating-point result is too large")
    return value


def _evaluate_node(node):
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)

    if isinstance(node, ast.Constant):
        return _validate_number(node.value)

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise CalculationError(f"unsupported name: {node.id}")

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        value = _validate_number(_evaluate_node(node.operand))
        return _validate_number(_UNARY_OPERATORS[type(node.op)](value))

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _validate_number(_evaluate_node(node.left))
        right = _validate_number(_evaluate_node(node.right))
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER_EXPONENT:
            raise CalculationError(
                f"power exponent exceeds {_MAX_POWER_EXPONENT}"
            )
        return _validate_number(_BINARY_OPERATORS[type(node.op)](left, right))

    if isinstance(node, (ast.List, ast.Tuple)):
        if len(node.elts) > _MAX_CONTAINER_ITEMS:
            raise CalculationError("too many values in one calculation")
        return [_validate_number(_evaluate_node(item)) for item in node.elts]

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise CalculationError("unsupported function")
        if node.keywords:
            raise CalculationError("keyword arguments are not supported")
        args = [_evaluate_node(argument) for argument in node.args]
        try:
            result = _FUNCTIONS[node.func.id](*args)
        except CalculationError:
            raise
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise CalculationError(str(exc)) from exc
        return _validate_number(result)

    raise CalculationError(f"unsupported expression element: {type(node).__name__}")


def evaluate_expression(expression: str):
    """Parse and evaluate one bounded mathematical expression."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculationError("no expression was provided")
    if len(expression) > _MAX_EXPRESSION_CHARS:
        raise CalculationError("expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        detail = exc.msg if isinstance(exc, SyntaxError) else str(exc)
        raise CalculationError(f"invalid expression: {detail}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise CalculationError("expression is too complex")
    return _evaluate_node(tree)


def _format_result(value) -> str:
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = repr(value)
    if len(text) > _MAX_OUTPUT_CHARS:
        raise CalculationError("result is too large to display")
    return text


def execute(parameters, context):
    """Evaluate a calculator expression and return a conversational result."""
    del context
    from modules.module_messageQue import queue_message

    expression = (
        parameters.get("expression", "") if isinstance(parameters, dict) else ""
    )
    try:
        result = evaluate_expression(expression)
        formatted = _format_result(result)
    except CalculationError as exc:
        queue_message(f"CALCULATOR: Rejected expression — {exc}")
        return f"I could not calculate that safely: {exc}."
    except (ArithmeticError, TypeError, ValueError) as exc:
        queue_message(f"CALCULATOR: Calculation failed — {exc}")
        return f"The calculation failed: {exc}."

    queue_message(f"CALCULATOR: {expression} = {formatted}")
    return f"The result is {formatted}."
