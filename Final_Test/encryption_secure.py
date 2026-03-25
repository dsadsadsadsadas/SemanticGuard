# Secure Encryption Module
import os
import base64
from cryptography.fernet import Fernet
from typing import Optional

class EncryptionManager:
    """Singleton encryption manager with validated Fernet key from environment"""
    _instance: Optional['EncryptionManager'] = None
    _key: Optional[bytes] = None
    _fernet: Optional[Fernet] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_key()
        return cls._instance
    
    def _initialize_key(self):
        """Initialize and validate encryption key from environment (called once)"""
        key_str = os.getenv('ENCRYPTION_KEY')
        
        if not key_str:
            raise ValueError(
                "ENCRYPTION_KEY not found in environment. "
                "Set it using: export ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
            )
        
        # Validate key format (must be valid base64 and 32 bytes when decoded)
        try:
            key_bytes = key_str.encode() if isinstance(key_str, str) else key_str
            decoded = base64.urlsafe_b64decode(key_bytes)
            
            if len(decoded) != 32:
                raise ValueError(
                    f"ENCRYPTION_KEY must be exactly 32 bytes when base64 decoded. "
                    f"Got {len(decoded)} bytes. Generate a valid key using Fernet.generate_key()"
                )
            
            self._key = key_bytes
            self._fernet = Fernet(self._key)
            
        except Exception as e:
            raise ValueError(
                f"Invalid ENCRYPTION_KEY format: {str(e)}. "
                f"Key must be a valid Fernet key (base64-encoded 32 bytes)"
            )
    
    @property
    def fernet(self) -> Fernet:
        """Get the Fernet cipher instance"""
        return self._fernet

def encrypt_data(data: str) -> bytes:
    """Encrypt data using key from environment (validated once via Singleton)"""
    manager = EncryptionManager()
    return manager.fernet.encrypt(data.encode())

def decrypt_data(encrypted: bytes) -> str:
    """Decrypt data using key from environment (validated once via Singleton)"""
    manager = EncryptionManager()
    return manager.fernet.decrypt(encrypted).decode()
