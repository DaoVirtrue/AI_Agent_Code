"""
Safe calculator tool using AST whitelist evaluation.

Only allows mathematical operations, disallowing any calls,
attribute access, or other unsafe constructs.
"""

import ast
import math
import operator
import logging
from typing import Any

from src.agent_system.tools.base import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)

# Allowed AST node types for safe evaluation
_SAFE_NODES: set[type] = {
    # Literals
    ast.Constant,
    ast.Num,  # Python < 3.8 compatibility
    ast.Str,  # Python < 3.8 compatibility

    # Expressions
    ast.Expression,
    ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp,
    ast.IfExp,

    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Invert,

    # Collections
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,

    # Names
    ast.Name, ast.Load,
}

# Allowed functions
_SAFE_FUNCTIONS: dict[str, callable] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
}

# Allowed constants
_SAFE_CONSTANTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": float("inf"),
    "nan": float("nan"),
    "True": True,
    "False": False,
    "None": None,
}


class CalculatorTool(BaseTool):
    """Safely evaluates mathematical expressions.

    Uses AST whitelisting to prevent code injection. Only allows
    mathematical operations and a limited set of safe built-ins.
    """

    def __init__(self):
        self._allowed_names = {**_SAFE_CONSTANTS, **_SAFE_FUNCTIONS}

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description=(
                "Evaluate a mathematical expression safely. "
                "Supports: +, -, *, /, **, //, %, abs, round, min, max, sum, "
                "and constants pi, e, tau. Example: '(3 * 4) + sqrt(25)'"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate.",
                    },
                },
                "required": ["expression"],
            },
            category="utility",
            timeout_seconds=5,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        expression = kwargs["expression"]

        try:
            result = self._safe_eval(expression)
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "expression": expression,
                    "result": result,
                    "type": type(result).__name__,
                },
            )
        except SyntaxError as e:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Syntax error: {e}",
            )
        except ValueError as e:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=str(e),
            )
        except Exception as e:
            logger.exception("Unexpected error in calculator")
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Evaluation error: {e}",
            )

    def _safe_eval(self, expression: str) -> Any:
        """Safely evaluate a mathematical expression using AST whitelisting.

        Args:
            expression: The string expression to evaluate.

        Returns:
            The numeric result.

        Raises:
            SyntaxError: If the expression has invalid syntax.
            ValueError: If the expression uses disallowed operations.
        """
        # Remove leading/trailing whitespace
        expression = expression.strip()

        # Try to parse as an expression
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            # Try to wrap in a safe context for multi-statement or assign
            raise

        # Validate all nodes are safe
        self._validate_node(tree)

        # Compile and evaluate
        code = compile(tree, "<calculator>", "eval")
        result = eval(code, {"__builtins__": {}}, self._allowed_names)

        # Sanity: prevent huge results
        if isinstance(result, (int, float)) and abs(result) > 1e308:
            raise ValueError("Result too large")

        return result

    def _validate_node(self, node: ast.AST) -> None:
        """Recursively validate that an AST node only uses safe operations.

        Raises:
            ValueError: If a disallowed node type is found.
        """
        node_type = type(node)

        if node_type not in _SAFE_NODES:
            raise ValueError(
                f"Disallowed operation: {node_type.__name__}. "
                f"Only mathematical expressions are permitted."
            )

        # Check Name nodes for allowed identifiers
        if isinstance(node, ast.Name):
            if node.id not in self._allowed_names:
                raise ValueError(
                    f"Disallowed identifier: '{node.id}'. "
                    f"Allowed: {sorted(self._allowed_names.keys())}"
                )

        # Recursively validate children
        for _field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self._validate_node(item)
            elif isinstance(value, ast.AST):
                self._validate_node(value)

    def add_function(self, name: str, func: callable) -> None:
        """Add an allowed function to the calculator's namespace."""
        self._allowed_names[name] = func

    def add_constant(self, name: str, value: Any) -> None:
        """Add an allowed constant to the calculator's namespace."""
        self._allowed_names[name] = value
