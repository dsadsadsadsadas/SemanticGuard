#!/usr/bin/env python3
"""
🟨 TREPAN JavaScript/TypeScript Parser (js_parser.py)
Heuristic Taint Analysis - Lightweight, No External Dependencies

Phase 5, Step 2: Smart taint tracking without tree-sitter.

Detection Flow:
    1. Source Discovery: Find variables assigned from untrusted input
    2. Sink Detection: Find dangerous function calls
    3. Taint Connection: Link tainted variables to sinks → Report vulnerabilities

Example Detection:
    let userInput = req.body.name;  // userInput is TAINTED
    eval(userInput);                // CRITICAL: Tainted var in eval()
"""

import re
from typing import List, Dict, Any, Set, Optional, Tuple
from dataclasses import dataclass, field
from parsers.base_parser import (
    BaseSecurityParser,
    SourceNode,
    SinkNode,
    TaintFlow,
    Severity,
    VulnerabilityType
)


@dataclass
class TaintedVariable:
    """A variable that holds untrusted data."""
    name: str
    source_type: str
    source_line: int
    source_pattern: str


@dataclass
class SecurityIssue:
    """A detected security vulnerability."""
    type: str  # XSS, RCE, SQLi, etc.
    severity: str  # critical, high, medium, low
    line: int
    message: str
    sink_name: str
    tainted_var: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
            "sink": self.sink_name,
            "tainted_variable": self.tainted_var
        }


class JavascriptParser(BaseSecurityParser):
    """
    JavaScript/TypeScript Heuristic Taint Analyzer.
    
    Tracks data flow from untrusted sources to dangerous sinks
    using regex-based pattern matching and variable tracking.
    
    No external dependencies required (no tree-sitter).
    """
    
    # ═══════════════════════════════════════════════════════════════
    # SOURCES: Where untrusted data enters the application
    # ═══════════════════════════════════════════════════════════════
    SOURCES = {
        # Express.js / Node.js HTTP
        r'req\.body(?:\.\w+)*': ('user_input', 'HTTP Request Body'),
        r'req\.query(?:\.\w+)*': ('user_input', 'URL Query Parameter'),
        r'req\.params(?:\.\w+)*': ('user_input', 'URL Path Parameter'),
        r'req\.headers(?:\.\w+)*': ('user_input', 'HTTP Header'),
        r'req\.cookies(?:\.\w+)*': ('user_input', 'HTTP Cookie'),
        r'request\.body(?:\.\w+)*': ('user_input', 'HTTP Request Body'),
        r'request\.query(?:\.\w+)*': ('user_input', 'URL Query Parameter'),
        
        # Browser Location
        r'window\.location(?:\.\w+)*': ('url', 'Window Location'),
        r'location\.search': ('url', 'URL Search Params'),
        r'location\.hash': ('url', 'URL Hash Fragment'),
        r'location\.href': ('url', 'Full URL'),
        r'document\.URL': ('url', 'Document URL'),
        r'document\.referrer': ('url', 'Referrer URL'),
        
        # CLI / Environment
        r'process\.argv(?:\[\d+\])?': ('cli', 'Command Line Argument'),
        r'process\.env(?:\.\w+|\[\w+\])?': ('env', 'Environment Variable'),
        
        # DOM / User Input
        r'document\.getElementById\([^)]+\)\.value': ('dom', 'DOM Input Value'),
        r'document\.querySelector\([^)]+\)\.value': ('dom', 'DOM Input Value'),
        r'\.value\b': ('dom', 'Input Value'),
        
        # Storage
        r'localStorage\.getItem\([^)]+\)': ('storage', 'Local Storage'),
        r'sessionStorage\.getItem\([^)]+\)': ('storage', 'Session Storage'),
        
        # WebSocket / Network
        r'message\.data': ('network', 'WebSocket Message'),
        r'event\.data': ('network', 'Event Data'),
    }
    
    # ═══════════════════════════════════════════════════════════════
    # SINKS: Dangerous operations where tainted data causes harm
    # ═══════════════════════════════════════════════════════════════
    SINKS = {
        # Code Execution (RCE)
        r'\beval\s*\(': ('RCE', Severity.CRITICAL, 'eval() - Arbitrary Code Execution'),
        r'\bFunction\s*\(': ('RCE', Severity.CRITICAL, 'Function() Constructor'),
        r'setTimeout\s*\(\s*[^,]+': ('RCE', Severity.HIGH, 'setTimeout with String'),
        r'setInterval\s*\(\s*[^,]+': ('RCE', Severity.HIGH, 'setInterval with String'),
        r'new\s+Function\s*\(': ('RCE', Severity.CRITICAL, 'new Function()'),
        
        # XSS - Cross Site Scripting
        r'\.innerHTML\s*=': ('XSS', Severity.HIGH, 'innerHTML Assignment'),
        r'\.outerHTML\s*=': ('XSS', Severity.HIGH, 'outerHTML Assignment'),
        r'document\.write\s*\(': ('XSS', Severity.HIGH, 'document.write()'),
        r'document\.writeln\s*\(': ('XSS', Severity.HIGH, 'document.writeln()'),
        r'\.insertAdjacentHTML\s*\(': ('XSS', Severity.HIGH, 'insertAdjacentHTML()'),
        r'dangerouslySetInnerHTML': ('XSS', Severity.HIGH, 'React dangerouslySetInnerHTML'),
        r'\$\s*\([^)]+\)\s*\.html\s*\(': ('XSS', Severity.HIGH, 'jQuery .html()'),
        r'\$\s*\([^)]+\)\s*\.append\s*\(': ('XSS', Severity.MEDIUM, 'jQuery .append()'),
        
        # Command Injection
        r'child_process\.exec\s*\(': ('RCE', Severity.CRITICAL, 'child_process.exec()'),
        r'child_process\.execSync\s*\(': ('RCE', Severity.CRITICAL, 'child_process.execSync()'),
        r'child_process\.spawn\s*\(': ('RCE', Severity.HIGH, 'child_process.spawn()'),
        r'require\s*\(\s*[\'"]child_process[\'"]\s*\)': ('RCE', Severity.HIGH, 'child_process require'),
        r'execSync\s*\(': ('RCE', Severity.CRITICAL, 'execSync()'),
        r'spawnSync\s*\(': ('RCE', Severity.HIGH, 'spawnSync()'),
        
        # Path Traversal / File Operations
        r'fs\.readFile(?:Sync)?\s*\(': ('PATH_TRAVERSAL', Severity.HIGH, 'fs.readFile()'),
        r'fs\.writeFile(?:Sync)?\s*\(': ('PATH_TRAVERSAL', Severity.HIGH, 'fs.writeFile()'),
        r'fs\.unlink(?:Sync)?\s*\(': ('PATH_TRAVERSAL', Severity.HIGH, 'fs.unlink()'),
        r'fs\.readdir(?:Sync)?\s*\(': ('PATH_TRAVERSAL', Severity.MEDIUM, 'fs.readdir()'),
        r'fs\.access(?:Sync)?\s*\(': ('PATH_TRAVERSAL', Severity.LOW, 'fs.access()'),
        r'path\.join\s*\(': ('PATH_TRAVERSAL', Severity.MEDIUM, 'path.join() - check for ..'),
        
        # SQL Injection (Raw Queries)
        r'\.query\s*\(\s*[`"\']': ('SQLi', Severity.CRITICAL, 'Raw SQL Query'),
        r'\.raw\s*\(\s*[`"\']': ('SQLi', Severity.CRITICAL, 'Raw Query Method'),
        r'sequelize\.query\s*\(': ('SQLi', Severity.HIGH, 'Sequelize Raw Query'),
        r'knex\.raw\s*\(': ('SQLi', Severity.HIGH, 'Knex Raw Query'),
        
        # Open Redirect
        r'res\.redirect\s*\(': ('REDIRECT', Severity.MEDIUM, 'Express Redirect'),
        r'location\.href\s*=': ('REDIRECT', Severity.MEDIUM, 'Location Assignment'),
        r'location\.replace\s*\(': ('REDIRECT', Severity.MEDIUM, 'Location Replace'),
        r'window\.location\s*=': ('REDIRECT', Severity.MEDIUM, 'Window Location Assignment'),
        r'window\.open\s*\(': ('REDIRECT', Severity.MEDIUM, 'Window Open'),
        
        # Deserialization
        r'JSON\.parse\s*\(': ('DESER', Severity.MEDIUM, 'JSON.parse() - Prototype Pollution Risk'),
        r'unserialize\s*\(': ('DESER', Severity.CRITICAL, 'unserialize()'),
        r'yaml\.load\s*\(': ('DESER', Severity.CRITICAL, 'YAML Load - Arbitrary Code'),
        
        # Prototype Pollution
        r'Object\.assign\s*\(': ('PROTO', Severity.MEDIUM, 'Object.assign() - Pollution Risk'),
        r'_\.merge\s*\(': ('PROTO', Severity.MEDIUM, 'Lodash merge()'),
        r'_\.extend\s*\(': ('PROTO', Severity.MEDIUM, 'Underscore extend()'),
        r'\[\s*\w+\s*\]\s*=': ('PROTO', Severity.LOW, 'Dynamic Property Assignment'),
    }
    
    # Variables that might look tainted but are safe
    SAFE_PATTERNS = {
        r'parseInt\s*\(',
        r'parseFloat\s*\(',
        r'Number\s*\(',
        r'String\s*\(',
        r'\.toString\s*\(',
        r'encodeURIComponent\s*\(',
        r'encodeURI\s*\(',
        r'escape\s*\(',
        r'sanitize\w*\s*\(',
        r'validate\w*\s*\(',
        r'clean\w*\s*\(',
        r'escapeHtml\s*\(',
        r'DOMPurify\.',
    }
    
    def __init__(self):
        """Initialize the JavaScript parser."""
        super().__init__()
        self._tainted_vars: Dict[str, TaintedVariable] = {}
        self._issues: List[SecurityIssue] = []
        self._lines: List[str] = []
    
    def reset(self) -> None:
        """Reset parser state."""
        super().reset()
        self._tainted_vars = {}
        self._issues = []
        self._lines = []
    
    def parse(self, content: str) -> bool:
        """
        Parse JavaScript/TypeScript source code.
        
        Args:
            content: Source code to parse
            
        Returns:
            True if parsing succeeded
        """
        self.reset()
        self._content = content
        self._lines = content.split('\n')
        self._ast = self._lines  # For is_parsed check
        return True
    
    def scan(self, content: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Full taint analysis scan.
        
        This is the main entry point that performs:
        1. Source Discovery - Find tainted variables
        2. Sink Detection - Find dangerous operations
        3. Taint Connection - Link tainted data to sinks
        
        Args:
            content: Optional content to parse (uses cached if None)
            
        Returns:
            List of security issues found
        """
        if content:
            self.parse(content)
        
        if not self.is_parsed:
            return []
        
        # Step A: Source Discovery - Find all tainted variables
        self._discover_tainted_variables()
        
        # Step B & C: Sink Detection + Taint Connection
        self._analyze_sinks_for_taint()
        
        return [issue.to_dict() for issue in self._issues]
    
    def _discover_tainted_variables(self) -> None:
        """
        Step A: Find all variables assigned from untrusted sources.
        
        Detects patterns like:
            let userInput = req.body.name;
            const query = req.query.search;
            var data = location.hash;
        """
        # Pattern to capture variable assignments
        # Matches: let/const/var name = ... OR name = ...
        assignment_pattern = re.compile(
            r'(?:let|const|var)?\s*(\w+)\s*=\s*(.+?)(?:;|$)',
            re.MULTILINE
        )
        
        for line_num, line in enumerate(self._lines, start=1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue
            
            # Find assignments
            for match in assignment_pattern.finditer(line):
                var_name = match.group(1)
                rhs = match.group(2)
                
                # Check if RHS contains a source
                for source_pattern, (source_type, source_desc) in self.SOURCES.items():
                    if re.search(source_pattern, rhs):
                        self._tainted_vars[var_name] = TaintedVariable(
                            name=var_name,
                            source_type=source_type,
                            source_line=line_num,
                            source_pattern=source_desc
                        )
                        break
    
    def _analyze_sinks_for_taint(self) -> None:
        """
        Step B & C: Find sinks and check if they use tainted data.
        
        Detects:
        1. Direct source usage: eval(req.body)
        2. Tainted variable usage: eval(userInput) where userInput is tainted
        """
        for line_num, line in enumerate(self._lines, start=1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue
            
            # Check each sink pattern
            for sink_pattern, (vuln_type, severity, sink_desc) in self.SINKS.items():
                sink_match = re.search(sink_pattern, line)
                if not sink_match:
                    continue
                
                # Found a sink - now check if it uses tainted data
                sink_context = line[sink_match.end():]
                
                # Check 1: Direct source usage in sink
                direct_taint = self._check_direct_source_in_sink(line, sink_match)
                if direct_taint:
                    source_desc = direct_taint
                    # Check for sanitization
                    if self._is_sanitized(line):
                        continue
                    
                    self._issues.append(SecurityIssue(
                        type=vuln_type,
                        severity=severity.value,
                        line=line_num,
                        message=f"Direct untrusted input ({source_desc}) passed to {sink_desc}",
                        sink_name=sink_desc,
                        tainted_var=None
                    ))
                    continue
                
                # Check 2: Tainted variable usage in sink
                for var_name, tainted_var in self._tainted_vars.items():
                    # Look for the tainted variable after the sink pattern
                    var_pattern = rf'\b{re.escape(var_name)}\b'
                    if re.search(var_pattern, sink_context) or re.search(var_pattern, line):
                        # Check for sanitization
                        if self._is_sanitized(line):
                            continue
                        
                        self._issues.append(SecurityIssue(
                            type=vuln_type,
                            severity=severity.value,
                            line=line_num,
                            message=f"Tainted variable '{var_name}' (from {tainted_var.source_pattern}) used in {sink_desc}",
                            sink_name=sink_desc,
                            tainted_var=var_name
                        ))
                        break  # Only report once per sink
    
    def _check_direct_source_in_sink(self, line: str, sink_match: re.Match) -> Optional[str]:
        """
        Check if a source pattern appears directly in the sink call.
        
        Example: eval(req.body.code) -> Returns "HTTP Request Body"
        """
        for source_pattern, (_, source_desc) in self.SOURCES.items():
            if re.search(source_pattern, line):
                return source_desc
        return None
    
    def _is_sanitized(self, line: str) -> bool:
        """
        Check if the line contains sanitization patterns.
        
        This reduces false positives when data is properly escaped.
        """
        for safe_pattern in self.SAFE_PATTERNS:
            if re.search(safe_pattern, line, re.IGNORECASE):
                return True
        return False
    
    def find_sources(self) -> List[Dict[str, Any]]:
        """
        Find all sources of untrusted data.
        
        Returns:
            List of source dictionaries
        """
        if not self.is_parsed:
            return []
        
        sources = []
        for line_num, line in enumerate(self._lines, start=1):
            for pattern, (source_type, source_desc) in self.SOURCES.items():
                for match in re.finditer(pattern, line):
                    source = SourceNode(
                        name=match.group(0),
                        line=line_num,
                        column=match.start(),
                        source_type=source_type,
                        context=line.strip()
                    )
                    sources.append(source)
                    self._sources.append(source)
        
        return [s.to_dict() for s in sources]
    
    def find_sinks(self) -> List[Dict[str, Any]]:
        """
        Find all dangerous sinks.
        
        Returns:
            List of sink dictionaries
        """
        if not self.is_parsed:
            return []
        
        sinks = []
        for line_num, line in enumerate(self._lines, start=1):
            for pattern, (vuln_type, severity, sink_desc) in self.SINKS.items():
                for match in re.finditer(pattern, line):
                    # Map vuln_type string to enum
                    vuln_enum = self._get_vuln_type(vuln_type)
                    
                    sink = SinkNode(
                        name=match.group(0),
                        line=line_num,
                        column=match.start(),
                        sink_type=vuln_type,
                        vulnerability=vuln_enum,
                        severity=severity,
                        context=line.strip()
                    )
                    sinks.append(sink)
                    self._sinks.append(sink)
        
        return [s.to_dict() for s in sinks]
    
    def _get_vuln_type(self, type_str: str) -> VulnerabilityType:
        """Convert string to VulnerabilityType enum."""
        mapping = {
            'RCE': VulnerabilityType.CODE_INJECTION,
            'XSS': VulnerabilityType.XSS,
            'SQLi': VulnerabilityType.SQL_INJECTION,
            'PATH_TRAVERSAL': VulnerabilityType.PATH_TRAVERSAL,
            'REDIRECT': VulnerabilityType.OPEN_REDIRECT,
            'DESER': VulnerabilityType.DESERIALIZATION,
            'PROTO': VulnerabilityType.PROTOTYPE_POLLUTION,
        }
        return mapping.get(type_str, VulnerabilityType.CODE_INJECTION)
    
    def get_tainted_variables(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all discovered tainted variables.
        
        Returns:
            Dictionary of variable name -> taint info
        """
        return {
            name: {
                'source_type': var.source_type,
                'source_line': var.source_line,
                'source_description': var.source_pattern
            }
            for name, var in self._tainted_vars.items()
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLI Testing Interface
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Test code with known vulnerabilities
    test_code = '''
// Safe code
const express = require('express');
const app = express();

// VULNERABLE: Tainted variable flows to eval
app.post('/danger', (req, res) => {
    let userCode = req.body.code;
    eval(userCode);  // CRITICAL: RCE via tainted variable
});

// VULNERABLE: Direct source in innerHTML
app.get('/xss', (req, res) => {
    document.getElementById('output').innerHTML = req.query.name;  // XSS
});

// VULNERABLE: Command injection
const { exec } = require('child_process');
let cmd = req.query.command;
exec(cmd);  // CRITICAL: RCE

// SAFE: Sanitized input
let safeInput = parseInt(req.body.count);
eval(safeInput);  // This is actually sanitized

// VULNERABLE: Path traversal
const fs = require('fs');
let filePath = req.params.file;
fs.readFileSync(filePath);  // Path traversal
'''

    parser = JavascriptParser()
    issues = parser.scan(test_code)
    
    print("\n" + "=" * 60)
    print("🔍 TREPAN JavaScript Taint Analysis")
    print("=" * 60)
    
    # Show tainted variables
    print("\n📌 Tainted Variables Found:")
    for name, info in parser.get_tainted_variables().items():
        print(f"   • {name} (line {info['source_line']}): {info['source_description']}")
    
    # Show issues
    print(f"\n🚨 Security Issues Found: {len(issues)}")
    for issue in issues:
        severity_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }.get(issue['severity'], '⚪')
        
        print(f"\n{severity_emoji} [{issue['type']}] Line {issue['line']}")
        print(f"   {issue['message']}")
        if issue['tainted_variable']:
            print(f"   Tainted var: {issue['tainted_variable']}")
