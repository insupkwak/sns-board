# SNS 게시판 — 프로젝트 정리 (rev.1)

> _개정: 2026-05-30 · 모바일 최적화 / 너비 일관성 / 카테고리 선택창 제거 반영_

> 트위터 스타일의 간단한 SNS 게시판. 제목 없이 본문만 올리고, 카테고리·좋아요·댓글·무한스크롤을 지원합니다.
> **배포 주소(미리보기):** https://sns-board-mauve.vercel.app
> **저장소:** https://github.com/insupkwak/sns-board

---

## 1. 기술 스택

| 구분 | 사용 기술 |
|---|---|
| 백엔드 | Python **Flask** |
| 데이터베이스 | **SQLite** (`data/board.db`, 스키마 `data/data.sql`) |
| 비밀번호 | werkzeug 해시 저장(`generate/check_password_hash`) |
| 인증 | Flask **세션 쿠키** |
| 프론트엔드 | 순수 **HTML / CSS / JavaScript** (프레임워크 없음) |
| 미리보기 배포 | **Vercel** (GitHub 연동 자동배포) |
| 운영(예정) | **Oracle 서버** (영속 DB) |

---

## 2. 주요 기능 (요구사항 대응)

### 사용자
- 회원가입: **별명 / 이메일 / 비밀번호 / 비밀번호 확인** (최소 정보)
- 로그인 / 로그아웃 (세션 기반), 비밀번호 해시 저장
- 로그인·회원가입은 한 모달에서 **탭 전환**, 각 화면에 필요한 입력칸만 표시

### 게시판
- **제목 없이 본문만** 작성
- **카테고리**: 자유 / 질문 / 정보 / 일상 / 유머 — **왼쪽 메뉴에서 선택**(글쓰기 칸엔 별도 선택창 없음, 현재 보고 있는 카테고리로 작성, '전체'면 '자유')
- **최신글이 항상 최상단**, **무한 스크롤**
- **좋아요** 토글, **댓글** 보기/작성(댓글 버튼으로 펼침)
- 본인 글·댓글 **수정 / 삭제**
- 글쓰기·수정 입력칸은 **내용 줄 수에 맞춰 높이 자동 확장**

### 디자인 (디자인.md 기준)
- 밝은 색상 / 심플 / **각진(라운드 없음)** / **그림자 없음** / 시인성 우선
- 화면 중앙 레이아웃 (PC), **모바일 최적화**

---

## 3. 모바일 최적화

- `viewport-fit=cover` + `env(safe-area-inset-*)` — 노치/홈인디케이터 안전영역 확보
- **가로 스크롤 차단**, 320/360/390px 폭 모두 검증
- 좌우 여백 최소화(6px) — 콘텐츠가 화면 너비의 **약 97%** 사용
- 로그인 전·후 **너비 일관성**(글쓰기·안내·게시글 모두 전체 너비)
- 카테고리 가로 메뉴(스크롤바 숨김), 버튼이 가로를 꽉 채움
- 터치 타깃 42~44px, iOS 입력 자동확대 방지(입력칸 16px)

---

## 4. 폴더 구조

```
app.py                 Flask 백엔드(인증·게시글·댓글·좋아요 API, DB 초기화)
templates/index.html   단일 페이지 UI (상단바 + 왼쪽 카테고리 + 중앙 피드 + 로그인 모달)
static/css/style.css   스타일(각진 디자인 + 모바일 반응형)
static/js/app.js       프론트엔드 로직(피드/무한스크롤/모달/CRUD/자동높이)
data/data.sql          DB 스키마 (앱 첫 실행 시 board.db 자동 생성)
data/board.db          실제 데이터 (git/배포 제외 — 업로드 안 함)
vercel.json            Vercel 배포 설정
.gitignore/.vercelignore  실DB·.env·venv 제외
README.md / 프로젝트정리.md  문서
```

---

## 5. API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 메인 페이지 |
| POST | `/api/register` | 회원가입 |
| POST | `/api/login` | 로그인 |
| POST | `/api/logout` | 로그아웃 |
| GET | `/api/me` | 현재 사용자 + 카테고리 목록 |
| GET | `/api/posts` | 게시글 목록 (`?category=&offset=&limit=`, 최신순, 무한스크롤) |
| POST | `/api/posts` | 글 작성 |
| PUT | `/api/posts/<id>` | 글 수정 (본인만) |
| DELETE | `/api/posts/<id>` | 글 삭제 (본인만) |
| POST | `/api/posts/<id>/like` | 좋아요 토글 |
| GET | `/api/posts/<id>/comments` | 댓글 목록 |
| POST | `/api/posts/<id>/comments` | 댓글 작성 |
| PUT | `/api/comments/<id>` | 댓글 수정 (본인만) |
| DELETE | `/api/comments/<id>` | 댓글 삭제 (본인만) |

권한 가드: 비로그인 작성 401, 타인 글/댓글 수정·삭제 403, 중복 이메일 409.

---

## 6. 데이터베이스 스키마

- **users**: id, email(unique), nickname, password_hash, created_at
- **posts**: id, user_id, category, content, created_at, updated_at
- **comments**: id, post_id, user_id, content, created_at, updated_at
- **likes**: (post_id, user_id) 복합 PK — 게시글·사용자당 1개
- 외래키 `ON DELETE CASCADE` (글 삭제 시 댓글·좋아요 함께 삭제)

---

## 7. 로컬 실행

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

> macOS는 5000 포트를 AirPlay가 쓰므로 **5001** 사용.

---

## 8. 배포

- **미리보기(Vercel)**: GitHub `sns-board` 저장소와 연동되어, `git push`마다 자동 재배포.
  - 서버리스 환경이라 DB가 `/tmp/board.db`(임시) → **콜드스타트/재배포 시 데이터 초기화**. **UI·디자인 확인 전용**.
- **운영(Oracle, 예정)**: gunicorn 등 WSGI + 영속 SQLite/DB로 실제 데이터 보관.

---

## 9. 주의사항

- `data/board.db`는 **실제 사용자 계정/게시글** → 삭제 금지. 테스트는 `DB_DIR=/tmp`로 임시 DB 사용.
- Vercel **미리보기는 데이터 휘발** → 실데이터는 Oracle에서 운영.
- 코드 수정 시 브라우저 캐시 문제 없음(파일 mtime 기반 캐시버스터 + HTML `no-store` 적용).

---

## 10. 개발 중 해결한 주요 이슈

1. **로그인/회원가입 폼이 겹쳐 보임** → `[hidden]{display:none!important}`로 해결.
2. **회원가입 시 메인으로 튐 / 실패 시 모달 닫힘** → 캐시버스터를 파일 mtime 기반으로 바꿔 항상 최신 JS 로드 + 폼 네이티브 제출 차단.
3. **재시작하면 로그인 안 됨** → 코드 문제 아님(테스트가 DB를 지웠던 것). DB는 재시작에도 유지됨.
4. **모바일에서 너비가 로그인 전·후 다르고 화면을 못 채움** → `align-items:stretch` + `.feed width:100%`로 전체 너비 통일.
5. 글쓰기/수정 칸 고정 높이 → **내용에 맞춰 자동 확장**.
6. 글쓰기 칸의 중복 카테고리 선택창 제거(왼쪽 메뉴로 일원화).
