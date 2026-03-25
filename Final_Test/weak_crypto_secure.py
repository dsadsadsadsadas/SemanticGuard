import hashlib
import os
def hash_password(password):
    # SAFE: Using secure PBKDF2 hash algorithm with salt
    salt = os.urandom(32)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
