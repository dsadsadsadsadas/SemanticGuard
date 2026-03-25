# Secure Calculator Service
import ast
import operator

ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

def calculate_expression(expr: str) -> float:
    """Safely evaluate mathematical expression"""
    try:
        tree = ast.parse(expr, mode='eval')
        return _eval_node(tree.body)
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")

def _eval_node(node):
    """Recursively evaluate AST node"""
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.BinOp):
        op = ALLOWED_OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator")
        return op(_eval_node(node.left), _eval_node(node.right))
    else:
        raise ValueError("Unsupported expression")
