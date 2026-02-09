# AGENTS.md - 산돌이 카카오톡 챗봇 서비스

## 프로젝트 개요

**산돌이 프로젝트**의 **카카오톡 챗봇 서버**입니다.
- FastAPI + SQLAlchemy + SQLite 기반의 API 서버
- 카카오톡 Open Builder와 연동되어 사용자 메시지를 처리
- `kakao-chatbot` 패키지를 사용하여 카카오톡 규격에 맞는 요청/응답 처리
- Keycloak을 통한 사용자 인증 (auth-relay 연동)

### 핵심 동작 방식
1. 카카오톡 Open Builder가 POST 요청으로 사용자 메시지 정보 전달
2. 서버는 **반드시 200 Response**로 JSON 응답 반환 (400/500 등은 무시됨)
3. 에러 발생 시에도 200으로 `KakaoError` 형식으로 반환해야 함

---

## Build / Lint / Test Commands

```bash
# 의존성 설치 (uv 사용)
uv sync

# 린트 및 포맷팅
uv run ruff check .                    # 린트 검사
uv run ruff check . --fix              # 린트 자동 수정
uv run ruff format .                   # 코드 포맷팅
uv run black .                         # Black 포맷팅

# 타입 체크
uv run mypy .                          # 전체 타입 체크
uv run mypy app/routers/meal.py        # 단일 파일 타입 체크

# 로컬 서버 실행
uv run uvicorn main:app --host 0.0.0.0 --port 5600 --reload

# Docker 실행
docker compose up -d                   # 전체 서비스 실행
docker compose up -d --build           # 환경 변수 변경 후 재빌드
docker compose down                    # 서비스 중지

# 데이터베이스 마이그레이션
uv run alembic upgrade head            # 마이그레이션 적용
uv run alembic revision --autogenerate -m "message"  # 마이그레이션 생성
```

> **Note**: 테스트 파일이 현재 없음. 테스트 추가 시 `pytest` 사용 권장.

---

## 코드 스타일 가이드라인

### Python 버전
- **Python 3.11** (>=3.11, <3.12)

### Import 순서 (Ruff/isort 규칙)
1. 표준 라이브러리 (`datetime`, `typing`, `asyncio` 등)
2. 서드파티 라이브러리 (`fastapi`, `httpx`, `sqlalchemy` 등)
3. 로컬 모듈 (`app.config`, `app.routers`, `app.services` 등)

```python
# 예시
import asyncio
from typing import Annotated, List

from fastapi import Depends, APIRouter
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse

from app.config import Config, logger
from app.services.meal_service import fetch_latest_meals
from app.utils.kakao import parse_payload
```

### 포맷팅 규칙
- **Line length**: 88자 (Black 기본값)
- **Indent**: 4 spaces
- **Quote style**: Double quotes (`"`)
- **Docstring convention**: Google style

### 타입 힌팅
- **필수**: 모든 함수 인자와 반환값에 타입 힌트 사용
- FastAPI Depends는 `Annotated[Type, Depends(...)]` 형식 사용

```python
async def meal_view(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
) -> JSONResponse:
```

### 네이밍 컨벤션
- **함수/변수**: `snake_case`
- **클래스**: `PascalCase`
- **상수**: `UPPER_SNAKE_CASE`
- **Enum**: `PascalCase` (멤버는 `snake_case`)
- **Router prefix**: `/{feature}` (예: `/meal`, `/users`)
- **API 함수명**: `{action}_{resource}` (예: `meal_view`, `get_login_link`)

### 파일 구조
```
app/
├── config/         # 설정 및 상수 (Config, BlockID, logger)
├── models/         # SQLAlchemy 모델 (ORM)
├── routers/        # FastAPI 라우터 (API 엔드포인트)
├── schemas/        # Pydantic 모델 (요청/응답 스키마)
├── services/       # 비즈니스 로직 (외부 API 호출 등)
└── utils/          # 유틸리티 함수
```

---

## 에러 처리 패턴

### KakaoError (핵심 패턴)
카카오톡은 200 외의 응답을 무시하므로, 에러도 200으로 반환해야 합니다.

```python
from app.utils.kakao import KakaoError

# 문자열 메시지로 에러 반환
raise KakaoError("등록된 식당이 없습니다.")

# KakaoResponse 객체로 에러 반환
response = KakaoResponse().add_component(SimpleTextComponent("에러 메시지"))
raise KakaoError(response)
```

### 인증 관련 에러
```python
from app.utils.kakao import NotAuthorizedError, LoginRequiredError

# 사용자 미등록 시
raise NotAuthorizedError()

# 토큰 만료/갱신 필요 시
raise LoginRequiredError(message="다시 로그인해주세요.")
```

### 일반 예외 처리
- `main.py`의 전역 exception handler가 모든 예외를 `KakaoResponse` 형식으로 변환
- `Config.debug`가 True일 경우 traceback 포함

---

## API 엔드포인트 패턴

### 기본 구조
```python
@meal_router.post(
    "/view",
    openapi_extra=create_openapi_extra(
        detail_params={"Cafeteria": {"origin": "미가", "value": "미가식당"}},
        utterance="학식 미가",
    ),
)
async def meal_view(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
) -> JSONResponse:
    """식단 정보를 반환합니다.
    
    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 발화
    - OpenBuilder: 블럭: "학식 보기", 스킬: "학식 보기"
    - Params: detail_params.Cafeteria(식당 이름)
    ---
    """
    logger.info("식단 정보 조회 요청: kakao_id=%s", payload.user_request.user.id)
    # ... 비즈니스 로직 ...
    return JSONResponse(response.get_dict())
```

### 응답 패턴
```python
# 기본 응답
response = KakaoResponse()
response.add_component(SimpleTextComponent("텍스트 메시지"))
return JSONResponse(response.get_dict())

# 퀵리플라이 추가
response.add_quick_reply(label="확인", action="message", message_text="확인")

# 블록 연결 퀵리플라이
response.add_quick_reply(
    label="로그인",
    action=ActionEnum.BLOCK,
    block_id=BlockID.LOGIN,
)
```

---

## 로깅 가이드

```python
from app.config import logger

# 레벨별 사용
logger.debug("상세 디버깅 정보: %s", data)      # 개발 시에만
logger.info("정상 동작 로그: kakao_id=%s", id)   # 주요 이벤트
logger.warning("경고: 데이터 없음")              # 비정상이지만 처리 가능
logger.error("에러 발생: %s", exc, exc_info=True) # 에러 (traceback 포함)
```

---

## 주요 의존성

| 패키지 | 용도 |
|--------|------|
| `kakao-chatbot` | 카카오톡 요청/응답 규격 처리 |
| `httpx` | 비동기 HTTP 클라이언트 (외부 서비스 호출) |
| `python-keycloak` | Keycloak 인증 연동 |
| `SQLAlchemy` | ORM (비동기, aiosqlite) |
| `alembic` | 데이터베이스 마이그레이션 |

---

## Ruff 린트 규칙

`pyproject.toml`에 정의된 규칙:
- **활성화**: E, F, W, C, D, R, B, N, S, PL
- **무시**: E203, E501 (line too long), D415, D403

```bash
# 린트 검사
uv run ruff check .

# 자동 수정
uv run ruff check . --fix
```

---

## 환경 변수 (`.env`)

```env
DEBUG=False
BASE_URL=https://sandol.sio2.kr/kakao-bot
KC_SERVER_URL=https://sandol.sio2.kr/auth/
DATABASE_URL=sqlite+aiosqlite:///./kakao_bot_service.db
AUTH_RELAY_URL=http://auth-relay:8000/relay
MEAL_SERVICE_URL=http://meal-service:80/meal
STATIC_INFO_SERVICE_URL=http://static-info-service:80/static-info
NOTICE_SERVICE_URL=http://notice-notification:3000/notice-notification
CLASSROOM_TIMETABLE_SERVICE_URL=http://classroom-timetable-service:80/classroom-timetable
TOKEN_ENCRYPTION_KEY=***
KC_CLIENT_SECRET=***
```

---

## 주의사항

1. **카카오톡 응답은 반드시 200**: 400/500 에러를 반환하면 사용자에게 전달되지 않음
2. **KakaoError 사용**: 의도적인 에러 메시지는 `KakaoError`를 통해 반환
3. **타입 안전성**: `as any`, `@ts-ignore` 등 타입 무시 금지 (Python에서는 `type: ignore` 금지)
4. **로깅 필수**: 모든 API 엔드포인트 시작/종료 시 로깅
5. **Context 보존**: `deepcopy(payload.contexts)` 사용하여 Context 수정 시 원본 보호
