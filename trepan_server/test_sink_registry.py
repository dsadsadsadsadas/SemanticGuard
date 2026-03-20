import ast
import json
import os
import unittest
try:
    from trepan_server import sink_registry
except ImportError:
    import sink_registry

class TestSinkRegistry(unittest.TestCase):
    def setUp(self):
        # Reset registry to defaults before each test
        if os.path.exists("sinks.config.json"):
            os.remove("sinks.config.json")
        sink_registry.load()

    def tearDown(self):
        if os.path.exists("sinks.config.json"):
            os.remove("sinks.config.json")

    def test_known_middleware(self):
        # errorHandler is a default middleware sink
        node = ast.parse("errorHandler(data)").body[0].value
        self.assertTrue(sink_registry.is_sink(node))

    def test_unknown_function(self):
        # random_func is not a sink
        node = ast.parse("random_func(data)").body[0].value
        self.assertFalse(sink_registry.is_sink(node))

    def test_decorator_sink(self):
        # @sanitized is a default decorator sink
        node = ast.Name(id="sanitized", ctx=ast.Load())
        self.assertTrue(sink_registry.is_sink(node))

    def test_pattern_sink(self):
        # .replace() is a default pattern sink
        node = ast.parse("data.replace('a', 'b')").body[0].value
        self.assertTrue(sink_registry.is_sink(node))
        
        # hashlib. is a default pattern sink
        node = ast.parse("hashlib.sha256(data)").body[0].value
        self.assertTrue(sink_registry.is_sink(node))

    def test_user_defined_sink(self):
        # Create a valid config file
        config = {
            "middleware": ["myCustomSanitizer"],
            "decorators": ["@my_decorator"],
            "patterns": [r"audit_log\("]
        }
        with open("sinks.config.json", "w") as f:
            json.dump(config, f)
        
        sink_registry.load("sinks.config.json")
        
        # Test custom middleware
        node = ast.parse("myCustomSanitizer(data)").body[0].value
        self.assertTrue(sink_registry.is_sink(node))
        
        # Test custom pattern
        node = ast.parse("audit_log(data)").body[0].value
        self.assertTrue(sink_registry.is_sink(node))

    def test_malformed_config_fallback(self):
        # Create a malformed config file
        with open("sinks.config.json", "w") as f:
            f.write("{ invalid json: ")
        
        # Should log a warning and fall back to defaults (no crash)
        sink_registry.load("sinks.config.json")
        
        # errorHandler (default) should still work
        node = ast.parse("errorHandler(data)").body[0].value
        self.assertTrue(sink_registry.is_sink(node))

if __name__ == "__main__":
    unittest.main()
