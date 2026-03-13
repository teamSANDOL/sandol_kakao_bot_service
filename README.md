# 📌 산돌이 Repository Template

## 📂 개요

**(이 Repository가 담당하는 서비스의 간략한 설명을 작성하세요.)**
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
- **서비스 관련 문서**
  - 카카오 OpenBuilder 가이드: [OpenBuilder 가이드](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format)

---

## 📌 환경 설정

- **모든 서비스는 Docker 기반으로 실행**되므로, `Docker`만 설치되어 있다면 로컬 환경에 별도로 의존하지 않음
- 환경 변수 파일 (`.env`) 필요

  ```.env
  DEBUG=False

  # 각종 설정(Debug 변경시 변경 필요)
  BASE_URL=https://sandol.sio2.kr/kakao-bot
  KC_SERVER_URL=https://sandol.sio2.kr/auth/
  DATABASE_URL=sqlite+aiosqlite:///./kakao_bot_service.db
  AUTH_RELAY_URL=http://auth-relay:8000/relay
  MEAL_SERVICE_URL=http://meal-service:80/meal
  STATIC_INFO_SERVICE_URL=http://static-info-service:80/static-info
  NOTICE_SERVICE_URL=http://notice-notification:3000/notice-notification
  CLASSROOM_TIMETABLE_SERVICE_URL=http://classroom-timetable-service:80/classroom-timetable
  TOKEN_ENCRYPTION_KEY=*****
  RELAY_CLIENT_SECRETS=dev-hmac-secret-please-change
  KC_CLIENT_SECRET=*****
  ```

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
