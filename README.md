# Messenger — Telegram 스타일 내부용 SNS / 메신저

Flask + Flask-SocketIO + SQLite 기반의 간단하고 깔끔한 실시간 메신저입니다.
그룹/1:1 채팅, 실시간 메시지, 첨부파일, 읽음 표시, 프로필, 관리자 기능을 제공합니다.

## 주요 기능

- **사용자**: 회원가입, 로그인/로그아웃(세션), 비밀번호 해시 저장, 프로필 이름·상태·이미지 변경, 사용자 검색
- **채팅방**: General 자동 생성, 그룹방 생성/검색/이름·설명 변경/삭제/나가기, 멤버 초대·목록, 고정·즐겨찾기, 최근 메시지·시간·읽지 않은 수 표시
- **1:1 채팅**: 사용자 검색 후 시작, 동일 상대는 기존 방 재사용, 상대 이름으로 표시
- **메시지**: 실시간 송수신, 수정/삭제(소프트 삭제)/답장/고정/검색, 읽음 처리, Enter 전송 / Shift+Enter 줄바꿈, 길이 제한
- **첨부파일**: 업로드(확장자·크기 제한), 이미지 미리보기, 일반 파일 다운로드, secure_filename + uuid 저장
- **알림/UX**: 앱 내부 알림, 자동 스크롤, debounce 검색, Toast, 다크 Telegram UI, 모바일 전환
- **관리자**: 요약 통계, 사용자 목록·비활성화, 채팅방 목록·삭제, 공지방 생성

## 설치

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 실행

```bash
python app.py
```

접속: http://127.0.0.1:5000

## 기본 관리자 계정

```
아이디: admin
비밀번호: admin1234
이름: Administrator
```

> ⚠️ 운영 환경에서는 반드시 비밀번호를 변경/재설정하세요. (DB 초기화 시 자동 생성됩니다)

## 폴더 구조

```
app.py            Flask 라우트 + SocketIO + 인증 + 파일 업로드
storage.py        DB 함수 + 마이그레이션
requirements.txt
README.md
instance/sns.db   SQLite DB (자동 생성, git 제외)
uploads/
  attachments/    첨부파일 저장 위치
  profiles/       프로필 이미지 저장 위치
templates/        base, login, register, chat, profile, admin
static/css/style.css
static/js/         chat.js, profile.js, admin.js
```

## 저장 위치

- DB: `instance/sns.db` (서버리스/Vercel 환경에서는 `/tmp/sns.db`)
- 첨부파일: `uploads/attachments/`
- 프로필 이미지: `uploads/profiles/`

## 테스트 방법

1. http://127.0.0.1:5000 접속 → 회원가입 후 로그인
2. 좌측에서 General 방 선택 → 메시지 전송(다른 브라우저/시크릿창으로 동시 접속하면 실시간 확인)
3. "새 그룹 채팅방" 생성, 사용자 검색으로 1:1 채팅 시작
4. 메시지 수정/삭제/답장/고정, 파일 첨부(이미지/문서)
5. 프로필에서 이름·상태·이미지 변경
6. admin 계정으로 로그인 → 우상단 ⚙ → 관리자 페이지

## 주의사항

- 실시간(SocketIO)은 **상시 구동되는 서버**가 필요합니다. 로컬 `python app.py` 또는 Oracle 등 일반 서버에서 동작합니다.
  Vercel 같은 서버리스 환경에서는 WebSocket/상태 유지가 제한되며 업로드·DB가 휘발됩니다(미리보기 한계).
- `instance/`, `uploads/`, `.env`는 git에 올리지 않습니다(실데이터 보호).
- 운영 시 `SECRET_KEY`를 안전한 값으로 설정하세요.
```
SECRET_KEY=충분히-긴-임의-문자열
PORT=5000
```
