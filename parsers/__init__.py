"""
TREPAN Parsers Package
Language-specific security parsers for taint analysis.

Available Parsers:
    - BaseSecurityParser: Abstract base class (base_parser.py)
    - JavascriptParser: JavaScript/TypeScript parser (js_parser.py)
"""

from parsers.base_parser import BaseSecurityParser
from parsers.js_parser import JavascriptParser

__all__ = ['BaseSecurityParser', 'JavascriptParser']
