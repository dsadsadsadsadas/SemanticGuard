import ast
from typing import List, Dict

# Keywords that indicate a variable contains sensitive information
SENSITIVE_KEYWORDS = {'password', 'secret', 'key', 'token', 'credential', 'auth', 'access_key'}

class SecretScanner(ast.NodeVisitor):
    def __init__(self):
        self.issues = []

    def _is_sensitive(self, name: str) -> bool:
        """Check if a variable name suggests it contains sensitive data."""
        return any(keyword in name.lower() for keyword in SENSITIVE_KEYWORDS)

    def visit_Assign(self, node):
        """
        Detects: password = "plain_text_secret"
        """
        # We only care if a literal string is being assigned
        if not isinstance(node.value, ast.Constant):
            return
        if not isinstance(node.value.value, str):
            return
            
        # Check all targets of the assignment (e.g. x = y = "secret")
        for target in node.targets:
            if isinstance(target, ast.Name):
                if self._is_sensitive(target.id):
                    # Filter out empty strings or placeholders which might be safe
                    if len(node.value.value.strip()) > 0:
                        self.issues.append({
                            'line': node.lineno,
                            'type': 'Hardcoded Secret',
                            'message': f"Variable '{target.id}' assigned hardcoded string value."
                        })
        self.generic_visit(node)

    def visit_Call(self, node):
        """
        Detects: print(password) or logging.info(secret)
        """
        func_name = ""
        # Handle simple calls: print(...)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        # Handle attribute calls: logging.info(...)
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        # List of logging/printing functions to watch
        unsafe_funcs = {'print', 'info', 'debug', 'warning', 'error', 'critical', 'log', 'exception'}
        
        if func_name in unsafe_funcs:
            for arg in node.args:
                if isinstance(arg, ast.Name) and self._is_sensitive(arg.id):
                     self.issues.append({
                        'line': node.lineno,
                        'type': 'Unsafe Logging',
                        'message': f"Sensitive variable '{arg.id}' passed to '{func_name}'."
                    })
        self.generic_visit(node)

def scan_for_secrets(code_content: str) -> List[Dict]:
    """
    Scans Python code string for security issues using AST.
    Returns a list of dictionaries with issue details.
    """
    try:
        tree = ast.parse(code_content)
        scanner = SecretScanner()
        scanner.visit(tree)
        return scanner.issues
    except SyntaxError:
        # If code is actively being typed, it might be syntax invalid. Ignore.
        return []
    except Exception as e:
        return [{'line': 0, 'type': 'Error', 'message': f"AST Analysis Failed: {str(e)}"}]
