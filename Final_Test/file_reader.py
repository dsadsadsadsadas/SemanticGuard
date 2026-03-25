# File Reader Service
def read_user_file(filename):
    # VULNERABLE: Path Traversal - no validation
    with open(filename, 'r') as f:
        return f.read()

def download_file(file_path):
    # VULNERABLE: Direct user input to file system
    with open(file_path, 'rb') as f:
        return f.read()
