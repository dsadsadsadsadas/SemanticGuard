"""
Test Security file - should trigger Security Mode
"""

def validate_password(password: str) -> bool:
    """Validate password strength."""
    return len(password) >= 8
