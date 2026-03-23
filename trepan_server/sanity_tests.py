"""
Trepan Adversarial Sanity Test Suite

Tests exploitability logic under adversarial conditions.
Validates that AST and LLM reasoning are aligned and reliable.
"""
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
from enum import Enum

class Severity(Enum):
    SAFE = 0
    LOW = 30
    HIGH = 70
    CRITICAL = 100

@dataclass
class TestCase:
    name: str
    code: str
    language: str
    tier: int  # 1-4
    expected_severity: Severity
    description: str

@dataclass
class TestResult:
    test_name: str
    expected: Severity
    ast_result: Severity
    llm_result: Severity
    final_result: Severity
    confidence: int  # 0-100
    passed: bool
    reason: str

class AdversarialSanityTests:
    """Adversarial test suite for exploitability detection."""
    
    # ── TIER 1: BASIC (must NEVER fail) ──────────────────────────────────────
    TIER_1_TESTS = [
        TestCase(
            name="test_safe_static",
            code="""const cp = require('child_process');
cp.spawn('/bin/ls', ['-la']);""",
            language="javascript",
            tier=1,
            expected_severity=Severity.SAFE,
            description="Hardcoded binary + array args = SAFE"
        ),
        TestCase(
            name="test_eval_direct",
            code="""const cmd = req.query.cmd;
eval(cmd);""",
            language="javascript",
            tier=1,
            expected_severity=Severity.CRITICAL,
            description="eval() with user input = CRITICAL"
        ),
    ]
    
    # ── TIER 2: MEDIUM (common real-world patterns) ──────────────────────────
    TIER_2_TESTS = [
        TestCase(
            name="test_spawn_user_input",
            code="""const input = req.query.file;
require('child_process').spawn('cat', [input]);""",
            language="javascript",
            tier=2,
            expected_severity=Severity.HIGH,
            description="User-controlled argument = HIGH RISK"
        ),
        TestCase(
            name="test_env_injection",
            code="""const env = { ...process.env, LD_PRELOAD: req.query.lib };
spawn('node', ['app.js'], { env });""",
            language="javascript",
            tier=2,
            expected_severity=Severity.CRITICAL,
            description="Execution-influencing env var from user input = CRITICAL"
        ),
        TestCase(
            name="test_safe_env_static",
            code="""spawn('node', ['app.js'], { env: process.env });""",
            language="javascript",
            tier=2,
            expected_severity=Severity.SAFE,
            description="Hardcoded env vars = SAFE"
        ),
    ]
    
    # ── TIER 3: HARD (where models usually fail) ────────────────────────────
    TIER_3_TESTS = [
        TestCase(
            name="test_indirect_flow",
            code="""const a = req.query.cmd;
const b = a;
const c = b;
eval(c);""",
            language="javascript",
            tier=3,
            expected_severity=Severity.CRITICAL,
            description="Indirect data flow to eval() = CRITICAL"
        ),
        TestCase(
            name="test_encoded_input",
            code="""const cmd = decodeURIComponent(req.query.cmd);
eval(cmd);""",
            language="javascript",
            tier=3,
            expected_severity=Severity.CRITICAL,
            description="Decoded user input to eval() = CRITICAL"
        ),
        TestCase(
            name="test_false_positive_subprocess",
            code="""spawn('/bin/echo', ['hello']);""",
            language="javascript",
            tier=3,
            expected_severity=Severity.SAFE,
            description="Hardcoded binary + hardcoded args = SAFE (no false positive)"
        ),
        TestCase(
            name="test_shell_true",
            code="""spawn(`ls ${req.query.dir}`, { shell: true });""",
            language="javascript",
            tier=3,
            expected_severity=Severity.CRITICAL,
            description="Template string with user input + shell=true = CRITICAL"
        ),
    ]
    
    # ── TIER 4: ADVERSARIAL / EDGE CASES ────────────────────────────────────
    TIER_4_TESTS = [
        TestCase(
            name="test_path_control",
            code="""const bin = req.query.bin;
spawn(bin, ['--help']);""",
            language="javascript",
            tier=4,
            expected_severity=Severity.CRITICAL,
            description="User-controlled binary = CRITICAL"
        ),
        TestCase(
            name="test_mixed_safe",
            code="""const safe = "ls";
spawn(safe, ['-la']);""",
            language="javascript",
            tier=4,
            expected_severity=Severity.SAFE,
            description="Hardcoded string assigned to variable = SAFE"
        ),
        TestCase(
            name="test_partial_control",
            code="""const arg = req.query.arg;
spawn('/bin/ls', [arg]);""",
            language="javascript",
            tier=4,
            expected_severity=Severity.HIGH,
            description="User-controlled argument to safe binary = HIGH"
        ),
    ]
    
    @staticmethod
    def get_all_tests() -> List[TestCase]:
        """Return all test cases organized by tier."""
        return (
            AdversarialSanityTests.TIER_1_TESTS +
            AdversarialSanityTests.TIER_2_TESTS +
            AdversarialSanityTests.TIER_3_TESTS +
            AdversarialSanityTests.TIER_4_TESTS
        )
    
    @staticmethod
    def analyze_ast(code: str, language: str) -> Severity:
        """
        Analyze code using AST-based heuristics.
        Returns severity based on exploitability patterns.
        """
        # Check for user-controlled input patterns
        user_input_patterns = [
            r'req\.',
            r'request\.',
            r'params\.',
            r'query\.',
            r'body\.',
            r'userInput',
            r'decodeURIComponent\s*\(',
        ]
        
        has_user_input = any(re.search(pattern, code) for pattern in user_input_patterns)
        
        # Check for sensitive sinks
        eval_pattern = r'eval\s*\('
        exec_pattern = r'exec\s*\('
        spawn_pattern = r'spawn\s*\('
        shell_true_pattern = r'shell\s*:\s*true'
        env_injection_pattern = r'(?:LD_PRELOAD|BASH_ENV|ZDOTDIR|PYTHONPATH|NODE_OPTIONS)'
        
        has_eval = re.search(eval_pattern, code)
        has_exec = re.search(exec_pattern, code)
        has_spawn = re.search(spawn_pattern, code)
        has_shell_true = re.search(shell_true_pattern, code)
        has_env_injection = re.search(env_injection_pattern, code)
        
        # Check for user-controlled binary (first argument to spawn)
        user_controlled_binary = re.search(r'spawn\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)', code)
        
        # Check for variable assignment from user input followed by spawn
        # Pattern: const/let/var X = req.Y; ... spawn(X, ...)
        var_from_user = re.search(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)', code)
        if var_from_user:
            var_name = var_from_user.group(1)
            if re.search(rf'spawn\s*\(\s*{var_name}\s*[,\)]', code):
                user_controlled_binary = True
        
        # Scoring logic
        if has_user_input:
            # User-controlled binary is CRITICAL
            if user_controlled_binary:
                return Severity.CRITICAL
            
            if has_eval or has_exec:
                return Severity.CRITICAL
            if has_env_injection:
                return Severity.CRITICAL
            if has_shell_true:
                return Severity.CRITICAL
            if has_spawn:
                return Severity.HIGH
        
        # Check for shell=true with template strings (user input indicator)
        if has_shell_true and re.search(r'\$\{.*\}', code):
            return Severity.CRITICAL
        
        # Safe patterns
        if has_spawn and not has_user_input:
            return Severity.SAFE
        
        return Severity.SAFE
    
    @staticmethod
    def calculate_confidence(ast_result: Severity, llm_result: Severity, expected: Severity) -> Tuple[int, str]:
        """
        Calculate confidence score based on agreement between AST and LLM.
        
        100: Both agree with expected
        70: AST confirms exploit but LLM says safe (LLM miss)
        30: LLM flags but AST finds no path (possible false positive)
        0: Both agree it's safe
        """
        ast_matches = ast_result == expected
        llm_matches = llm_result == expected
        
        if ast_matches and llm_matches:
            return 100, "AST and LLM both confirm"
        
        if ast_result == Severity.CRITICAL and llm_result == Severity.SAFE:
            return 70, "AST confirms exploit but LLM says safe (possible LLM miss)"
        
        if llm_result != Severity.SAFE and ast_result == Severity.SAFE:
            return 30, "LLM flags issue but AST finds no user-controlled path"
        
        if ast_result == Severity.SAFE and llm_result == Severity.SAFE:
            return 0, "Both agree it's safe"
        
        return 50, "Partial agreement"

def run_internal_sanity_tests(llm_analyzer_func=None) -> Tuple[List[TestResult], bool]:
    """
    Run full adversarial sanity test suite.
    
    Args:
        llm_analyzer_func: Function that takes code and returns Severity
        
    Returns:
        (test_results, all_passed)
    """
    tests = AdversarialSanityTests.get_all_tests()
    results = []
    
    print("\n" + "="*80)
    print("[TEST] TREPAN ADVERSARIAL SANITY TEST SUITE")
    print("="*80)
    
    for test in tests:
        # Get AST result
        ast_result = AdversarialSanityTests.analyze_ast(test.code, test.language)
        
        # Get LLM result (if analyzer provided)
        if llm_analyzer_func:
            llm_result = llm_analyzer_func(test.code)
        else:
            llm_result = ast_result  # Fallback to AST if no LLM
        
        # Calculate confidence
        confidence, reason = AdversarialSanityTests.calculate_confidence(
            ast_result, llm_result, test.expected_severity
        )
        
        # Determine if test passed
        # Test passes if final result matches expected
        final_result = llm_result if llm_analyzer_func else ast_result
        passed = final_result == test.expected_severity
        
        result = TestResult(
            test_name=test.name,
            expected=test.expected_severity,
            ast_result=ast_result,
            llm_result=llm_result,
            final_result=final_result,
            confidence=confidence,
            passed=passed,
            reason=reason
        )
        results.append(result)
        
        # Print result
        status = "[PASS]" if passed else "[FAIL]"
        print(f"\n[TIER {test.tier}] {test.name}")
        print(f"  Description: {test.description}")
        print(f"  Expected: {test.expected_severity.name}")
        print(f"  AST: {ast_result.name}")
        print(f"  LLM: {llm_result.name}")
        print(f"  Final: {final_result.name}")
        print(f"  Confidence: {confidence}%")
        print(f"  {status} -- {reason}")
    
    # Check for critical failures
    critical_failures = []
    
    # Rule 1: eval test must NOT be marked SAFE
    eval_test = next((r for r in results if r.test_name == "test_eval_direct"), None)
    if eval_test and eval_test.final_result == Severity.SAFE:
        critical_failures.append("[FAIL] eval() test marked SAFE -- CRITICAL FAILURE")
    
    # Rule 2: shell:true test must be CRITICAL
    shell_test = next((r for r in results if r.test_name == "test_shell_true"), None)
    if shell_test and shell_test.final_result != Severity.CRITICAL:
        critical_failures.append("[FAIL] shell:true test not CRITICAL -- CRITICAL FAILURE")
    
    # Rule 3: safe subprocess must NOT be flagged
    safe_subprocess_test = next((r for r in results if r.test_name == "test_false_positive_subprocess"), None)
    if safe_subprocess_test and safe_subprocess_test.final_result != Severity.SAFE:
        critical_failures.append("[FAIL] safe subprocess flagged -- CRITICAL FAILURE")
    
    # Rule 4: safe static test must be SAFE
    safe_static_test = next((r for r in results if r.test_name == "test_safe_static"), None)
    if safe_static_test and safe_static_test.final_result != Severity.SAFE:
        critical_failures.append("[FAIL] safe static test not SAFE -- CRITICAL FAILURE")
    
    # Summary
    print("\n" + "="*80)
    print("[SUMMARY] TEST SUMMARY")
    print("="*80)
    
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if critical_failures:
        print("\n[CRITICAL] CRITICAL FAILURES:")
        for failure in critical_failures:
            print(f"  {failure}")
        all_passed = False
    else:
        print("\n[PASS] All critical checks passed!")
        all_passed = failed == 0
    
    print("="*80 + "\n")
    
    return results, all_passed and len(critical_failures) == 0
