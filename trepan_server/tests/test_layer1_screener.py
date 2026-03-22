import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from trepan_server.engine.layer1.screener import screen

class TestLayer1Screener(unittest.TestCase):

    # ── L1-001: Hardcoded Secrets ────────────────────────────────────────
    def test_hardcoded_api_key_rejected(self):
        code = 'api_key = "sk-abc123secretkey999"'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-001" for v in result.violations))

    def test_literal_string_not_secret(self):
        code = 'name = "John Doe"'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")

    # ── L1-002: Eval With Input ──────────────────────────────────────────
    def test_eval_with_user_input_rejected(self):
        code = 'result = eval(request.body)'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-002" for v in result.violations))

    def test_eval_with_literal_accepted(self):
        code = 'result = eval("2 + 2")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")

    # ── L1-003: Shell Injection ──────────────────────────────────────────
    def test_subprocess_shell_true_rejected(self):
        code = 'subprocess.run(cmd, shell=True)'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-003" for v in result.violations))

    def test_subprocess_no_shell_accepted(self):
        code = 'subprocess.run(["ls", "-la"])'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")

    # ── L1-005: Console Log With Request Data ────────────────────────────
    def test_console_log_request_rejected(self):
        code = 'console.log(req.body.password)'
        result = screen(code, ".js")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-005" for v in result.violations))

    def test_console_log_literal_accepted(self):
        code = 'console.log("Server started")'
        result = screen(code, ".js")
        self.assertEqual(result.verdict, "ACCEPT")

    # ── L1-006: Print With Request Data ─────────────────────────────────
    def test_print_with_password_rejected(self):
        code = 'print(f"Login: {password}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    # ── L1-007: Error Stack Exposed ──────────────────────────────────────
    def test_error_stack_in_response_rejected(self):
        code = 'res.json({message: err.stack})'
        result = screen(code, ".js")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-007" for v in result.violations))

    # ── L1-009: Assert for Security ──────────────────────────────────────
    def test_assert_for_security_flagged(self):
        code = 'assert user.is_admin, "Not authorized"'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-009" for v in result.violations))

    # ── L1-010: Bare Except ──────────────────────────────────────────────
    def test_bare_except_flagged(self):
        code = "try:\n    do_something()\nexcept:\n    pass"
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-010" for v in result.violations))

    # ── Performance ──────────────────────────────────────────────────────
    def test_layer1_runs_fast(self):
        import time
        code = "\n".join([f"x_{i} = {i}" for i in range(200)])
        t = time.perf_counter()
        result = screen(code, ".py")
        elapsed = time.perf_counter() - t
        self.assertLess(elapsed, 0.1)  # Must complete in under 100ms
        self.assertEqual(result.verdict, "ACCEPT")

    # ── Multi-violation ──────────────────────────────────────────────────
    def test_multiple_violations_detected(self):
        code = (
            'api_key = "sk-secret123abc"\n'
            'subprocess.run(cmd, shell=True)\n'
            'print(f"Password: {password}")\n'
        )
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertGreaterEqual(len(result.violations), 2)

    def test_clean_code_accepted(self):
        code = (
            "def calculate_total(items):\n"
            "    return sum(item.price for item in items)\n"
        )
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")

unittest.main(verbosity=2, exit=False) if __name__ == "__main__" else None
