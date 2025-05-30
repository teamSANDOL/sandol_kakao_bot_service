# 📌 산돌이 Repository Template

## 📂 개요

**(이 Repository가 담당하는 서비스의 간략한 설명을 작성하세요.)**
이 Repository는 **산돌이 프로젝트**의 **카카오톡 챗봇 서버** 코드 내용입니다.

이 서비스는 **Docker 컨테이너로 실행**되며, 이후 **Docker Compose를 활용하여 통합 운영**됩니다.

---

## 📌 프로젝트 구조

- FastAPI + SQLAlchemy + SQLite 기반의 API 서버
- 카카오톡 Open Builder의 설정을 통해 본 서버와 연동됩니다.

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

  # User 서버에 저장된 SERVICE_ID
  SERVICE_ID=4

  # 각종 설정(Debug 변경시 변경 필요)
  DATABASE_URL=sqlite+aiosqlite:///./kakao_bot_service.db
  USER_SERVICE_URL=http://user-service:8000/user
  MEAL_SERVICE_URL=http://meal-service:80/meal
  STATIC_INFO_SERVICE_URL=http://static-info-service:80/static-info
  NOTICE_SERVICE_URL=http://notice-notification:8081/notice-notification
  CLASSTROOM_TIMETABLE_SERVICE_URL=http://classroom-timetable-service:80/classroom-timetable

  # 애플리케이션 설정
  APP_PORT=80
  APP_ENV=development
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
  - Sqlalchemy를 사용하여 데이터베이스 마이그레이션을 자동으로 처리합니다. Service_account 등 db가 없을 경우 자동으로 생성됩니다.

- **.env 파일 설정 필요**  
  - repository에 `.env` 파일이 포함되어 있지 않으므로, 환경에 맞게 `.env` 파일을 생성해야 합니다. 파일의 내용은 `.env.example` 파일을 참고하세요.

---

## 📌 문의

- 버그는 Issue로 등록해주세요.
- [디스코드 채널(팀원용)](https://discord.com/channels/1339452791071969331/1339456512363597875)
- [코드 개발자(홍석영)의 깃허브](https://github.com/Seokyoung-Hong)

---
🚀 **산돌이 프로젝트와 함께 효율적인 개발 환경을 만들어갑시다!**
