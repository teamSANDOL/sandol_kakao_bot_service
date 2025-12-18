# app/utils/security.py
import os
from cryptography.fernet import Fernet
from app.config import logger
from cryptography.fernet import InvalidToken

# 환경변수에서 직접 로드
ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    logger.error("TOKEN_ENCRYPTION_KEY가 설정되지 않았습니다!")
    raise ValueError("Encryption key not set")

fernet = Fernet(ENCRYPTION_KEY.encode("utf-8"))


def encrypt_token(token: str) -> str:
    """토큰을 암호화합니다."""
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """암호화된 토큰을 복호화합니다. 실패/변조 감지 시 적절히 로깅하고 예외를 발생시킵니다."""
    if not encrypted_token:
        logger.error("decrypt_token: encrypted_token이 비어 있거나 None입니다.")
        raise ValueError("Encrypted token is required")

    try:
        # 지역 임포트로 InvalidToken을 잡습니다.

        return fernet.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning(
            "decrypt_token: 토큰 복호화 실패 - 변조되었거나 유효하지 않은 토큰입니다."
        )
        raise ValueError("Invalid or tampered token")
    except Exception as exc:
        logger.error(
            "decrypt_token: 토큰 복호화 중 예기치 못한 오류가 발생했습니다.",
            exc_info=True,
        )
        # 내부 예외를 보존하여 호출자가 원인 파악 가능하도록 합니다.
        raise RuntimeError("Decryption failed") from exc
