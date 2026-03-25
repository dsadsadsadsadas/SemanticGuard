# Secure Token Generator
import secrets
import string

def generate_reset_token() -> str:
    """Generate cryptographically secure reset token"""
    # SECURE: Using secrets module for cryptographic randomness
    return secrets.token_urlsafe(32)

def generate_session_id() -> str:
    """Generate secure session ID"""
    # SECURE: Cryptographically secure random
    return secrets.token_hex(16)

def generate_api_key() -> str:
    """Generate secure API key"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(40))
