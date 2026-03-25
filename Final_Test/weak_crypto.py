import hashlib
def hash_password(password):
    # VULNERABLE: Using obsolete MD5 algorithm for passwords
    return hashlib.md5(password.encode()).hexdigest()
