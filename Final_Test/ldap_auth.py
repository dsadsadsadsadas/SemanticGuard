# LDAP Authentication
import ldap

def authenticate_ldap(username, password):
    conn = ldap.initialize('ldap://ldap.example.com')
    # VULNERABLE: LDAP Injection
    search_filter = f"(&(uid={username})(userPassword={password}))"
    conn.search_s('dc=example,dc=com', ldap.SCOPE_SUBTREE, search_filter)
