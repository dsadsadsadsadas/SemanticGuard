#!/usr/bin/env python3
"""
🔍 TREPAN Polyglot Taint Analysis Engine (taint_engine.py)
Phase 5: Cross-language security vulnerability detection

This engine coordinates taint analysis across multiple languages:
- Python (via existing ast_engine.py)
- JavaScript/TypeScript (via parsers/js_parser.py)

Architecture:
    PolyglotTaintEngine
        ├── _detect_language() → Identifies file language
        ├── scan_file() → Routes to appropriate parser
        └── parsers/
            ├── base_parser.py → Abstract interface
            ├── js_parser.py → JavaScript/TypeScript
            └── (python uses ast_engine.py)

Usage:
    engine = PolyglotTaintEngine()
    results = engine.scan_file("app.js")
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class Language(Enum):
    """Supported languages for taint analysis."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


@dataclass
class TaintResult:
    """Result of a taint analysis scan."""
    filepath: str
    language: Language
    sources: List[Dict[str, Any]] = field(default_factory=list)
    sinks: List[Dict[str, Any]] = field(default_factory=list)
    flows: List[Dict[str, Any]] = field(default_factory=list)
    vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class PolyglotTaintEngine:
    """
    Cross-language taint analysis coordinator.
    
    Routes files to appropriate language-specific parsers and
    aggregates vulnerability findings.
    """
    
    # File extension to language mapping
    EXTENSION_MAP = {
        '.py': Language.PYTHON,
        '.pyw': Language.PYTHON,
        '.js': Language.JAVASCRIPT,
        '.jsx': Language.JAVASCRIPT,
        '.mjs': Language.JAVASCRIPT,
        '.cjs': Language.JAVASCRIPT,
        '.ts': Language.TYPESCRIPT,
        '.tsx': Language.TYPESCRIPT,
        '.mts': Language.TYPESCRIPT,
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the Polyglot Taint Engine.
        
        Args:
            config: Optional configuration dict with settings like:
                - max_file_size: Maximum file size to scan (bytes)
                - enabled_languages: List of languages to enable
                - custom_sources: Additional source patterns
                - custom_sinks: Additional sink patterns
        """
        self.config = config or {}
        self._parsers: Dict[Language, Any] = {}
        self._initialize_parsers()
    
    def _initialize_parsers(self) -> None:
        """
        Lazy-load and cache language-specific parsers.
        
        Note: Parsers are initialized on first use to avoid
        importing unused dependencies.
        """
        # Parsers will be loaded on demand in scan_file()
        pass
    
    def _detect_language(self, filename: str) -> Language:
        """
        Detect the programming language from a filename.
        
        Args:
            filename: Path or filename to analyze
            
        Returns:
            Language enum indicating the detected language
        """
        ext = Path(filename).suffix.lower()
        return self.EXTENSION_MAP.get(ext, Language.UNKNOWN)
    
    def _get_parser(self, language: Language) -> Optional[Any]:
        """
        Get or create the parser for a specific language.
        
        Args:
            language: The language to get a parser for
            
        Returns:
            Parser instance or None if not supported
        """
        if language in self._parsers:
            return self._parsers[language]
        
        parser = None
        
        if language == Language.PYTHON:
            # Use existing ast_engine for Python
            try:
                from ast_engine import ASTEngine
                parser = ASTEngine()
            except ImportError:
                pass
                
        elif language in (Language.JAVASCRIPT, Language.TYPESCRIPT):
            # Use JavaScript parser for JS/TS
            try:
                from parsers.js_parser import JavascriptParser
                parser = JavascriptParser()
            except ImportError:
                pass
        
        if parser:
            self._parsers[language] = parser
        
        return parser
    
    def scan_file(self, filepath: str) -> TaintResult:
        """
        Scan a single file for taint analysis vulnerabilities.
        
        Routes to the appropriate language parser based on file extension.
        
        Args:
            filepath: Path to the file to scan
            
        Returns:
            TaintResult with sources, sinks, flows, and vulnerabilities
        """
        # Detect language
        language = self._detect_language(filepath)
        
        # Create result object
        result = TaintResult(
            filepath=filepath,
            language=language
        )
        
        # Handle unknown language
        if language == Language.UNKNOWN:
            result.errors.append(f"Unsupported file type: {Path(filepath).suffix}")
            return result
        
        # Check file exists
        if not os.path.exists(filepath):
            result.errors.append(f"File not found: {filepath}")
            return result
        
        # Get appropriate parser
        parser = self._get_parser(language)
        
        if parser is None:
            result.errors.append(f"Parser not available for {language.value}")
            return result
        
        # Read file content
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            result.errors.append(f"Failed to read file: {e}")
            return result
        
        # Route to language-specific analysis
        try:
            if language == Language.PYTHON:
                result = self._scan_python(filepath, content, parser)
            elif language in (Language.JAVASCRIPT, Language.TYPESCRIPT):
                result = self._scan_javascript(filepath, content, parser)
        except Exception as e:
            result.errors.append(f"Analysis failed: {e}")
        
        return result
    
    def _scan_python(self, filepath: str, content: str, parser: Any) -> TaintResult:
        """
        Scan Python file using ast_engine.
        
        Args:
            filepath: Path to the Python file
            content: File contents
            parser: ASTEngine instance
            
        Returns:
            TaintResult with findings
        """
        result = TaintResult(filepath=filepath, language=Language.PYTHON)
        
        # TODO: Integrate with ast_engine.py analysis
        # For now, placeholder that will be connected in Step 2
        result.errors.append("Python taint analysis not yet integrated")
        
        return result
    
    def _scan_javascript(self, filepath: str, content: str, parser: Any) -> TaintResult:
        """
        Scan JavaScript/TypeScript file.
        
        Args:
            filepath: Path to the JS/TS file
            content: File contents
            parser: JavascriptParser instance
            
        Returns:
            TaintResult with findings
        """
        result = TaintResult(filepath=filepath, language=self._detect_language(filepath))
        
        # Use the full scan() method for taint analysis
        try:
            issues = parser.scan(content)
            
            # Populate sources and sinks
            result.sources = parser.find_sources()
            result.sinks = parser.find_sinks()
            
            # Convert issues to vulnerabilities
            for issue in issues:
                result.vulnerabilities.append({
                    "type": issue.get("type", "UNKNOWN"),
                    "severity": issue.get("severity", "medium"),
                    "line": issue.get("line", 0),
                    "message": issue.get("message", ""),
                    "sink": issue.get("sink", ""),
                    "tainted_variable": issue.get("tainted_variable")
                })
                
        except Exception as e:
            result.errors.append(f"JavaScript parsing failed: {e}")
        
        return result
    
    def scan_directory(self, directory: str, recursive: bool = True) -> List[TaintResult]:
        """
        Scan all supported files in a directory.
        
        Args:
            directory: Path to directory to scan
            recursive: Whether to scan subdirectories
            
        Returns:
            List of TaintResult objects
        """
        results = []
        path = Path(directory)
        
        if not path.exists():
            return results
        
        pattern = '**/*' if recursive else '*'
        
        for filepath in path.glob(pattern):
            if filepath.is_file():
                language = self._detect_language(str(filepath))
                if language != Language.UNKNOWN:
                    results.append(self.scan_file(str(filepath)))
        
        return results


# CLI interface for standalone usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python taint_engine.py <file_or_directory>")
        print("       python taint_engine.py app.js")
        print("       python taint_engine.py ./src/")
        sys.exit(1)
    
    target = sys.argv[1]
    engine = PolyglotTaintEngine()
    
    if os.path.isfile(target):
        result = engine.scan_file(target)
        print(f"\n🔍 Taint Analysis: {result.filepath}")
        print(f"   Language: {result.language.value}")
        print(f"   Sources: {len(result.sources)}")
        print(f"   Sinks: {len(result.sinks)}")
        if result.errors:
            print(f"   Errors: {result.errors}")
    else:
        results = engine.scan_directory(target)
        print(f"\n🔍 Scanned {len(results)} files")
        for r in results:
            status = "✅" if not r.errors else "⚠️"
            print(f"   {status} {r.filepath} ({r.language.value})")
