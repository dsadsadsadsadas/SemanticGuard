# Encryption Module
from cryptography.fernet import Fernet

ENCRYPTION_KEY = b'ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg='

def encrypt_data(data):
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(data.encode())

def decrypt_data(encrypted):
    f = Fernet(ENCRYPTION_KEY)
    return f.decrypt(encrypted).decode()
