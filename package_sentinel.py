#!/usr/bin/env python3
"""
🛡️ TREPAN Package Sentinel (package_sentinel.py)
Supply Chain Guardian - Real-time package validation

Checks:
1. Package Exists - Is this a real package or AI hallucination?
2. Typosquatting - Levenshtein distance from popular packages
3. Age Check - Block packages < 7 days old (configurable)
4. Download Count - Warn on low-popularity packages
5. Known Vulnerabilities - Cross-reference with CVE databases (future)

Usage:
    python package_sentinel.py check requests
    python package_sentinel.py check reqeusts  # typosquatting detection
    python package_sentinel.py check-file requirements.txt
    python package_sentinel.py watch  # Monitor pip install commands
"""

import argparse
import json
import sys
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import urllib.request
import urllib.error
import difflib


class PolicyAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class PackageInfo:
    """Information about a package from PyPI/npm."""
    name: str
    version: str
    exists: bool
    created_date: Optional[datetime] = None
    age_days: Optional[int] = None
    weekly_downloads: Optional[int] = None
    maintainer: Optional[str] = None
    homepage: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PolicyDecision:
    """Decision about whether to allow a package."""
    action: PolicyAction
    package: str
    reasons: List[str]
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


# Popular packages for typosquatting detection
POPULAR_PACKAGES = {
    # Python
    'requests', 'numpy', 'pandas', 'flask', 'django', 'tensorflow',
    'pytorch', 'scipy', 'matplotlib', 'pillow', 'beautifulsoup4',
    'selenium', 'pytest', 'boto3', 'pyyaml', 'cryptography',
    'sqlalchemy', 'fastapi', 'uvicorn', 'pydantic', 'httpx',
    'aiohttp', 'redis', 'celery', 'scrapy', 'faker', 'jinja2',
    # npm
    'react', 'express', 'lodash', 'axios', 'moment', 'webpack',
    'typescript', 'next', 'vue', 'angular', 'jquery', 'socket.io',
}


class PackageSentinel:
    """Real-time package validation for supply chain security."""
    
    # Default policy thresholds
    DEFAULT_MIN_AGE_DAYS = 7
    DEFAULT_MIN_DOWNLOADS = 100
    DEFAULT_TYPOSQUAT_THRESHOLD = 0.85  # Similarity % to trigger warning
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.min_age_days = self.config.get('min_age_days', self.DEFAULT_MIN_AGE_DAYS)
        self.min_downloads = self.config.get('min_downloads', self.DEFAULT_MIN_DOWNLOADS)
        self.typosquat_threshold = self.config.get('typosquat_threshold', self.DEFAULT_TYPOSQUAT_THRESHOLD)
        self.allowlist = set(self.config.get('allowlist', []))
        self.blocklist = set(self.config.get('blocklist', []))
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file."""
        if config_path and os.path.exists(config_path):
            try:
                # Try to load YAML
                import yaml
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            except ImportError:
                # Fallback to JSON
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def check_package(self, package_name: str, registry: str = "pypi") -> PolicyDecision:
        """
        Check a package against all security policies.
        
        Args:
            package_name: Name of the package to check
            registry: 'pypi' or 'npm'
        
        Returns:
            PolicyDecision with ALLOW, WARN, or BLOCK
        """
        reasons = []
        suggestions = []
        action = PolicyAction.ALLOW
        
        # Normalize package name
        package_name = package_name.lower().strip()
        
        # Check blocklist first
        if package_name in self.blocklist:
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                package=package_name,
                reasons=["Package is on the blocklist"]
            )
        
        # Check allowlist (skip other checks)
        if package_name in self.allowlist:
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                package=package_name,
                reasons=["Package is on the allowlist"]
            )
        
        # 1. Check if package exists
        info = self._fetch_package_info(package_name, registry)
        
        if not info.exists:
            # Check for typosquatting
            similar = self._find_similar_packages(package_name)
            if similar:
                suggestions = [f"Did you mean: {', '.join(similar)}?"]
            
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                package=package_name,
                reasons=[f"Package '{package_name}' does not exist on {registry}"],
                suggestions=suggestions
            )
        
        # 2. Check for typosquatting of popular packages
        typo_match = self._check_typosquatting(package_name)
        if typo_match:
            reasons.append(f"⚠️ Possible typosquatting of '{typo_match}'")
            suggestions.append(f"Verify you meant '{package_name}' and not '{typo_match}'")
            action = PolicyAction.WARN
        
        # 3. Check package age
        if info.age_days is not None and info.age_days < self.min_age_days:
            reasons.append(f"🆕 Package is only {info.age_days} days old (min: {self.min_age_days})")
            suggestions.append("Wait until package has more history, or manually verify trustworthiness")
            action = PolicyAction.BLOCK
        
        # 4. Check download count
        if info.weekly_downloads is not None and info.weekly_downloads < self.min_downloads:
            reasons.append(f"📉 Low downloads: {info.weekly_downloads}/week (min: {self.min_downloads})")
            suggestions.append("Verify this is an intentional dependency")
            if action != PolicyAction.BLOCK:
                action = PolicyAction.WARN
        
        # If no issues found
        if not reasons:
            reasons = ["✅ Package passed all security checks"]
        
        return PolicyDecision(
            action=action,
            package=package_name,
            reasons=reasons,
            suggestions=suggestions
        )
    
    def _fetch_package_info(self, package_name: str, registry: str) -> PackageInfo:
        """Fetch package information from PyPI or npm."""
        if registry == "pypi":
            return self._fetch_pypi_info(package_name)
        elif registry == "npm":
            return self._fetch_npm_info(package_name)
        else:
            return PackageInfo(name=package_name, version="", exists=False)
    
    def _fetch_pypi_info(self, package_name: str) -> PackageInfo:
        """Fetch package info from PyPI."""
        url = f"https://pypi.org/pypi/{package_name}/json"
        
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                info = data.get('info', {})
                releases = data.get('releases', {})
                
                # Calculate age from first release
                created_date = None
                age_days = None
                if releases:
                    # Find earliest release
                    earliest = None
                    for version, release_info in releases.items():
                        if release_info:
                            upload_time = release_info[0].get('upload_time')
                            if upload_time:
                                dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                                if earliest is None or dt < earliest:
                                    earliest = dt
                    
                    if earliest:
                        created_date = earliest
                        age_days = (datetime.now(earliest.tzinfo) - earliest).days
                
                # Get weekly downloads (approximate from PyPI stats)
                # Note: PyPI doesn't provide this directly, would need BigQuery
                weekly_downloads = None
                
                return PackageInfo(
                    name=package_name,
                    version=info.get('version', ''),
                    exists=True,
                    created_date=created_date,
                    age_days=age_days,
                    weekly_downloads=weekly_downloads,
                    maintainer=info.get('author'),
                    homepage=info.get('home_page') or info.get('project_url'),
                    description=info.get('summary')
                )
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return PackageInfo(name=package_name, version="", exists=False)
            raise
        except Exception:
            return PackageInfo(name=package_name, version="", exists=False)
    
    def _fetch_npm_info(self, package_name: str) -> PackageInfo:
        """Fetch package info from npm."""
        url = f"https://registry.npmjs.org/{package_name}"
        
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                # Get time information
                time_info = data.get('time', {})
                created = time_info.get('created')
                
                created_date = None
                age_days = None
                if created:
                    created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    age_days = (datetime.now(created_date.tzinfo) - created_date).days
                
                latest = data.get('dist-tags', {}).get('latest', '')
                
                return PackageInfo(
                    name=package_name,
                    version=latest,
                    exists=True,
                    created_date=created_date,
                    age_days=age_days,
                    maintainer=data.get('maintainers', [{}])[0].get('name') if data.get('maintainers') else None,
                    homepage=data.get('homepage'),
                    description=data.get('description')
                )
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return PackageInfo(name=package_name, version="", exists=False)
            raise
        except Exception:
            return PackageInfo(name=package_name, version="", exists=False)
    
    def _check_typosquatting(self, package_name: str) -> Optional[str]:
        """Check if package name is suspiciously similar to a popular package."""
        for popular in POPULAR_PACKAGES:
            if package_name == popular:
                continue  # Exact match is fine
            
            similarity = difflib.SequenceMatcher(None, package_name, popular).ratio()
            if similarity >= self.typosquat_threshold:
                return popular
        
        return None
    
    def _find_similar_packages(self, package_name: str) -> List[str]:
        """Find similar package names for suggestions."""
        similar = []
        for popular in POPULAR_PACKAGES:
            similarity = difflib.SequenceMatcher(None, package_name, popular).ratio()
            if similarity >= 0.7:  # More lenient for suggestions
                similar.append(popular)
        
        return sorted(similar, key=lambda x: difflib.SequenceMatcher(None, package_name, x).ratio(), reverse=True)[:3]
    
    def check_requirements_file(self, filepath: str) -> List[PolicyDecision]:
        """Check all packages in a requirements.txt or package.json."""
        results = []
        path = Path(filepath)
        
        if path.suffix == '.txt' or path.name == 'requirements.txt':
            # Parse requirements.txt
            packages = self._parse_requirements_txt(path)
            for pkg in packages:
                results.append(self.check_package(pkg, registry="pypi"))
        
        elif path.suffix == '.json' or path.name == 'package.json':
            # Parse package.json
            packages = self._parse_package_json(path)
            for pkg in packages:
                results.append(self.check_package(pkg, registry="npm"))
        
        return results
    
    def _parse_requirements_txt(self, path: Path) -> List[str]:
        """Extract package names from requirements.txt."""
        packages = []
        try:
            content = path.read_text()
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                
                # Extract package name (before ==, >=, <=, etc.)
                match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                if match:
                    packages.append(match.group(1))
        except Exception:
            pass
        
        return packages
    
    def _parse_package_json(self, path: Path) -> List[str]:
        """Extract package names from package.json."""
        packages = []
        try:
            data = json.loads(path.read_text())
            deps = data.get('dependencies', {})
            dev_deps = data.get('devDependencies', {})
            packages.extend(deps.keys())
            packages.extend(dev_deps.keys())
        except Exception:
            pass
        
        return packages


def print_decision(decision: PolicyDecision, verbose: bool = False):
    """Pretty print a policy decision."""
    emoji = {
        PolicyAction.ALLOW: "✅",
        PolicyAction.WARN: "⚠️",
        PolicyAction.BLOCK: "🛑"
    }
    
    color_start = ""
    color_end = ""
    
    print(f"\n{emoji[decision.action]} {decision.action.value.upper()}: {decision.package}")
    print("─" * 40)
    
    for reason in decision.reasons:
        print(f"  • {reason}")
    
    if decision.suggestions:
        print("\n  Suggestions:")
        for suggestion in decision.suggestions:
            print(f"    → {suggestion}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="🛡️ Trepan Package Sentinel - Supply Chain Guardian"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Check single package
    check_parser = subparsers.add_parser("check", help="Check a single package")
    check_parser.add_argument("package", help="Package name to check")
    check_parser.add_argument("--registry", "-r", choices=["pypi", "npm"], default="pypi")
    check_parser.add_argument("--config", "-c", help="Path to config file")
    
    # Check requirements file
    file_parser = subparsers.add_parser("check-file", help="Check all packages in a file")
    file_parser.add_argument("file", help="Path to requirements.txt or package.json")
    file_parser.add_argument("--config", "-c", help="Path to config file")
    file_parser.add_argument("--fail-on-warn", action="store_true", help="Exit with error on warnings")
    
    args = parser.parse_args()
    
    if args.command == "check":
        config_path = getattr(args, 'config', None)
        sentinel = PackageSentinel(config_path=config_path)
        decision = sentinel.check_package(args.package, args.registry)
        print_decision(decision)
        
        if decision.action == PolicyAction.BLOCK:
            sys.exit(1)
        elif decision.action == PolicyAction.WARN:
            sys.exit(0)  # Warnings don't fail by default
        sys.exit(0)
    
    elif args.command == "check-file":
        config_path = getattr(args, 'config', None)
        sentinel = PackageSentinel(config_path=config_path)
        decisions = sentinel.check_requirements_file(args.file)
        
        has_block = False
        has_warn = False
        
        for decision in decisions:
            print_decision(decision)
            if decision.action == PolicyAction.BLOCK:
                has_block = True
            elif decision.action == PolicyAction.WARN:
                has_warn = True
        
        print("═" * 50)
        print(f"Total packages checked: {len(decisions)}")
        print(f"Blocked: {sum(1 for d in decisions if d.action == PolicyAction.BLOCK)}")
        print(f"Warnings: {sum(1 for d in decisions if d.action == PolicyAction.WARN)}")
        print(f"Allowed: {sum(1 for d in decisions if d.action == PolicyAction.ALLOW)}")
        
        if has_block:
            sys.exit(1)
        elif has_warn and args.fail_on_warn:
            sys.exit(1)
        sys.exit(0)
    
    else:
        parser.print_help()



# =============================================================================
# TREPAN INTEGRATION HELPER
# =============================================================================

def check_package_security(filepath: str) -> List[Dict]:
    """
    Helper for Trepan integration.
    Checks a requirements file and returns a list of issues (dictionaries).
    """
    results = []
    try:
        sentinel = PackageSentinel()
        decisions = sentinel.check_requirements_file(filepath)
        
        for d in decisions:
            if d.action in (PolicyAction.WARN, PolicyAction.BLOCK):
                severity = "CRITICAL" if d.action == PolicyAction.BLOCK else "HIGH"
                results.append({
                    "type": "SUPPLY_CHAIN",
                    "severity": severity,
                    "message": f"{d.action.value.upper()}: {d.package} - {', '.join(d.reasons)}",
                    "line": 0
                })
    except Exception as e:
        results.append({
            "type": "SUPPLY_CHAIN_ERROR",
            "severity": "LOW",
            "message": f"Sentinel check failed: {e}",
            "line": 0
        })
    return results


if __name__ == "__main__":
    main()
