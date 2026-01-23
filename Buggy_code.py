import os
from flask import request

# TODO: Fix this CRITICAL BUG before production
def download_file():
    filename = request.args.get('file')
    # VULNERABILITY: Path Traversal (User can download /etc/passwd)
    file_path = "/var/www/uploads/" + filename 
    
    with open(file_path, 'r') as f:
        return f.read()