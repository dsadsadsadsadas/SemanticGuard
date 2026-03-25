import ast
import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger("semanticguard.sink_registry")

# Layer 1: Hardcoded Defaults (Fallback)
KNOWN_SINKS: Dict[str, List[str]] = {
    "middleware": [
        "errorHandler",
        "globalExceptionHandler",
        "sanitize_output",
        "strip_pii",
        "redact",
        "sanitize_input",
        "sanitize",
        "clean_input",
        "clean",
        "escape",
        "encode",
        "serialize",
    ],
    "decorators": [
        "sanitized",
        "pii_safe",
        "scrubbed",
    ],
    "patterns": [
        r"\.replace\(",          # masking pattern
        r"hashlib\.",            # hashing
        r"hashlib\.\w+\(",       # all hashlib functions — sha256, md5, sha512 etc
        r"\.encode\(",           # string encoding
        r"\.hexdigest\(",        # hash finalization — always safe output
        r"bcrypt\.",             # password hashing
        r"hmac\.",               # message authentication
        r"anonymize\(",          # anonymization
        r"mask_field\(",
    ]
}

import copy

# The active registry (merged with user config)
_current_registry: Dict[str, List[str]] = copy.deepcopy(KNOWN_SINKS)

def load(config_path: str = "sinks.config.json") -> None:
    """
    Load user-defined sinks from a JSON file and merge them into the registry.
    Handles malformed JSON by falling back to defaults with a warning.
    """
    global _current_registry
    # logger.info(f"DEBUG: KNOWN_SINKS middleware size: {len(KNOWN_SINKS['middleware'])}")
    
    if not os.path.exists(config_path):
        _current_registry = copy.deepcopy(KNOWN_SINKS)
        return

    try:
        with open(config_path, "r") as f:
            user_sinks = json.load(f)
            
        _current_registry = {
            "middleware": copy.deepcopy(KNOWN_SINKS["middleware"]) + user_sinks.get("middleware", []),
            "decorators": copy.deepcopy(KNOWN_SINKS["decorators"]) + [
                d.lstrip("@") for d in user_sinks.get("decorators", [])
            ],
            "patterns": copy.deepcopy(KNOWN_SINKS["patterns"]) + user_sinks.get("patterns", []),
        }
        logger.info(f"🛡️ Successfully loaded user sinks from {config_path}")
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Malformed JSON in {config_path}: {e}. Falling back to default sinks.")
        _current_registry = copy.deepcopy(KNOWN_SINKS)
    except Exception as e:
        logger.warning(f"⚠️ Error reading {config_path}: {e}. Falling back to default sinks.")
        _current_registry = copy.deepcopy(KNOWN_SINKS)

def is_sink(node: ast.AST) -> bool:
    """
    Walk the node. Return True if this call or decorator matches any registered sink signature.
    """
    import ast as _ast  # local alias, immune to namespace pollution
    
    # 1. Check Function Calls (Middleware/Sanitizers)
    if isinstance(node, _ast.Call):
        # Case A: Simple name call (e.g., sanitize(u))
        if isinstance(node.func, _ast.Name):
            func_name = node.func.id
            if func_name in _current_registry["middleware"]:
                return True
        
        # Case B: Attribute call (e.g., middleware.redact(u))
        elif isinstance(node.func, _ast.Attribute):
            attr_name = node.func.attr
            if attr_name in _current_registry["middleware"]:
                return True

    # 2. Check Decorators (Name or Call)
    # The 'node' could be from a function_def.decorator_list
    if isinstance(node, (_ast.Name, _ast.Call, _ast.Attribute)):
        dec_name = ""
        if isinstance(node, _ast.Name):
            dec_name = node.id
        elif isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            dec_name = node.func.id
        elif isinstance(node, _ast.Attribute):
            dec_name = node.attr
            
        if dec_name and dec_name in _current_registry["decorators"]:
            return True

    # 3. Check Regex Patterns against Node Source
    # We use ast.unparse (available in Python 3.9+) to get the source representation
    node_source = ""
    try:
        # ast.unparse is the standard way to get code back from node
        node_source = _ast.unparse(node)
    except (AttributeError, Exception):
        # Fallback or older python: try to build a simple string for Name/Call
        if isinstance(node, _ast.Name):
            node_source = node.id
        elif isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            node_source = f"{node.func.id}()"
        elif isinstance(node, _ast.Attribute):
            node_source = f"{node.attr}"

    if node_source:
        for pattern in _current_registry["patterns"]:
            if re.search(pattern, node_source):
                return True

    return False

# Initialize registry with defaults immediately
load()
