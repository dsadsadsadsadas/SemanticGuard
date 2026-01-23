#!/usr/bin/env python3
"""
🛡️ TREPAN CI Scanner (ci_scanner.py)
Headless CLI mode for CI/CD integration

Usage:
    python ci_scanner.py --path ./src --format sarif --fail-on critical
    python ci_scanner.py --path . --format json
    python ci_scanner.py --help

Exit Codes:
    0 = No issues found (or only warnings when --fail-on critical)
    1 = Critical issues found
    2 = Error during scanning
"""

import argparse
import ast
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"  
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityIssue:
    """Represents a detected security issue."""
    file: str
    line: int
    column: int
    severity: Severity
    rule_id: str
    message: str
    code_snippet: str = ""
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['severity'] = self.severity.value
        return d


class TrepanCIScanner:
    """Headless security scanner for CI/CD pipelines."""
    
    # Sensitive variable patterns
    SENSITIVE_KEYWORDS = {
        'password', 'secret', 'key', 'token', 'credential', 
        'auth', 'access_key', 'api_key', 'private_key'
    }
    
    # Dangerous function calls
    DANGEROUS_FUNCTIONS = {
        'eval': ('TREPAN-001', Severity.CRITICAL, 'Use of eval() is dangerous'),
        'exec': ('TREPAN-002', Severity.CRITICAL, 'Use of exec() is dangerous'),
        'compile': ('TREPAN-003', Severity.HIGH, 'Dynamic code compilation detected'),
        '__import__': ('TREPAN-004', Severity.HIGH, 'Dynamic import detected'),
    }
    
    # Unsafe logging functions
    LOGGING_FUNCTIONS = {'print', 'info', 'debug', 'warning', 'error', 'critical', 'log'}
    
    def __init__(self, extensions: List[str] = None):
        self.extensions = extensions or ['.py']
        self.issues: List[SecurityIssue] = []
        
    def scan_directory(self, path: str) -> List[SecurityIssue]:
        """Scan a directory recursively for security issues."""
        self.issues = []
        path = Path(path)
        
        if path.is_file():
            self._scan_file(path)
        elif path.is_dir():
            for ext in self.extensions:
                for file_path in path.rglob(f"*{ext}"):
                    # Skip common non-source directories
                    if any(skip in str(file_path) for skip in 
                           ['node_modules', '__pycache__', '.git', 'venv', '.venv']):
                        continue
                    self._scan_file(file_path)
        
        return self.issues
    
    def _scan_file(self, file_path: Path):
        """Scan a single file for security issues."""
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # Python-specific AST analysis
            if file_path.suffix == '.py':
                self._scan_python(file_path, content, lines)
            
            # Generic pattern matching for all files
            self._scan_generic_patterns(file_path, lines)
            
        except Exception as e:
            self.issues.append(SecurityIssue(
                file=str(file_path),
                line=0,
                column=0,
                severity=Severity.LOW,
                rule_id="TREPAN-ERR",
                message=f"Failed to scan file: {e}"
            ))
    
    def _scan_python(self, file_path: Path, content: str, lines: List[str]):
        """AST-based scanning for Python files."""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            self.issues.append(SecurityIssue(
                file=str(file_path),
                line=e.lineno or 0,
                column=e.offset or 0,
                severity=Severity.LOW,
                rule_id="TREPAN-SYN",
                message=f"Syntax error: {e.msg}"
            ))
            return
        
        for node in ast.walk(tree):
            # Check for hardcoded secrets
            if isinstance(node, ast.Assign):
                self._check_hardcoded_secret(file_path, node, lines)
            
            # Check for dangerous function calls
            if isinstance(node, ast.Call):
                self._check_dangerous_call(file_path, node, lines)
                self._check_unsafe_logging(file_path, node, lines)
    
    def _check_hardcoded_secret(self, file_path: Path, node: ast.Assign, lines: List[str]):
        """Detect hardcoded secrets in variable assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if any(kw in var_name for kw in self.SENSITIVE_KEYWORDS):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        if len(node.value.value.strip()) > 0:
                            snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                            self.issues.append(SecurityIssue(
                                file=str(file_path),
                                line=node.lineno,
                                column=node.col_offset,
                                severity=Severity.CRITICAL,
                                rule_id="TREPAN-SEC",
                                message=f"Hardcoded secret in variable '{target.id}'",
                                code_snippet=snippet.strip()
                            ))
    
    def _check_dangerous_call(self, file_path: Path, node: ast.Call, lines: List[str]):
        """Detect dangerous function calls like eval(), exec()."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        
        if func_name in self.DANGEROUS_FUNCTIONS:
            rule_id, severity, message = self.DANGEROUS_FUNCTIONS[func_name]
            snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            self.issues.append(SecurityIssue(
                file=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                severity=severity,
                rule_id=rule_id,
                message=message,
                code_snippet=snippet.strip()
            ))
    
    def _check_unsafe_logging(self, file_path: Path, node: ast.Call, lines: List[str]):
        """Detect logging of sensitive variables."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        if func_name in self.LOGGING_FUNCTIONS:
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    if any(kw in arg.id.lower() for kw in self.SENSITIVE_KEYWORDS):
                        snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        self.issues.append(SecurityIssue(
                            file=str(file_path),
                            line=node.lineno,
                            column=node.col_offset,
                            severity=Severity.HIGH,
                            rule_id="TREPAN-LOG",
                            message=f"Sensitive variable '{arg.id}' passed to logging function",
                            code_snippet=snippet.strip()
                        ))
    
    def _scan_generic_patterns(self, file_path: Path, lines: List[str]):
        """Generic pattern matching for common security issues."""
        for i, line in enumerate(lines, 1):
            # Check for TODO/FIXME security markers
            if 'TODO' in line.upper() and 'security' in line.lower():
                self.issues.append(SecurityIssue(
                    file=str(file_path),
                    line=i,
                    column=0,
                    severity=Severity.MEDIUM,
                    rule_id="TREPAN-TODO",
                    message="Security TODO found",
                    code_snippet=line.strip()
                ))


class OutputFormatter:
    """Format scan results for different output types."""
    
    @staticmethod
    def to_json(issues: List[SecurityIssue]) -> str:
        """Format as JSON."""
        return json.dumps({
            "trepan_version": "4.0",
            "scan_time": datetime.now().isoformat(),
            "total_issues": len(issues),
            "issues": [i.to_dict() for i in issues]
        }, indent=2)
    
    @staticmethod
    def to_sarif(issues: List[SecurityIssue]) -> str:
        """Format as SARIF (Static Analysis Results Interchange Format)."""
        # Group issues by rule
        rules = {}
        results = []
        
        for issue in issues:
            # Add rule if not exists
            if issue.rule_id not in rules:
                rules[issue.rule_id] = {
                    "id": issue.rule_id,
                    "name": issue.rule_id,
                    "shortDescription": {"text": issue.message.split(':')[0]},
                    "defaultConfiguration": {
                        "level": "error" if issue.severity in [Severity.CRITICAL, Severity.HIGH] else "warning"
                    }
                }
            
            # Add result
            results.append({
                "ruleId": issue.rule_id,
                "level": "error" if issue.severity in [Severity.CRITICAL, Severity.HIGH] else "warning",
                "message": {"text": issue.message},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": issue.file},
                        "region": {
                            "startLine": issue.line,
                            "startColumn": issue.column + 1
                        }
                    }
                }]
            })
        
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Trepan",
                        "version": "4.0",
                        "informationUri": "https://github.com/yourorg/trepan",
                        "rules": list(rules.values())
                    }
                },
                "results": results
            }]
        }
        
        return json.dumps(sarif, indent=2)
    
    @staticmethod
    def to_console(issues: List[SecurityIssue]) -> str:
        """Format as human-readable console output."""
        if not issues:
            return "✅ No security issues found!"
        
        lines = [
            "═" * 70,
            "🛡️ TREPAN CI Security Scan Results",
            "═" * 70,
            ""
        ]
        
        # Group by severity
        by_severity = {}
        for issue in issues:
            sev = issue.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(issue)
        
        severity_order = ['critical', 'high', 'medium', 'low']
        emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '⚪'}
        
        for sev in severity_order:
            if sev in by_severity:
                lines.append(f"\n{emoji[sev]} {sev.upper()} ({len(by_severity[sev])} issues):")
                lines.append("─" * 50)
                for issue in by_severity[sev]:
                    lines.append(f"  [{issue.rule_id}] {issue.file}:{issue.line}")
                    lines.append(f"    → {issue.message}")
                    if issue.code_snippet:
                        lines.append(f"    │ {issue.code_snippet}")
        
        lines.append("")
        lines.append("═" * 70)
        lines.append(f"Total: {len(issues)} issues found")
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="🛡️ Trepan CI Scanner - Security analysis for CI/CD pipelines"
    )
    parser.add_argument(
        "--path", "-p",
        default=".",
        help="Path to scan (file or directory)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "sarif", "console"],
        default="console",
        help="Output format"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--fail-on",
        choices=["low", "medium", "high", "critical"],
        default="high",
        help="Minimum severity to fail the build"
    )
    parser.add_argument(
        "--extensions", "-e",
        nargs="+",
        default=[".py"],
        help="File extensions to scan"
    )
    
    args = parser.parse_args()
    
    # Run scan
    scanner = TrepanCIScanner(extensions=args.extensions)
    
    print(f"🔍 Scanning: {args.path}", file=sys.stderr)
    issues = scanner.scan_directory(args.path)
    print(f"📊 Found {len(issues)} issues", file=sys.stderr)
    
    # Format output
    if args.format == "json":
        output = OutputFormatter.to_json(issues)
    elif args.format == "sarif":
        output = OutputFormatter.to_sarif(issues)
    else:
        output = OutputFormatter.to_console(issues)
    
    # Write output
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"📄 Results written to: {args.output}", file=sys.stderr)
    else:
        print(output)
    
    # Determine exit code
    fail_threshold = {
        "low": [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL],
        "medium": [Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL],
        "high": [Severity.HIGH, Severity.CRITICAL],
        "critical": [Severity.CRITICAL]
    }
    
    failing_issues = [i for i in issues if i.severity in fail_threshold[args.fail_on]]
    
    if failing_issues:
        print(f"❌ Build failed: {len(failing_issues)} {args.fail_on}+ severity issues", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"✅ Build passed (no {args.fail_on}+ severity issues)", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
