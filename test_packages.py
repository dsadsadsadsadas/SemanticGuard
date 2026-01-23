#!/usr/bin/env python3
"""
TEST: Package Sentinel (Phase 9)
Verifies that package_sentinel.py correctly detects malicious packages
while allowing legitimate ones.

Test Cases:
1. Safe packages (requests, numpy) - Should ALLOW
2. Typosquatted packages (requessts, numpyy) - Should WARN/BLOCK
3. New/Low reputation packages - Should BLOCK

Run: python test_packages.py
"""

import sys
import io

# Fix Windows console encoding for Unicode/emoji
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

# Import the module under test
from package_sentinel import PackageSentinel, PolicyAction, PackageInfo


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print formatted test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{'='*60}")
    print(f"{status}: {test_name}")
    print(f"{'='*60}")
    if details:
        print(details)


def test_safe_packages():
    """
    TEST 1: Safe Packages
    Packages like 'requests' and 'numpy' should be ALLOWED.
    These are well-established, popular packages.
    """
    print("\n" + "🧪 TEST 1: SAFE PACKAGES ".ljust(60, "─"))
    
    sentinel = PackageSentinel()
    safe_packages = ["requests", "numpy"]
    
    all_passed = True
    details = []
    
    for pkg in safe_packages:
        decision = sentinel.check_package(pkg, registry="pypi")
        
        # Safe packages should be ALLOWED (not BLOCKED)
        # Note: They might get WARN for low downloads, but should NOT be BLOCKED
        passed = decision.action != PolicyAction.BLOCK
        
        status = "✅ ALLOWED" if passed else "❌ BLOCKED"
        result_line = f"  {pkg}: {decision.action.value.upper()} - {status}"
        details.append(result_line)
        print(result_line)
        
        for reason in decision.reasons:
            print(f"    └─ {reason}")
        
        if not passed:
            all_passed = False
    
    print_result("Safe Packages Test", all_passed, "\n".join(details))
    return all_passed


def test_typosquatted_packages():
    """
    TEST 2: Typosquatted Packages
    Packages like 'requessts' and 'numpyy' should WARN or BLOCK.
    These are suspicious misspellings of popular packages.
    """
    print("\n" + "🧪 TEST 2: TYPOSQUATTED PACKAGES ".ljust(60, "─"))
    
    sentinel = PackageSentinel()
    typosquat_packages = ["requessts", "numpyy", "pandass", "djanggo"]
    
    all_passed = True
    details = []
    
    for pkg in typosquat_packages:
        decision = sentinel.check_package(pkg, registry="pypi")
        
        # Typosquatted packages should be WARNED or BLOCKED (not ALLOWED with clean pass)
        # If the package doesn't exist, it will be BLOCKED (good!)
        # If it exists but is similar to a popular one, it should WARN
        is_detected = decision.action in [PolicyAction.WARN, PolicyAction.BLOCK]
        
        status = "✅ DETECTED" if is_detected else "❌ UNDETECTED"
        result_line = f"  {pkg}: {decision.action.value.upper()} - {status}"
        details.append(result_line)
        print(result_line)
        
        for reason in decision.reasons:
            print(f"    └─ {reason}")
        
        if decision.suggestions:
            for suggestion in decision.suggestions:
                print(f"    💡 {suggestion}")
        
        if not is_detected:
            all_passed = False
    
    print_result("Typosquatted Packages Test", all_passed, "\n".join(details))
    return all_passed


def test_new_low_reputation_package():
    """
    TEST 3: New/Low Reputation Packages
    Simulates a package created today with very few downloads.
    Should be BLOCKED due to age policy (< 7 days old).
    """
    print("\n" + "🧪 TEST 3: NEW/LOW REPUTATION PACKAGE ".ljust(60, "─"))
    
    # Create a mock PackageInfo that represents a package created TODAY
    # This simulates a brand new package with suspicious characteristics
    
    new_package_info = PackageInfo(
        name="totally-legit-package-2026",
        version="0.0.1",
        exists=True,
        created_date=datetime.now(timezone.utc),
        age_days=0,  # Created today!
        weekly_downloads=5,  # Very few downloads
        maintainer="suspicious_user_12345",
        homepage=None,
        description="Definitely not malware, trust me"
    )
    
    sentinel = PackageSentinel()
    
    # Patch the _fetch_pypi_info method to return our mock data
    with patch.object(sentinel, '_fetch_pypi_info', return_value=new_package_info):
        decision = sentinel.check_package("totally-legit-package-2026", registry="pypi")
    
    # New package should be BLOCKED
    passed = decision.action == PolicyAction.BLOCK
    
    status = "✅ BLOCKED" if passed else "❌ NOT BLOCKED"
    details = f"  Package: totally-legit-package-2026 (age: 0 days)\n"
    details += f"  Action: {decision.action.value.upper()} - {status}"
    
    print(details)
    for reason in decision.reasons:
        print(f"    └─ {reason}")
    
    print_result("New/Low Reputation Package Test", passed, details)
    return passed


def test_blocklist():
    """
    TEST 4: Blocklist Enforcement
    Packages on the blocklist should be immediately BLOCKED.
    """
    print("\n" + "🧪 TEST 4: BLOCKLIST ENFORCEMENT ".ljust(60, "─"))
    
    # Create sentinel with a custom blocklist
    sentinel = PackageSentinel()
    sentinel.blocklist = {"malicious-package", "known-bad-package"}
    
    decision = sentinel.check_package("malicious-package", registry="pypi")
    
    passed = decision.action == PolicyAction.BLOCK
    
    status = "✅ BLOCKED" if passed else "❌ NOT BLOCKED"
    details = f"  Package: malicious-package (on blocklist)\n"
    details += f"  Action: {decision.action.value.upper()} - {status}"
    
    print(details)
    for reason in decision.reasons:
        print(f"    └─ {reason}")
    
    print_result("Blocklist Enforcement Test", passed, details)
    return passed


def test_allowlist():
    """
    TEST 5: Allowlist Bypass
    Packages on the allowlist should bypass all checks and be ALLOWED.
    """
    print("\n" + "🧪 TEST 5: ALLOWLIST BYPASS ".ljust(60, "─"))
    
    # Create sentinel with a custom allowlist
    sentinel = PackageSentinel()
    sentinel.allowlist = {"internal-company-package"}
    
    decision = sentinel.check_package("internal-company-package", registry="pypi")
    
    passed = decision.action == PolicyAction.ALLOW
    
    status = "✅ ALLOWED" if passed else "❌ NOT ALLOWED"
    details = f"  Package: internal-company-package (on allowlist)\n"
    details += f"  Action: {decision.action.value.upper()} - {status}"
    
    print(details)
    for reason in decision.reasons:
        print(f"    └─ {reason}")
    
    print_result("Allowlist Bypass Test", passed, details)
    return passed


def main():
    """Run all Package Sentinel tests."""
    print("\n" + "🛡️ TREPAN PACKAGE SENTINEL TEST SUITE ".center(60, "═"))
    print("Testing Phase 9: Supply Chain Security")
    print("═" * 60)
    
    results = []
    
    # Run all tests
    results.append(("Safe Packages", test_safe_packages()))
    results.append(("Typosquatted Packages", test_typosquatted_packages()))
    results.append(("New/Low Reputation", test_new_low_reputation_package()))
    results.append(("Blocklist Enforcement", test_blocklist()))
    results.append(("Allowlist Bypass", test_allowlist()))
    
    # Print summary
    print("\n" + "═" * 60)
    print("📊 TEST SUMMARY")
    print("═" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Package Sentinel is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
