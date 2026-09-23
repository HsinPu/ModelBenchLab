import os
from pathlib import Path
from cryptography.fernet import Fernet

def cipher():
    key = os.getenv('APP_ENCRYPTION_KEY')
    if not key:
        if os.getenv('APP_ENV') == 'production':
            raise RuntimeError('APP_ENCRYPTION_KEY is required in production')
        path = Path('.local-key')
        try:
            with path.open('xb') as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        key = path.read_bytes()
    return Fernet(key)

def encrypt(value):
    return cipher().encrypt(value.encode()).decode() if value else ''

def decrypt(value):
    return cipher().decrypt(value.encode()).decode() if value else ''
