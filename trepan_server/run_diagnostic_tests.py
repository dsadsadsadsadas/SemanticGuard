import unittest
import sys
import os

# Ensure the current directory is in the path
sys.path.insert(0, os.getcwd())

from test_sink_registry import TestSinkRegistry

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSinkRegistry)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    
    if not result.wasSuccessful():
        print("\n--- DETAILED ERRORS ---")
        for failure in result.failures:
            print(f"FAILURE: {failure[0]}")
            print(failure[1])
        for error in result.errors:
            print(f"ERROR: {error[0]}")
            print(error[1])
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)
