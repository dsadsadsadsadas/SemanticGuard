# Token Generator
import random
import string

def generate_reset_token():
    # VULNERABLE: Using random instead of secrets
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

def generate_session_id():
    # VULNERABLE: Predictable random
    return str(random.randint(100000, 999999))
