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

# 핸들러 1: 파일에 모든 로그 저장 (디버깅용)
file_handler = logging.FileHandler(
    os.path.join(CONFIG_DIR, "app.log"), encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)  # DEBUG 이상 저장
file_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
file_handler.setFormatter(file_formatter)

# 핸들러 2: 콘솔에 INFO 이상만 출력 (간결한 버전)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # INFO 이상만 출력
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

# 로거에 핸들러 추가
logger.addHandler(file_handler)
logger.addHandler(console_handler)


class Config:
    """FastAPI 설정 값을 관리하는 클래스

    이 클래스는 환경 변수에서 설정 값을 로드하고, 기본 값을 제공합니다.
    또한, meal_types.json 파일에서 식사 유형을 불러오는 기능도 포함되어 있습니다.
    """

    debug = os.getenv("DEBUG", "False").lower() == "true"

    SERVICE_ID: str = os.getenv("SERVICE_ID", "4")

    USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
    MEAL_SERVICE_URL = os.getenv("MEAL_SERVICE_URL", "http://meal-service:8000")
    DATABASE_URL = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./kakao_bot_service.db"
    )

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
