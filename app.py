import os
import re
import sqlite3
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, g, session, make_response

load_dotenv()

APP_VERSION = os.getenv("APP_VERSION", "0.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCHEMA_PATH = os.path.join(DATA_DIR, "data.sql")

# Vercel 등 서버리스 환경은 파일시스템이 읽기전용이고 /tmp 만 쓰기 가능.
# (이 경우 DB 는 임시본이라 재배포/콜드스타트 시 초기화됨 — 디자인 확인용)
if os.getenv("VERCEL") or os.getenv("DB_DIR"):
    DB_PATH = os.path.join(os.getenv("DB_DIR", "/tmp"), "board.db")
else:
    DB_PATH = os.path.join(DATA_DIR, "board.db")

# 왼쪽 메뉴 카테고리 (디자인.md: 카테고리 선택은 왼쪽 메뉴)
CATEGORIES = ["자유", "질문", "정보", "일상", "유머"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")


# ---------------------------------------------------------------------------
# 데이터베이스
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """data.sql 스키마로 board.db 생성 (없으면). CREATE ... IF NOT EXISTS 라 반복 호출 안전."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


# 실행 방식(python app.py / flask run / gunicorn 등)과 무관하게 항상 테이블 보장
init_db()


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = get_db().execute(
        "SELECT id, email, nickname FROM users WHERE id = ?", (uid,)
    ).fetchone()
    return dict(row) if row else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "로그인이 필요합니다."}), 401
        return view(*args, **kwargs)

    return wrapped


def serialize_post(row, me_id):
    db = get_db()
    likes = db.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id = ?", (row["id"],)
    ).fetchone()[0]
    liked = False
    if me_id:
        liked = (
            db.execute(
                "SELECT 1 FROM likes WHERE post_id = ? AND user_id = ?",
                (row["id"], me_id),
            ).fetchone()
            is not None
        )
    comment_count = db.execute(
        "SELECT COUNT(*) FROM comments WHERE post_id = ?", (row["id"],)
    ).fetchone()[0]
    return {
        "id": row["id"],
        "category": row["category"],
        "content": row["content"],
        "nickname": row["nickname"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "likes": likes,
        "liked": liked,
        "comment_count": comment_count,
        "mine": me_id == row["user_id"],
    }


# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------
def asset_version(rel_path):
    """정적 파일 수정시각을 캐시버스터로 사용 (편집할 때마다 값이 바뀌어 새로 로드됨)."""
    try:
        return int(os.path.getmtime(os.path.join(app.static_folder, rel_path)))
    except OSError:
        return APP_VERSION


@app.route("/")
def index():
    resp = make_response(render_template(
        "index.html",
        version=APP_VERSION,
        categories=CATEGORIES,
        css_v=asset_version("css/style.css"),
        js_v=asset_version("js/app.js"),
    ))
    # HTML 은 항상 새로 받도록(캐시버스터가 붙은 최신 JS/CSS 를 참조하게)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------------------
# 인증 API
# ---------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    nickname = (data.get("nickname") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""

    if not email or not nickname or not password:
        return jsonify({"error": "모든 항목을 입력하세요."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "이메일 형식이 올바르지 않습니다."}), 400
    if len(nickname) > 20:
        return jsonify({"error": "별명은 20자 이하로 입력하세요."}), 400
    if len(password) < 4:
        return jsonify({"error": "비밀번호는 4자 이상이어야 합니다."}), 400
    if password != password2:
        return jsonify({"error": "비밀번호가 일치하지 않습니다."}), 400

    from werkzeug.security import generate_password_hash

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (email, nickname, password_hash) VALUES (?, ?, ?)",
            (email, nickname, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "이미 가입된 이메일입니다."}), 409

    session["user_id"] = cur.lastrowid
    return jsonify({"user": current_user()}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    from werkzeug.security import check_password_hash

    row = get_db().execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401

    session["user_id"] = row["id"]
    return jsonify({"user": current_user()})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    return jsonify({"user": current_user(), "categories": CATEGORIES})


# ---------------------------------------------------------------------------
# 게시글 API
# ---------------------------------------------------------------------------
@app.route("/api/posts")
def list_posts():
    """최신글 상단, 무한스크롤용 offset/limit."""
    category = request.args.get("category")
    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = min(50, max(1, int(request.args.get("limit", 10))))
    except ValueError:
        offset, limit = 0, 10

    me_id = session.get("user_id")
    db = get_db()
    sql = (
        "SELECT p.*, u.nickname FROM posts p "
        "JOIN users u ON u.id = p.user_id "
    )
    params = []
    if category and category in CATEGORIES:
        sql += "WHERE p.category = ? "
        params.append(category)
    sql += "ORDER BY p.id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = db.execute(sql, params).fetchall()
    posts = [serialize_post(r, me_id) for r in rows]
    return jsonify({"posts": posts, "has_more": len(rows) == limit})


@app.route("/api/posts", methods=["POST"])
@login_required
def create_post():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    category = data.get("category") or "자유"
    if not content:
        return jsonify({"error": "내용을 입력하세요."}), 400
    if category not in CATEGORIES:
        category = "자유"

    db = get_db()
    cur = db.execute(
        "INSERT INTO posts (user_id, category, content) VALUES (?, ?, ?)",
        (session["user_id"], category, content),
    )
    db.commit()
    row = db.execute(
        "SELECT p.*, u.nickname FROM posts p JOIN users u ON u.id = p.user_id "
        "WHERE p.id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return jsonify({"post": serialize_post(row, session["user_id"])}), 201


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
@login_required
def update_post(post_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "내용을 입력하세요."}), 400

    db = get_db()
    row = db.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
    if row["user_id"] != session["user_id"]:
        return jsonify({"error": "권한이 없습니다."}), 403

    db.execute(
        "UPDATE posts SET content = ?, updated_at = datetime('now','localtime') "
        "WHERE id = ?",
        (content, post_id),
    )
    db.commit()
    updated = db.execute(
        "SELECT p.*, u.nickname FROM posts p JOIN users u ON u.id = p.user_id "
        "WHERE p.id = ?",
        (post_id,),
    ).fetchone()
    return jsonify({"post": serialize_post(updated, session["user_id"])})


@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
@login_required
def delete_post(post_id):
    db = get_db()
    row = db.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
    if row["user_id"] != session["user_id"]:
        return jsonify({"error": "권한이 없습니다."}), 403
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/posts/<int:post_id>/like", methods=["POST"])
@login_required
def toggle_like(post_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
        return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404

    uid = session["user_id"]
    exists = db.execute(
        "SELECT 1 FROM likes WHERE post_id = ? AND user_id = ?", (post_id, uid)
    ).fetchone()
    if exists:
        db.execute(
            "DELETE FROM likes WHERE post_id = ? AND user_id = ?", (post_id, uid)
        )
        liked = False
    else:
        db.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, uid)
        )
        liked = True
    db.commit()
    likes = db.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id = ?", (post_id,)
    ).fetchone()[0]
    return jsonify({"liked": liked, "likes": likes})


# ---------------------------------------------------------------------------
# 댓글 API
# ---------------------------------------------------------------------------
@app.route("/api/posts/<int:post_id>/comments")
def list_comments(post_id):
    me_id = session.get("user_id")
    rows = get_db().execute(
        "SELECT c.*, u.nickname FROM comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.post_id = ? ORDER BY c.id ASC",
        (post_id,),
    ).fetchall()
    comments = [
        {
            "id": r["id"],
            "content": r["content"],
            "nickname": r["nickname"],
            "user_id": r["user_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "mine": me_id == r["user_id"],
        }
        for r in rows
    ]
    return jsonify({"comments": comments})


@app.route("/api/posts/<int:post_id>/comments", methods=["POST"])
@login_required
def create_comment(post_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "댓글을 입력하세요."}), 400

    db = get_db()
    if not db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
        return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
    db.execute(
        "INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
        (post_id, session["user_id"], content),
    )
    db.commit()
    return jsonify({"ok": True}), 201


@app.route("/api/comments/<int:comment_id>", methods=["PUT"])
@login_required
def update_comment(comment_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "댓글을 입력하세요."}), 400

    db = get_db()
    row = db.execute(
        "SELECT user_id FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "댓글을 찾을 수 없습니다."}), 404
    if row["user_id"] != session["user_id"]:
        return jsonify({"error": "권한이 없습니다."}), 403
    db.execute(
        "UPDATE comments SET content = ?, updated_at = datetime('now','localtime') "
        "WHERE id = ?",
        (content, comment_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
@login_required
def delete_comment(comment_id):
    db = get_db()
    row = db.execute(
        "SELECT user_id FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "댓글을 찾을 수 없습니다."}), 404
    if row["user_id"] != session["user_id"]:
        return jsonify({"error": "권한이 없습니다."}), 403
    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    # macOS 는 5000 포트를 AirPlay 수신기가 점유하는 경우가 많아 5001 사용
    port = int(os.getenv("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True, threaded=True)
