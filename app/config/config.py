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

# 현재 파일이 위치한 디렉터리 (config 폴더의 절대 경로)
CONFIG_DIR = os.path.dirname(__file__)

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
    """FastAPI 설정 값을 관리하는 클래스

    이 클래스는 환경 변수에서 설정 값을 로드하고, 기본 값을 제공합니다.
    또한, meal_types.json 파일에서 식사 유형을 불러오는 기능도 포함되어 있습니다.
    """

    debug = os.getenv("DEBUG", "False").lower() == "true"

    SERVICE_ID: str = os.getenv("SERVICE_ID", "4")

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
    CLASSTROOM_TIMETABLE_SERVICE_URL = os.getenv(
        "CLASSTROOM_TIMETABLE_SERVICE_URL",
        "http://classroom-timetable-service:80/classroom-timetable",
    ).rstrip("/")

    TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
    TZ = timezone(TIMEZONE)

    class HttpStatus:
        """HTTP 상태 코드를 정의하는 클래스"""

        OK = 200
        CREATED = 201
        NO_CONTENT = 204
        BAD_REQUEST = 400
        UNAUTHORIZED = 401
        FORBIDDEN = 403
        NOT_FOUND = 404
        CONFLICT = 409
        INTERNAL_SERVER_ERROR = 500
