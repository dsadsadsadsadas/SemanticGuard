# Secure LDAP Authentication
import ldap
import ldap.filter

def authenticate_ldap(username: str, password: str) -> bool:
    """Authenticate with LDAP injection protection"""
    conn = ldap.initialize('ldap://ldap.example.com')
    
    # SECURE: Escape LDAP special characters
    safe_username = ldap.filter.escape_filter_chars(username)
    search_filter = f"(&(uid={safe_username}))"
    
    try:
        conn.simple_bind_s(f"uid={safe_username},dc=example,dc=com", password)
        return True
    except ldap.INVALID_CREDENTIALS:
        return False
