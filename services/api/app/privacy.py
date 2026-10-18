import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.credential_encryption_key
    if not key:
        digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt_private(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_private(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("敏感数据无法解密，请检查加密密钥") from exc


def mask_name(value: str) -> str:
    if len(value) <= 1:
        return "*"
    return f"{value[0]}{'*' * (len(value) - 1)}"


def mask_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def mask_address(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:8]}***"

