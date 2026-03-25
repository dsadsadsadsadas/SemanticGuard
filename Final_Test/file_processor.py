# File Processing Utility
import os

def process_file(filename):
    # VULNERABLE: Command Injection
    os.system(f"cat {filename} | grep 'error'")
    
def compress_file(filepath):
    # VULNERABLE: Command Injection
    os.system(f"tar -czf {filepath}.tar.gz {filepath}")
