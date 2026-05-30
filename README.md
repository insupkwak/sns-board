# SNS 게시판

Flask + SQLite 기반 SNS 게시판. 카테고리(왼쪽 메뉴) · 글쓰기(제목 없이 본문) · 좋아요 · 댓글 · 수정/삭제 · 무한 스크롤 · 로그인/회원가입.

## 로컬 실행

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py        # http://127.0.0.1:5001
```

`.env` 예시:

```
SECRET_KEY=충분히-긴-임의-문자열
PORT=5001
APP_VERSION=1.0.0
```

## 배포

- **개발 미리보기: Vercel** — `vercel.json` 포함. 서버리스 환경이라 DB 는 `/tmp/board.db`(임시)로 동작하며 콜드스타트/재배포 시 초기화됩니다. **UI·디자인 확인용**으로만 사용하세요.
  - 환경변수: `SECRET_KEY` 를 Vercel 프로젝트에 설정 권장.
- **운영: Oracle 서버(예정)** — gunicorn 등 WSGI + 영속 SQLite/DB 로 실제 데이터 보관.

## 구조

```
app.py                 Flask 백엔드(인증·게시글·댓글·좋아요 API)
templates/index.html   단일 페이지 UI
static/css/style.css   스타일
static/js/app.js       프론트엔드 로직
data/data.sql          DB 스키마(앱 첫 실행 시 board.db 자동 생성)
vercel.json            Vercel 배포 설정
```
