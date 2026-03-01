# AGENTS.md - sandol_kakao_bot_service

## 목적
- 이 문서는 이 저장소에서 작업하는 코딩 에이전트를 위한 실행 가이드입니다.
- 목표는 기존 패턴을 유지하면서 FastAPI + Kakao 응답 규격을 안전하게 지키는 것입니다.

## 프로젝트 개요
- 산돌이 프로젝트의 카카오톡 챗봇 서버입니다.
- FastAPI + SQLAlchemy + SQLite(`.env` 기본값 기준) 기반 API 서버입니다.
- 카카오 OpenBuilder와 연동되며, `kakao-chatbot` 패키지로 요청/응답 스키마를 처리합니다.
- 인증은 Keycloak + auth-relay 흐름을 사용합니다.

### 핵심 동작 방식
1. OpenBuilder가 사용자 메시지 payload를 POST로 전달합니다.
2. 카카오 스킬 엔드포인트는 예외 상황에서도 사용자에게 보여줄 JSON 응답을 반환해야 합니다.
3. 의도된 실패는 `KakaoError` 계열로 처리하고 전역 핸들러에서 Kakao 응답으로 변환합니다.

## 프로젝트 핵심 맥락
- 카카오 OpenBuilder 연동 FastAPI 챗봇 서버입니다.
- 주요 스택: Python 3.11, FastAPI, SQLAlchemy Async, httpx, kakao-chatbot.
- 핵심 제약: 카카오 사용자 응답은 JSON으로 반환되어야 하며, 실패 케이스도 사용자에게 전달 가능한 형태를 유지해야 합니다.

## 실행/검증 명령어

### 의존성 설치
```bash
uv sync
```

### 로컬 서버 실행
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 5600 --reload
```

### 린트/포맷
```bash
uv run ruff check .
uv run ruff check . --fix
uv run ruff format .
uv run black .
```

### 타입 체크
```bash
uv run mypy .
uv run mypy app/routers/meal.py
```

### 테스트
- 현재 저장소에 테스트 파일이 없습니다.
- 테스트 추가 시 아래 패턴을 사용하세요.

```bash
uv run pytest
uv run pytest tests/test_example.py
uv run pytest tests/test_example.py::test_case_name
uv run pytest -k "keyword"
```

### DB 마이그레이션
```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"
```

### Docker
```bash
docker compose up -d
docker compose up -d --build
docker compose down
```

## 코드베이스 구조
```text
app/
  config/      # 설정, 블록 ID, 로거
  models/      # SQLAlchemy ORM 모델
  routers/     # FastAPI 엔드포인트
  schemas/     # Pydantic 스키마
  services/    # 비즈니스 로직 / 외부 서비스 호출
  utils/       # 카카오 응답, HTTP, 보안, 공용 유틸
main.py        # 앱 생성, 라우터 등록, 전역 예외 처리
```

## 코드 스타일 규칙

### Python/포맷
- Python: `>=3.11,<3.12`
- line length: 88
- indent: 4 spaces
- quote: double quote
- docstring: Google convention

### Import
- 표준 라이브러리 -> 서드파티 -> 로컬 모듈(`app.*`) 순서.
- OpenAPI 유틸은 `from app.utils import create_openapi_extra`를 우선 사용.

### 타입 힌트
- 함수 인자/리턴 타입을 명시합니다.
- FastAPI 의존성은 `Annotated[T, Depends(...)]` 패턴을 사용합니다.
- `get_current_user`, `select_restaurant`, `get_xuser_client_by_payload`도 같은 방식으로 주입합니다.
- `Any` 남용을 피하고 스키마 타입을 우선 사용합니다.

### 네이밍
- 함수/변수: `snake_case`
- 클래스/Enum: `PascalCase`
- 상수: `UPPER_SNAKE_CASE`
- 라우터 prefix는 기능 단위(`/meal`, `/users`, `/notice` 등)

## 라우터/응답 작성 규칙

### 기본 엔드포인트 형태
```python
@router.post("/path")
async def endpoint(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
) -> JSONResponse:
    response = KakaoResponse()
    response.add_component(SimpleTextComponent("..."))
    return JSONResponse(response.get_dict())
```

### OpenBuilder 연동
- 가능한 경우 `openapi_extra=create_openapi_extra(...)`를 사용해 샘플 payload를 문서화합니다.
- `detail_params`, `client_extra`, `contexts`를 실제 스킬 입력과 맞춥니다.
- `utterance`는 선택 파라미터이므로 필요한 경우만 명시합니다.

### Quick Reply
- 단순 발화 유도는 `action="message"` 사용.
- 블록 이동은 `ActionEnum.BLOCK` + `block_id` 사용.
- 블록 ID/퀵리플라이 헬퍼는 `app.config.blocks` 상수/함수를 우선 사용.

### Context 반영
- payload context 수정 전 `deepcopy(payload.contexts)`로 원본을 보존합니다.
- context 수정 후 응답에 `response.contexts = contexts`를 반드시 설정합니다.

## 에러 처리 규칙

### Kakao 친화 에러
- 사용자 의도 오류는 `KakaoError` 계열로 처리합니다.
- 인증 유도는 `NotAuthorizedError`, `LoginRequiredError`를 사용합니다.

### 전역 예외 처리
- `main.py` 전역 핸들러가 `KakaoError/NotAuthorizedError/LoginRequiredError`를 우선 처리합니다.
- 일반 예외는 로깅 후 `error_message(...)` 기반 Kakao 응답으로 변환됩니다.
- 카카오 스킬 엔드포인트는 사용자 단에서 4xx/5xx가 무시되므로, 사용자 노출 실패는 Kakao 응답 등을 활용하여 HTTP 200으로 반환합니다.
- 단, 내부 콜백/헬스체크 등 비-카카오 엔드포인트는 HTTP 상태코드 기반 응답을 사용할 수 있습니다.

### 예외 작성 원칙
- `except Exception`은 경계 지점에서만 사용하고 로그를 남깁니다.
- 빈 catch 금지.
- 에러 메시지/로그에 토큰, 시크릿, 개인정보를 남기지 않습니다.

## 로깅 규칙
- 공용 로거는 `app.config`의 logger를 사용합니다.
- 가능하면 엔드포인트 시작/종료에 `logger.info`를 남깁니다.
- 분기 추적은 `logger.debug`, 복구 가능한 이상은 `logger.warning`.
- 실패는 `logger.error(..., exc_info=True)` 또는 traceback 포함 형태로 기록합니다.
- 토큰/시크릿/개인식별자 원문 로그는 금지하고, 필요 시 마스킹된 값만 기록합니다.

## Ruff 규칙
- `pyproject.toml` 기준 lint 선택 규칙: `E, F, W, C, D, R, B, N, S, PL`
- ignore 규칙: `E203`, `E501`, `D415`, `D403`
- pydocstyle convention: `google`

## 주요 의존성
- `kakao-chatbot`: 카카오 요청/응답 규격 처리
- `fastapi`, `uvicorn`: API 서버
- `httpx`: 비동기 외부 호출
- `SQLAlchemy`, `aiosqlite`: 비동기 ORM/DB
- `alembic`: 마이그레이션
- `python-keycloak`, `pyjwt`, `cryptography`: 인증/토큰 처리

## 환경 변수 가이드
- 기준 파일: `.env.example`
- 핵심 항목: `BASE_URL`, `DATABASE_URL`, `AUTH_RELAY_URL`, `MEAL_SERVICE_URL`, `STATIC_INFO_SERVICE_URL`, `NOTICE_SERVICE_URL`, `CLASSROOM_TIMETABLE_SERVICE_URL`
- 인증/보안 항목: `KC_SERVER_URL`, `KC_CLIENT_ID`, `KC_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `RELAY_CLIENT_SECRETS`
- 운영 시크릿은 절대 하드코딩/로그 출력하지 않습니다.

## 인증/보안 작업 주의
- `app/services/auth_service.py`, `app/services/user_service.py`, `app/utils/security.py` 패턴을 우선 따릅니다.
- relay 서명/nonce/timestamp 검증 흐름을 임의 단순화하지 않습니다.
- 토큰 저장/복호화 로직 변경 시 민감정보 로그 노출 여부를 먼저 점검합니다.

## 에이전트 작업 체크리스트
- 변경 전: 관련 router/service/utils를 읽고 흐름 파악.
- 변경 중: `KakaoResponse().get_dict()` 기반 응답 포맷 유지.
- 변경 후: 최소 `ruff check`, 필요 시 `mypy`, 실행 영향 시 수동 시나리오 점검.
- 테스트 추가 시: `uv run pytest <file>::<test_name>` 형태의 단일 재현 경로를 문서화.

## Cursor / Copilot 규칙 반영
- `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`는 현재 저장소에서 확인되지 않았습니다.
- 이후 추가되면 이 문서에 우선순위/충돌 규칙을 즉시 반영하세요.

## 절대 금지
- 카카오 응답 스키마를 깨는 임의 JSON 반환.
- 응답 처리에서 `response.get_dict()` 누락.
- 타입/린트 경고를 무시하기 위한 주석성 우회.
- 인증/시크릿 데이터 하드코딩.
