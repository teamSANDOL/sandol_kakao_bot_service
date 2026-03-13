# 📌 산돌이 Repository Template

## 📂 개요

이 Repository는 **산돌이 프로젝트**의 **카카오톡 챗봇 서버** 코드 내용입니다.

이 서비스는 **Docker 컨테이너로 실행**되며, 이후 **Docker Compose를 활용하여 통합 운영**됩니다.

---

## 📌 프로젝트 구조

- FastAPI + SQLAlchemy + SQLite 기반의 API 서버
- 카카오톡 Open Builder의 설정을 통해 본 서버와 연동됩니다.

### 동작 방식

카카오톡 챗봇 서버의 작동 방식은 기본적으로 카카오톡의 Open Builder 서버가 POST 요청을 통해 사용자의 메시지 정보를 제공합니다.
이에 서버는 200 Response를 정해진 규격에 맞게 JSON형태로 반환해야 합니다.
이때, 주의할 점은 404, 500 등 200이 아닌 기타 Response는 전부 사용자에게 전달되지 않고 무시되므로 예외처리시 에러메시지까지 200으로 반환하는 것이 중요합니다.
따라서 에러는 별도로 처리방식을 서버단에서 강구해야 합니다.
본 서버는 `KakaoError`라는 별도 에러 처리 반환 형식을 통해 서버에서 발생하는 500에러를 Debug여부에 따라 별도로 분리 관리하도록 되어있습니다.

### 입력 및 반환형태

카카오톡의 Open Builder 서버가 POST 요청을 통해 사용자의 메시지 정보를 JSON으로 정해진 규격에 따라 제공하고,
서버는 200 Response를 정해진 규격에 맞게 JSON형태로 반환해야 합니다.
따라서 이를 간편하게 처리하기 위해, `kakao-chatbot` 패키지를 사용합니다.

### 사용자 정보 처리 및 인증

사용자 정보는 `tuk_sandol_team`프로젝트에서 공통적으로 `keycloak`을 통해 중앙관리되며, `auth-relay`를 통한 로그인 링크 발급 후 사용자가 별도 웹페이지로 로그인을 진행하면 사용자의 token을 서버에서 저장 및 사용합니다.
해당 token을 사용해 사용자 정보가 포함되어야 하는 작업을 처리합니다.

---

## 📌 문서

- **문서 링크**
  - [로컬 서버 Swagger UI](http://localhost:80/kakao-bot/docs)
  - http://localhost:80/kakao-bot/docs
- **서비스 관련 문서**
  - 카카오 OpenBuilder 가이드: [OpenBuilder 가이드](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format)

---

## 📌 환경 설정

- **모든 서비스는 Docker 기반으로 실행**되므로, `Docker`만 설치되어 있다면 로컬 환경에 별도로 의존하지 않음
- 환경 변수 파일 (`.env`) 필요
- `.env` / `.env.example`는 현재 아래와 같이 분야별로 정리되어 있음

  ```.env
  ### Runtime
  DEBUG=False
  TIMEZONE=Asia/Seoul

  ### App Base
  BASE_URL=https://sandol.sio2.kr/kakao-bot
  LOGIN_CALLBACK_URL=https://sandol.sio2.kr/kakao-bot/users/callback
  LOGIN_REDIRECT_AFTER=

  ### Database & Cache
  DATABASE_URL=sqlite+aiosqlite:///./kakao_bot_service.db
  CACHE_DIR=./.cache

  ### Internal Service URLs (MSA)
  AUTH_RELAY_URL=http://auth-relay:8000/relay
  MEAL_SERVICE_URL=http://meal-service:80/meal
  STATIC_INFO_SERVICE_URL=http://static-info-service:80/static-info
  NOTICE_SERVICE_URL=http://notice-notification:3000/notice-notification
  CLASSROOM_TIMETABLE_SERVICE_URL=http://classroom-timetable-service:80/classroom-timetable

  ### Keycloak
  KC_SERVER_URL=https://sandol.sio2.kr/auth/
  KC_CLIENT_ID=sandol-kakao-bot
  KC_REALM=Sandori
  KC_CLIENT_SECRET=*****

  ### Security
  TOKEN_ENCRYPTION_KEY=*****
  RELAY_CLIENT_SECRETS=dev-hmac-secret-please-change
  NONCE_TTL_SECONDS=300
  ```

### env 항목별 상세 설명

| NAME | Required | Default | Example | Sensitive | Notes | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `DEBUG` | No | `False` | `False` | No | `False`일 때 운영 검증이 강제됨 | 디버그 모드 여부와 로그 레벨/검증 조건에 영향을 줍니다. |
| `TIMEZONE` | No | `Asia/Seoul` | `Asia/Seoul` | No | `Config.TZ`로 변환되어 사용 | 날짜/시간 응답 직렬화 및 시간 계산 기준 타임존입니다. |
| `BASE_URL` | No | `https://sandol.sio2.kr/kakao-bot` | `https://sandol.sio2.kr/kakao-bot` | No | 끝 `/`는 내부에서 정리됨 | 외부 접근 기준 URL이며 로그인 콜백 기본값 계산에 사용됩니다. |
| `LOGIN_CALLBACK_URL` | No | `{BASE_URL}/users/callback` | `https://.../kakao-bot/users/callback` | No | 미설정 시 `BASE_URL` 기반 자동 계산 | Auth Relay 로그인 콜백 URL입니다. |
| `LOGIN_REDIRECT_AFTER` | No | empty / `None` | `` | No | 빈 문자열(`""`)과 `None`은 의미가 다를 수 있어 명시 권장 | 로그인 완료 후 추가 리다이렉트 URL입니다. |
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///./kakao_bot_service.db` | `sqlite+aiosqlite:///./kakao_bot_service.db` | No | Alembic(`alembic/env.py`)에서 필수 | 앱 DB 엔진과 마이그레이션 연결 문자열입니다. |
| `CACHE_DIR` | No | `./.cache` | `./.cache` | No | nonce/cache 저장 경로 | Auth Relay nonce 검증 캐시 저장 위치입니다. |
| `AUTH_RELAY_URL` | Yes (login flow) | `http://auth-relay:8000/relay` | `http://auth-relay:8000/relay` | No | `/issue_login_link` 호출에 사용 | 로그인 링크 발급용 auth-relay base URL입니다. |
| `MEAL_SERVICE_URL` | Yes (meal feature) | `http://meal-service:80/meal` | `http://meal-service:80/meal` | No | meal/restaurant API 호출 | 식단/식당 조회 기능의 upstream base URL입니다. |
| `STATIC_INFO_SERVICE_URL` | Yes (statics feature) | `http://static-info-service:80/static-info` | `http://static-info-service:80/static-info` | No | 조직도/셔틀 이미지 조회 | 정적 정보 기능 upstream base URL입니다. |
| `NOTICE_SERVICE_URL` | Yes (notice feature) | `http://notice-notification:8081/notice-notification` | `http://notice-notification:3000/notice-notification` | No | `.env.example` 예시 포트(3000)와 코드 fallback(8081) 불일치, 운영에서는 실제 포트로 명시 | 공지 조회 기능 upstream base URL입니다. |
| `CLASSROOM_TIMETABLE_SERVICE_URL` | Yes (classroom feature) | `http://classroom-timetable-service:80/classroom-timetable` | `http://classroom-timetable-service:80/classroom-timetable` | No | 빈 강의실 조회 API 호출 | 강의실 시간표 기능 upstream base URL입니다. |
| `KC_SERVER_URL` | Yes (auth feature) | `https://sandol.sio2.kr/auth/` | `https://sandol.sio2.kr/auth/` | No | 내부에서 trailing slash 정규화 | Keycloak 서버 base URL입니다. |
| `KC_CLIENT_ID` | Yes (auth feature) | `sandol-kakao-bot` | `sandol-kakao-bot` | No | login link payload에도 사용 | Keycloak 클라이언트 ID입니다. |
| `KC_REALM` | Yes (auth feature) | `Sandori` | `Sandori` | No | Keycloak client 초기화에 사용 | Keycloak Realm 이름입니다. |
| `KC_CLIENT_SECRET` | Yes when `DEBUG=False` | none | `*****` | Yes | `Config._validate()`에서 운영 시 필수 | Keycloak confidential client 시크릿입니다. |
| `TOKEN_ENCRYPTION_KEY` | Yes | none | `*****` | Yes | `Config._validate()`에서 항상 필수 | 사용자 토큰 암복호화(Fernet) 키입니다. |
| `RELAY_CLIENT_SECRETS` | Yes when `DEBUG=False` | empty string | `dev-hmac-secret-please-change` | Yes | relay 서명 검증 키, 운영에서는 강한 값 필수 | Auth Relay callback 서명 검증용 secret입니다. |
| `NONCE_TTL_SECONDS` | No | `300` | `300` | No | timestamp/nonce 검증 허용 시간창 | replay 공격 방지를 위한 nonce/timestamp TTL(초)입니다. |

#### Required 판정 기준

- `Yes`: 미설정 시 런타임 오류 또는 핵심 기능 불가
- `Yes when DEBUG=False`: 운영 모드 검증(`Config._validate`)에서 강제
- `No`: 코드 fallback 또는 기능 선택적 사용 가능

- **Docker Compose를 통해 서비스 간 네트워크 및 볼륨을 설정**
- **프론트엔드 서비스(챗봇 서버, 웹 서비스)와 백엔드 서비스(API 서버)의 차이점을 반영하여 개별 실행 가능**

### 📌 실행 방법

#### 1. 기본 실행 (모든 서비스 실행)

```bash
docker compose up -d
```

#### 2. 특정 서비스만 실행 (예: 챗봇 서버)

```bash
docker compose up -d sandol_kakao_bot_service
```

#### 3. 서비스 중지

```bash
docker compose down
```

#### 4. 환경 변수 변경 후 재시작

```bash
docker compose up -d --build
```

---

## 📌 배포 가이드

- **Database 자동화**
  - Sqlalchemy를 사용하여 데이터베이스 마이그레이션을 자동으로 처리합니다. db가 없을 경우 자동으로 생성됩니다.

- **.env 파일 설정 필요**  
  - repository에 `.env` 파일이 포함되어 있지 않으므로, 환경에 맞게 `.env` 파일을 생성해야 합니다. 파일의 내용은 `.env.example` 파일을 참고하세요.

---

## 📌 문의

- 버그는 Issue로 등록해주세요.
- [디스코드 채널(팀원용)](https://discord.com/channels/1339452791071969331/1339456512363597875)
- [코드 개발자(홍석영)의 깃허브](https://github.com/Seokyoung-Hong)

---
🚀 **산돌이 프로젝트와 함께 효율적인 개발 환경을 만들어갑시다!**
