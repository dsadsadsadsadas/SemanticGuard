#!/usr/bin/env python3
"""
🔧 TREPAN Base Security Parser (base_parser.py)
Abstract base class for language-specific security parsers.

All language parsers must implement this interface to ensure
consistent taint analysis across Python, JavaScript, TypeScript, etc.

Concepts:
    - Sources: Points where untrusted data enters (user input, network, files)
    - Sinks: Points where data is used dangerously (eval, SQL, file writes)
    - Flows: Paths from sources to sinks (the actual vulnerability)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Vulnerability severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityType(Enum):
    """Common vulnerability categories."""
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    SSRF = "ssrf"
    CODE_INJECTION = "code_injection"
    DESERIALIZATION = "deserialization"
    PROTOTYPE_POLLUTION = "prototype_pollution"  # JS-specific
    REGEX_DOS = "regex_dos"
    OPEN_REDIRECT = "open_redirect"


@dataclass
class SourceNode:
    """Represents a source of untrusted data."""
    name: str
    line: int
    column: int
    source_type: str  # e.g., "user_input", "network", "file", "env"
    context: str = ""  # Code snippet
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "line": self.line,
            "column": self.column,
            "type": self.source_type,
            "context": self.context
        }


@dataclass
class SinkNode:
    """Represents a dangerous sink where data should not flow unvalidated."""
    name: str
    line: int
    column: int
    sink_type: str  # e.g., "eval", "sql", "file_write", "command"
    vulnerability: VulnerabilityType
    severity: Severity = Severity.HIGH
    context: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "line": self.line,
            "column": self.column,
            "type": self.sink_type,
            "vulnerability": self.vulnerability.value,
            "severity": self.severity.value,
            "context": self.context
        }


@dataclass
class TaintFlow:
    """Represents a data flow from source to sink."""
    source: SourceNode
    sink: SinkNode
    path: List[str] = field(default_factory=list)  # Variable names in flow
    sanitizers: List[str] = field(default_factory=list)  # Applied sanitizers
    is_vulnerable: bool = True  # False if properly sanitized
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "sink": self.sink.to_dict(),
            "path": self.path,
            "sanitizers": self.sanitizers,
            "is_vulnerable": self.is_vulnerable
        }


class BaseSecurityParser(ABC):
    """
    Abstract base class for language-specific security parsers.
    
    Subclasses must implement:
        - parse(content): Parse source code into AST/IR
        - find_sources(): Locate untrusted data entry points
        - find_sinks(): Locate dangerous operations
        - find_flows(): (Optional) Trace data from sources to sinks
    
    Example usage:
        parser = JavascriptParser()
        parser.parse(code)
        sources = parser.find_sources()
        sinks = parser.find_sinks()
        flows = parser.find_flows()
    """
    
    def __init__(self):
        """Initialize the parser."""
        self._ast: Optional[Any] = None
        self._content: str = ""
        self._sources: List[SourceNode] = []
        self._sinks: List[SinkNode] = []
        self._flows: List[TaintFlow] = []
    
    @property
    def is_parsed(self) -> bool:
        """Check if content has been parsed."""
        return self._ast is not None
    
    @abstractmethod
    def parse(self, content: str) -> bool:
        """
        Parse source code into an AST or intermediate representation.
        
        Args:
            content: Source code string to parse
            
        Returns:
            True if parsing succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    def find_sources(self) -> List[Dict[str, Any]]:
        """
        Find all sources of untrusted data in the parsed code.
        
        Sources include:
            - User input (req.body, request.args, etc.)
            - URL parameters
            - File reads
            - Network responses
            - Environment variables
            - Database results (in some contexts)
        
        Returns:
            List of source dictionaries with location and type info
        """
        pass
    
    @abstractmethod
    def find_sinks(self) -> List[Dict[str, Any]]:
        """
        Find all dangerous sinks in the parsed code.
        
        Sinks include:
            - eval(), exec(), Function()
            - SQL query execution
            - File system operations
            - Command execution (subprocess, child_process)
            - HTML rendering (innerHTML, dangerouslySetInnerHTML)
            - Serialization/deserialization
        
        Returns:
            List of sink dictionaries with location, type, and severity
        """
        pass
    
    def find_flows(self) -> List[Dict[str, Any]]:
        """
        Trace data flow from sources to sinks.
        
        This is the core taint analysis that identifies actual vulnerabilities
        by tracking how untrusted data propagates through the code.
        
        Returns:
            List of flow dictionaries connecting sources to sinks
        
        Note:
            Default implementation returns empty list.
            Subclasses should override for full taint tracking.
        """
        return [flow.to_dict() for flow in self._flows]
    
    def get_vulnerabilities(self) -> List[Dict[str, Any]]:
        """
        Get all detected vulnerabilities (unvalidated flows to sinks).
        
        Returns:
            List of vulnerability dictionaries
        """
        vulnerabilities = []
        for flow in self._flows:
            if flow.is_vulnerable:
                vulnerabilities.append({
                    "type": flow.sink.vulnerability.value,
                    "severity": flow.sink.severity.value,
                    "source": flow.source.to_dict(),
                    "sink": flow.sink.to_dict(),
                    "flow_path": flow.path
                })
        return vulnerabilities
    
    def reset(self) -> None:
        """Reset parser state for reuse."""
        self._ast = None
        self._content = ""
        self._sources = []
        self._sinks = []
        self._flows = []
