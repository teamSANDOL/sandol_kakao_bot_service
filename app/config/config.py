"""FastAPI 앱의 설정을 정의하는 모듈입니다.

이 모듈은 환경 변수를 로드하고, 로깅을 설정하며, FastAPI 애플리케이션의 설정 값을 관리하는 Config 클래스를 제공합니다.
또한, meal_types.json 파일에서 식사 유형을 불러오는 기능도 포함되어 있습니다.
"""

import os
import logging
from dotenv import load_dotenv
from pytz import timezone


# 환경 변수 로딩
load_dotenv()

CONFIG_DIR = os.path.dirname(__file__)
DEFAULT_CACHE_DIR = os.path.abspath(os.path.join(CONFIG_DIR, "..", "..", ".cache"))
CACHE_DIR = os.getenv("CACHE_DIR", DEFAULT_CACHE_DIR)

# 로깅 설정
logger = logging.getLogger("sandol_kakao_bot_service")
logger.setLevel(logging.DEBUG)  # 모든 로그 기록

console_handler = logging.StreamHandler()
if os.getenv("DEBUG", "False").lower() == "true":
    console_handler.setLevel(logging.DEBUG)  # DEBUG 이상 출력
else:
    # DEBUG 모드가 아닐 때는 INFO 이상만 출력
    console_handler.setLevel(logging.INFO)  # INFO 이상만 출력
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

logger.addHandler(console_handler)


class Config:
    """FastAPI 설정 값을 관리하는 클래스입니다.

    이 클래스는 환경 변수에서 설정 값을 로드하고, 기본 값을 제공합니다.
    또한, meal_types.json 파일에서 식사 유형을 불러오는 기능도 포함되어 있습니다.
    """

    debug = os.getenv("DEBUG", "False").lower() == "true"

    SERVICE_ID: str = os.getenv("SERVICE_ID", "4")
    SERVICE_ACCOUNT_SUB: str | None = os.getenv("SERVICE_ACCOUNT_SUB")
    SERVICE_ACCOUNT_TOKEN: str | None = os.getenv("SERVICE_ACCOUNT_TOKEN")
    SERVICE_ACCOUNT_TOKEN_TYPE: str = os.getenv("SERVICE_ACCOUNT_TOKEN_TYPE", "Bearer")

    BASE_URL = os.getenv("BASE_URL", "https://sandol.sio2.kr/kakao-bot").rstrip("/")

    DATABASE_URL = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./kakao_bot_service.db"
    )
    USER_SERVICE_URL = os.getenv(
        "USER_SERVICE_URL", "http://user-service:8000/user"
    ).rstrip("/")
    MEAL_SERVICE_URL = os.getenv(
        "MEAL_SERVICE_URL", "http://meal-service:80/meal"
    ).rstrip("/")
    STATIC_INFO_SERVICE_URL = os.getenv(
        "STATIC_INFO_SERVICE_URL", "http://static-info-service:80/static-info"
    ).rstrip("/")
    NOTICE_SERVICE_URL = os.getenv(
        "NOTICE_SERVICE_URL", "http://notice-notification:8081/notice-notification"
    ).rstrip("/")
    CLASSROOM_TIMETABLE_SERVICE_URL = os.getenv(
        "CLASSROOM_TIMETABLE_SERVICE_URL",
        "http://classroom-timetable-service:80/classroom-timetable",
    ).rstrip("/")
    AUTH_RELAY_URL = os.getenv("AUTH_RELAY_URL", "http://auth-relay:8000/relay").rstrip(
        "/"
    )
    LOGIN_CALLBACK_URL = os.getenv("LOGIN_CALLBACK_URL", f"{BASE_URL}/users/callback")
    LOGIN_REDIRECT_AFTER = os.getenv("LOGIN_REDIRECT_AFTER")

    KC_SERVER_URL = (
        os.getenv("KC_SERVER_URL", "https://sandol.sio2.kr/auth/").rstrip("/") + "/"
    )
    KC_CLIENT_ID = os.getenv("KC_CLIENT_ID", "sandol-kakao-bot")
    KC_REALM = os.getenv("KC_REALM", "Sandori")
    KC_CLIENT_SECRET = os.getenv("KC_CLIENT_SECRET")
    if not KC_CLIENT_SECRET and not debug:
        raise RuntimeError(
            "KC_CLIENT_SECRET environment variable must be set when DEBUG is false."
        )

    TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
    TZ = timezone(TIMEZONE)

    RELAY_CLIENT_SECRETS = os.getenv("RELAY_CLIENT_SECRETS", "")
    if not debug and not RELAY_CLIENT_SECRETS:
        raise RuntimeError(
            "RELAY_CLIENT_SECRETS environment variable must be set and non-empty "
            "when DEBUG is false."
        )
    NONCE_TTL_SECONDS = int(os.getenv("NONCE_TTL_SECONDS", "300"))

    class HttpStatus:
        """HTTP 상태 코드를 정의하는 클래스입니다."""

        OK = 200
        CREATED = 201
        NO_CONTENT = 204
        BAD_REQUEST = 400
        UNAUTHORIZED = 401
        FORBIDDEN = 403
        NOT_FOUND = 404
        CONFLICT = 409
        INTERNAL_SERVER_ERROR = 500
        BAD_GATEWAY = 502
