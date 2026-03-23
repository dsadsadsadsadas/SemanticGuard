"""
Test L1-006 rule refinement: Distinguish between diagnostic prints and actual data leaks.

The old rule flagged ALL print() calls with req.* as violations.
The new rule should only flag prints that expose SENSITIVE data (password, token, body, etc).

Diagnostic prints like print(f"[LOG] Processing {req.model_name}") should PASS.
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from trepan_server.engine.layer1.screener import screen

class TestL1006DiagnosticPrints(unittest.TestCase):

    # ── SHOULD REJECT: Actual sensitive data leaks ──────────────────────────
    def test_print_request_body_rejected(self):
        """Printing entire request body is a leak."""
        code = 'print(f"Request body: {req.body}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_password_rejected(self):
        """Printing password field is a leak."""
        code = 'print(f"User password: {req.password}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_token_rejected(self):
        """Printing auth token is a leak."""
        code = 'print(f"Token: {req.token}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_secret_rejected(self):
        """Printing secret is a leak."""
        code = 'print(f"Secret: {req.secret}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    # ── SHOULD ACCEPT: Diagnostic/logging prints ──────────────────────────
    def test_print_model_name_accepted(self):
        """Printing model name is diagnostic, not a leak."""
        code = 'print(f"[LOG] Using model: {req.model_name}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_filename_accepted(self):
        """Printing filename is diagnostic, not a leak."""
        code = 'print(f"[AUDIT] Processing file: {req.filename}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_request_id_accepted(self):
        """Printing request ID is diagnostic, not a leak."""
        code = 'print(f"[TRACE] Request ID: {req.request_id}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_method_accepted(self):
        """Printing HTTP method is diagnostic, not a leak."""
        code = 'print(f"[DEBUG] HTTP method: {req.method}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_status_accepted(self):
        """Printing status is diagnostic, not a leak."""
        code = 'print(f"[VAULT SYNC] Status: {req.status}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_processor_mode_accepted(self):
        """Printing processor mode is diagnostic, not a leak."""
        code = 'print(f"[CONFIG] Processor: {req.processor_mode}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_vault_path_accepted(self):
        """Printing vault path is diagnostic, not a leak."""
        code = 'print(f"[VAULT SYNC] Path: {req.vault_path}")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))

    # ── EDGE CASES ──────────────────────────────────────────────────────────
    def test_print_request_body_direct_rejected(self):
        """Printing request.body directly is a leak."""
        code = 'print(request.body)'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v.rule_id == "L1-006" for v in result.violations))

    def test_print_no_request_accepted(self):
        """Print without request data is safe."""
        code = 'print(f"[LOG] Processing complete")'
        result = screen(code, ".py")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertFalse(any(v.rule_id == "L1-006" for v in result.violations))


if __name__ == '__main__':
    unittest.main()
