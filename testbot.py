"""
testbot.py — 테스트용 멤버 5명을 만들고 사이트에 계속 글을 올리는 봇

사용법:
    python3 testbot.py                 # 무한 반복(끄려면 Ctrl+C)
    python3 testbot.py --rounds 20     # 20번만 글 올리고 종료
    python3 testbot.py --interval 1.0  # 글 사이 간격(초)
    BASE=http://127.0.0.1:5001 python3 testbot.py

- 멤버 계정: tester1~5@test.com / 비밀번호 1234 (별명: 테스터민준 등)
- 글을 올리고, 가끔 다른 글에 좋아요/댓글도 단다.
- 실제 DB(data/board.db)에 쌓이므로 테스트 후 정리하려면 아래 'cleanup' 참고.
"""
import os
import json
import time
import random
import argparse
import http.cookiejar
import urllib.request
import urllib.error

BASE = os.getenv("BASE", "http://127.0.0.1:5001")

MEMBERS = [
    {"email": "tester1@test.com", "nickname": "테스터민준"},
    {"email": "tester2@test.com", "nickname": "테스터서연"},
    {"email": "tester3@test.com", "nickname": "테스터도윤"},
    {"email": "tester4@test.com", "nickname": "테스터지우"},
    {"email": "tester5@test.com", "nickname": "테스터하준"},
]
PASSWORD = "1234"
CATEGORIES = ["자유", "질문", "정보", "일상", "유머"]

TOPICS = [
    "오늘 점심 뭐 먹지? 추천 받아요 🍜",
    "이 기능 진짜 편하네요. 다들 써보셨나요?",
    "주말에 갈 만한 여행지 있을까요?",
    "오늘 코드 리뷰 통과! 기분 좋다 😎",
    "요즘 읽는 책 공유합니다 📚",
    "다크 모드 디자인 너무 깔끔한데요?",
    "질문 있어요. 무한 스크롤 어떻게 구현했나요?",
    "출근길 커피 한 잔의 여유 ☕",
    "버그 하나 잡았습니다. 뿌듯 🐛",
    "오늘 날씨 진짜 좋네요. 산책 가실 분?",
    "새 프로젝트 시작했어요. 응원 부탁 🙏",
    "이 게시판 점점 좋아지는 듯!",
    "운동 3일째 성공 💪",
    "고양이 자랑 좀 하겠습니다 🐱",
    "맛집 발견! 다음에 후기 올릴게요.",
]
COMMENTS = ["오 좋네요!", "공감합니다 👍", "저도요!", "정보 감사해요", "ㅋㅋㅋ", "응원합니다!", "굿굿", "오늘도 화이팅"]


def make_client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(op, path, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    try:
        r = op.open(req, timeout=10)
        return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"error": str(ex)}


def login_or_register(m):
    op = make_client()
    st, _ = call(op, "/api/login", "POST", {"email": m["email"], "password": PASSWORD})
    if st == 200:
        return op
    call(op, "/api/register", "POST", {
        "email": m["email"], "nickname": m["nickname"],
        "password": PASSWORD, "password2": PASSWORD})
    call(op, "/api/login", "POST", {"email": m["email"], "password": PASSWORD})
    return op


def recent_post_ids(op, limit=10):
    st, data = call(op, f"/api/posts?offset=0&limit={limit}")
    if st == 200 and isinstance(data.get("posts"), list):
        return [p["id"] for p in data["posts"]]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=0, help="글 올리는 횟수(0=무한)")
    ap.add_argument("--interval", type=float, default=2.0, help="글 사이 간격(초)")
    args = ap.parse_args()

    print(f"[testbot] 서버: {BASE}")
    sessions = []
    for m in MEMBERS:
        op = login_or_register(m)
        sessions.append((m, op))
        print(f"[testbot] 준비됨: {m['nickname']} ({m['email']})")

    print(f"[testbot] 시작 — rounds={args.rounds or '무한'}, interval={args.interval}s (Ctrl+C로 중지)")
    n = 0
    try:
        while True:
            n += 1
            m, op = random.choice(sessions)
            content = random.choice(TOPICS)
            category = random.choice(CATEGORIES)
            st, data = call(op, "/api/posts", "POST", {"content": content, "category": category})
            ok = "OK" if st == 201 else f"실패({st})"
            print(f"[{n:>4}] {m['nickname']} → [{category}] {content[:24]}  {ok}")

            # 가끔 좋아요/댓글
            ids = recent_post_ids(op)
            if ids and random.random() < 0.6:
                call(op, f"/api/posts/{random.choice(ids)}/like", "POST")
            if ids and random.random() < 0.4:
                call(op, f"/api/posts/{random.choice(ids)}/comments", "POST",
                     {"content": random.choice(COMMENTS)})

            if args.rounds and n >= args.rounds:
                print(f"[testbot] 완료 — 총 {n}개 글 작성")
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n[testbot] 중지됨 — 총 {n}개 글 작성")


if __name__ == "__main__":
    main()
