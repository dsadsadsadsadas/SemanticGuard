
import sys
import os

# Add parent directory to path to import trepan
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import trepan
    print("Successfully imported trepan.")
    if hasattr(trepan, 'self_diagnostic'):
        trepan.self_diagnostic()
    else:
        print("Error: self_diagnostic function not found in trepan module.")
except ImportError as e:
    print(f"Error importing trepan: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
