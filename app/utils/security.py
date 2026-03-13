"""토큰 암복호화 보안 유틸리티를 제공합니다."""

from typing import cast

from cryptography.fernet import Fernet, InvalidToken

from app.config import Config, logger

fernet = Fernet(cast(str, Config.TOKEN_ENCRYPTION_KEY).encode("utf-8"))


def encrypt_token(token: str) -> str:
    """토큰을 암호화합니다."""
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """암호화된 토큰을 복호화합니다. 실패/변조 감지 시 적절히 로깅하고 예외를 발생시킵니다."""
    if not encrypted_token:
        logger.error("decrypt_token: encrypted_token이 비어 있거나 None입니다.")
        raise ValueError("Encrypted token is required")

    try:
        return fernet.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        logger.warning(
            "decrypt_token: 토큰 복호화 실패 - 변조되었거나 유효하지 않은 토큰입니다."
        )
        raise ValueError("Invalid or tampered token") from exc
    except Exception as exc:
        logger.error(
            "decrypt_token: 토큰 복호화 중 예기치 못한 오류가 발생했습니다.",
            exc_info=True,
        )
        # 내부 예외를 보존하여 호출자가 원인 파악 가능하도록 합니다.
        raise RuntimeError("Decryption failed") from exc
