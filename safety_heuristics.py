#!/usr/bin/env python3
"""
🛡️ TREPAN Safety Heuristics (TR-08)
Critical capability detection via hardened regex patterns.

If ANY of these patterns trigger, Silent Mode is forbidden.
Forces immediate user intervention.
"""

import re
from typing import Tuple, Optional


class SafetyHeuristics:
    """
    Critical capability detection.
    If ANY of these trigger, Silent Mode is forbidden.
    """

    def __init__(self):
        self.CRITICAL_PATTERNS = {
            # Arbitrary or shell execution
            "EXECUTION": [
                r"\bexec\s*\(",
                r"\beval\s*\(",
                r"__import__\s*\(",
                r"getattr\s*\(\s*__builtins__",
                r"os\.system\s*\(",
                r"os\.popen\s*\(",
                r"subprocess\.(Popen|call|run|check_output)",
                r"\bpty\.spawn\s*\(",
            ],

            # Network access / exfiltration
            "NETWORK": [
                r"\bimport\s+socket\b",
                r"socket\.socket\s*\(",
                r"requests\.(get|post|put|delete|patch|request)",
                r"httpx\.(get|post|request)",
                r"urllib\.request\.",
                r"\bboto3\.(client|resource)\s*\(",
                r"paramiko\.",
            ],

            # Secrets & credentials
            "SECRETS": [
                r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH|PGP)\s+PRIVATE\s+KEY-----",
                r"AKIA[0-9A-Z]{16}",                      # AWS Access Key ID
                r"ASIA[0-9A-Z]{16}",                      # AWS STS
                r"gh[pousr]_[A-Za-z0-9]{36,}",            # GitHub tokens
                r"sk-[A-Za-z0-9]{20,}",                   # OpenAI / Stripe-like
                r"AIza[0-9A-Za-z\-_]{35}",                # Google API key
            ],

            # Filesystem destruction / persistence
            "FILESYSTEM": [
                r"\bopen\s*\(.*,[^\)]*[\"']w[\"']",
                r"\bopen\s*\(.*,[^\)]*[\"']a[\"']",
                r"os\.remove\s*\(",
                r"os\.unlink\s*\(",
                r"os\.rmdir\s*\(",
                r"shutil\.rmtree\s*\(",
                r"shutil\.copy(tree|file)?\s*\(",
                r"pathlib\.Path\(.+\)\.(write_text|write_bytes)",
            ],

            # Crypto footguns
            "CRYPTO_WEAKENING": [
                r"==\s*secrets\.compare_digest",
                r"hashlib\.(md5|sha1)\s*\(",
                r"random\.random\s*\(",
                r"ssl\._create_unverified_context",
                r"verify\s*=\s*False",
            ],
        }

        # Precompile for speed and consistency
        self._compiled = {}
        for category, patterns in self.CRITICAL_PATTERNS.items():
            self._compiled[category] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns
            ]

    def scan_for_critical_danger(self, code_snippet: str) -> Tuple[bool, Optional[str]]:
        """
        Scan code for critical security patterns.
        
        Args:
            code_snippet: The code to analyze
            
        Returns:
            Tuple of (is_dangerous, reason)
            - is_dangerous: True if ANY critical pattern matched
            - reason: Description of the match (e.g., "CRITICAL:EXECUTION:exec\\s*\\(")
        """
        if not code_snippet or not isinstance(code_snippet, str):
            return False, None

        for category, patterns in self._compiled.items():
            for pattern in patterns:
                if pattern.search(code_snippet):
                    return True, f"CRITICAL:{category}:{pattern.pattern}"

        return False, None
    
    def get_all_matches(self, code_snippet: str) -> list:
        """
        Get all matching patterns for detailed reporting.
        
        Returns:
            List of (category, pattern, match_text) tuples
        """
        matches = []
        if not code_snippet or not isinstance(code_snippet, str):
            return matches

        for category, patterns in self._compiled.items():
            for pattern in patterns:
                found = pattern.findall(code_snippet)
                if found:
                    matches.append((category, pattern.pattern, found))
        
        return matches


# Global instance
safety_guard = SafetyHeuristics()
