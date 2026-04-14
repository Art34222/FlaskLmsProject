import base64
import io

import pyotp
import qrcode
from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def generate_otp_secret() -> str:
    """Генерирует новый секрет для TOTP."""
    return pyotp.random_base32()


def get_totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret)


def verify_otp(secret: str, code: str) -> bool:
    """Проверяет 6-значный код из Google Authenticator."""
    return get_totp(secret).verify(code)


def generate_qr_base64(secret: str, email: str) -> str:
    """Возвращает QR-код для Google Authenticator как base64-строку для <img>."""
    uri = get_totp(secret).provisioning_uri(name=email, issuer_name="EduOnline")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
