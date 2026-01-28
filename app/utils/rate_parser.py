import ast
import operator as op

_ALLOWED_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

def parse_rate_expr(expr: str) -> float:
    """
    Parse a simple arithmetic expression safely.
    Allowed: numbers, + - * /, parentheses, unary +/-
    Examples: "1000/1.5", "(2000+500)/2"
    """
    if expr is None:
        raise ValueError("Rate is empty")

    s = str(expr).strip().replace(",", "")
    if not s:
        raise ValueError("Rate is empty")

    node = ast.parse(s, mode="eval").body

    def _eval(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(n.op)](_eval(n.operand))
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(n.op)](_eval(n.left), _eval(n.right))
        raise ValueError("Unsupported expression")

    val = _eval(node)
    if not (val == val) or val in (float("inf"), float("-inf")):
        raise ValueError("Invalid numeric result")
    return val
