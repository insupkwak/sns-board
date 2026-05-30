import os
import re
import sqlite3
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, g, session, make_response

import media

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
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


# 실행 방식(python app.py / flask run / gunicorn 등)과 무관하게 항상 테이블 보장
init_db()
media.init_media_db()


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = get_db().execute(
        "SELECT id, email, nickname, COALESCE(is_admin,0) is_admin FROM users WHERE id = ?", (uid,)
    ).fetchone()
    return dict(row) if row else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "로그인이 필요합니다."}), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u:
            return jsonify({"error": "로그인이 필요합니다."}), 401
        if not u.get("is_admin"):
            return jsonify({"error": "관리자 권한이 필요합니다."}), 403
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


def _page(template, **ctx):
    resp = make_response(render_template(
        template, version=APP_VERSION, categories=CATEGORIES,
        media_categories=media.MEDIA_CATEGORIES,
        css_v=asset_version("css/style.css"), **ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/discovery")
def discovery_page():
    return _page("discovery.html")


@app.route("/channel/<int:channel_id>")
def channel_page(channel_id):
    return _page("channel.html", channel_id=channel_id)


@app.route("/article/new")
def article_editor_page():
    return _page("article_editor.html")


@app.route("/article/<int:article_id>")
def article_detail_page(article_id):
    return _page("article_detail.html", article_id=article_id)


@app.route("/promotions")
def promotion_center_page():
    return _page("promotion_center.html")


@app.route("/media")
def media_dashboard_page():
    return _page("media_dashboard.html")


@app.route("/admin")
def admin_page():
    return _page("admin.html")


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
    search = (request.args.get("search") or "").strip()
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
    where, params = [], []
    if category and category in CATEGORIES:
        where.append("p.category = ?")
        params.append(category)
    if search:
        where.append("(p.content LIKE ? OR u.nickname LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
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


# ===========================================================================
#  3차 고도화: 미디어 기능 API (게시판 위에 레이어)
# ===========================================================================
def _uid():
    return session.get("user_id")


@app.route("/api/media/me")
def media_me():
    return jsonify({"user": current_user(), "media_categories": media.MEDIA_CATEGORIES})


# ---- Organizations ----
@app.route("/api/organizations", methods=["POST"])
@login_required
def org_create():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "조직명을 입력하세요."}), 400
    oid = media.create_organization(name, d.get("org_type") or "media", _uid(),
                                    description=(d.get("description") or "").strip() or None)
    return jsonify({"ok": True, "organization": media.get_organization(oid)}), 201


@app.route("/api/organizations/mine")
@login_required
def org_mine():
    return jsonify({"ok": True, "organizations": media.list_organizations_for_user(_uid())})


@app.route("/api/organizations/<int:oid>/verify-request", methods=["POST"])
@login_required
def org_verify_request(oid):
    if not media.is_org_member(oid, _uid()):
        return jsonify({"error": "권한이 없습니다."}), 403
    media.request_org_verification(oid)
    return jsonify({"ok": True})


# ---- Channels ----
@app.route("/api/channels", methods=["POST"])
@login_required
def channel_create():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "채널 이름을 입력하세요."}), 400
    org_id = d.get("organization_id")
    if org_id and not media.is_org_member(int(org_id), _uid()):
        return jsonify({"error": "해당 조직의 멤버가 아닙니다."}), 403
    cid = media.create_channel(name, _uid(), channel_type=d.get("channel_type") or "channel",
                               description=(d.get("description") or "").strip() or None,
                               organization_id=int(org_id) if org_id else None,
                               media_category=d.get("media_category"))
    return jsonify({"ok": True, "channel": media.get_channel(cid, _uid())}), 201


@app.route("/api/channels/mine")
@login_required
def channel_mine():
    return jsonify({"ok": True, "channels": media.list_my_channels(_uid())})


@app.route("/api/channels/<int:cid>")
def channel_get(cid):
    ch = media.get_channel(cid, _uid())
    if not ch:
        return jsonify({"error": "채널을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "channel": ch,
                    "articles": media.list_articles_for_channel(cid)})


@app.route("/api/channels/<int:cid>/follow", methods=["POST"])
@login_required
def channel_follow(cid):
    d = request.get_json(silent=True) or {}
    following, count = media.follow_channel(cid, _uid(), follow=d.get("follow") is not False)
    return jsonify({"ok": True, "following": following, "follower_count": count})


@app.route("/api/channels/<int:cid>", methods=["DELETE"])
@login_required
def channel_delete(cid):
    u = current_user()
    if media.channel_owner(cid) != _uid() and not u.get("is_admin"):
        return jsonify({"error": "권한이 없습니다."}), 403
    media.delete_channel(cid)
    return jsonify({"ok": True})


# ---- Discovery ----
@app.route("/api/discovery/categories")
def discovery_categories():
    return jsonify({"ok": True, "categories": media.MEDIA_CATEGORIES})


@app.route("/api/discovery/home")
def discovery_home():
    return jsonify({"ok": True, "data": media.discovery_home()})


@app.route("/api/discovery/search")
def discovery_search():
    res = media.discovery_search(q=request.args.get("q", "").strip(),
                                 category=request.args.get("category") or None,
                                 sort=request.args.get("sort") or "relevance")
    return jsonify({"ok": True, "promoted": res["promoted"], "channels": res["channels"]})


@app.route("/api/discovery/promotions/<int:pid>/event", methods=["POST"])
def discovery_promo_event(pid):
    d = request.get_json(silent=True) or {}
    et = d.get("event_type") or "impression"
    p = media.get_promotion(pid)
    media.log_promotion_event(pid, p["channel_id"] if p else None, _uid(), et)
    return jsonify({"ok": True})


# ---- Promotions ----
@app.route("/api/promotions/my")
@login_required
def promo_my():
    return jsonify({"ok": True, "promotions": media.list_my_promotions(_uid())})


@app.route("/api/promotions", methods=["POST"])
@login_required
def promo_create():
    d = request.get_json(silent=True) or {}
    cid = d.get("channel_id")
    title = (d.get("title") or "").strip()
    if not cid or not title:
        return jsonify({"error": "채널과 제목을 입력하세요."}), 400
    if media.channel_owner(int(cid)) != _uid():
        return jsonify({"error": "본인 채널만 홍보할 수 있습니다."}), 403
    pid = media.create_promotion(int(cid), _uid(), title,
                                 description=(d.get("description") or "").strip() or None,
                                 placement=d.get("placement") or "search_top")
    return jsonify({"ok": True, "promotion": media.get_promotion(pid)}), 201


@app.route("/api/promotions/<int:pid>/submit", methods=["POST"])
@login_required
def promo_submit(pid):
    if not media.submit_promotion(pid, _uid()):
        return jsonify({"error": "권한이 없습니다."}), 403
    return jsonify({"ok": True})


@app.route("/api/promotions/<int:pid>/pause", methods=["POST"])
@login_required
def promo_pause(pid):
    media.set_promotion_status(pid, _uid(), "paused"); return jsonify({"ok": True})


@app.route("/api/promotions/<int:pid>/resume", methods=["POST"])
@login_required
def promo_resume(pid):
    media.set_promotion_status(pid, _uid(), "approved"); return jsonify({"ok": True})


@app.route("/api/promotions/<int:pid>/stats")
@login_required
def promo_stats(pid):
    return jsonify({"ok": True, "stats": media.promotion_stats(pid)})


# ---- Articles ----
def _publish_to_board(aid):
    """기사 발행 → 게시판 피드에 글 자동 생성(통합)."""
    a = media.get_article(aid)
    if not a:
        return
    body = f"📰 [기사] {a['title']}"
    if a.get("summary"):
        body += f"\n{a['summary']}"
    body += f"\n▶ /article/{aid}"
    cat = a.get("media_category") if a.get("media_category") in CATEGORIES else "정보"
    db = get_db()
    cur = db.execute("INSERT INTO posts (user_id, category, content) VALUES (?,?,?)",
                     (a["author_id"], cat if cat in CATEGORIES else "자유", body))
    db.commit()
    media.set_article_post(aid, cur.lastrowid)


@app.route("/api/articles", methods=["POST"])
@login_required
def article_create():
    d = request.get_json(silent=True) or {}
    title = (d.get("title") or "").strip()
    if not title:
        return jsonify({"error": "기사 제목을 입력하세요."}), 400
    cid = d.get("channel_id") and int(d["channel_id"])
    if cid and media.channel_owner(cid) != _uid() and not current_user().get("is_admin"):
        return jsonify({"error": "이 채널에 발행할 권한이 없습니다."}), 403
    org_id = None
    if cid:
        ch = media.get_channel(cid)
        org_id = ch["organization_id"] if ch else None
    status = d.get("status") or "draft"
    aid = media.create_article(
        _uid(), title, channel_id=cid, organization_id=org_id,
        subtitle=d.get("subtitle"), summary=d.get("summary"), body=d.get("body"),
        source_url=d.get("source_url"), cover_image_url=d.get("cover_image_url"),
        media_category=d.get("media_category"), is_breaking=1 if d.get("is_breaking") else 0,
        status=status, tags=[t for t in (d.get("tags") or "").split(",") if t.strip()])
    if status == "published":
        _publish_to_board(aid)
    return jsonify({"ok": True, "article": media.get_article(aid)}), 201


@app.route("/api/articles/<int:aid>")
def article_get(aid):
    a = media.get_article(aid)
    if not a or a["status"] == "deleted":
        return jsonify({"error": "기사를 찾을 수 없습니다."}), 404
    if a["status"] != "published":
        u = current_user()
        if not u or (u["id"] != a["author_id"] and not u.get("is_admin")):
            return jsonify({"error": "비공개 기사입니다."}), 403
    else:
        media.increment_view(aid)
        a = media.get_article(aid)
    liked = media.article_liked(aid, _uid()) if _uid() else False
    return jsonify({"ok": True, "article": a, "liked": liked})


@app.route("/api/articles/<int:aid>", methods=["PUT"])
@login_required
def article_update(aid):
    d = request.get_json(silent=True) or {}
    if not media.update_article(aid, _uid(), **d):
        return jsonify({"error": "수정 권한이 없습니다."}), 403
    return jsonify({"ok": True, "article": media.get_article(aid)})


@app.route("/api/articles/<int:aid>/publish", methods=["POST"])
@login_required
def article_publish(aid):
    a = media.get_article(aid)
    if not a:
        return jsonify({"error": "기사를 찾을 수 없습니다."}), 404
    if a["author_id"] != _uid() and not current_user().get("is_admin"):
        return jsonify({"error": "발행 권한이 없습니다."}), 403
    media.publish_article(aid)
    if not a.get("post_id"):
        _publish_to_board(aid)
    return jsonify({"ok": True, "article": media.get_article(aid)})


@app.route("/api/articles/<int:aid>/like", methods=["POST"])
@login_required
def article_like(aid):
    liked, count = media.toggle_article_like(aid, _uid())
    return jsonify({"ok": True, "liked": liked, "like_count": count})


@app.route("/api/articles/<int:aid>/share", methods=["POST"])
@login_required
def article_share(aid):
    media.share_article(aid); return jsonify({"ok": True})


@app.route("/api/articles/<int:aid>/report", methods=["POST"])
@login_required
def article_report(aid):
    d = request.get_json(silent=True) or {}
    media.create_report(_uid(), "article", aid, d.get("reason") or "other", d.get("detail"))
    return jsonify({"ok": True})


@app.route("/api/articles")
def articles_search():
    return jsonify({"ok": True, "articles": media.search_articles(request.args.get("q", "").strip())})


@app.route("/api/articles/mine")
@login_required
def articles_mine():
    return jsonify({"ok": True, "articles": media.list_my_articles(_uid(), request.args.get("status"))})


# ---- Reports ----
@app.route("/api/reports", methods=["POST"])
@login_required
def report_create():
    d = request.get_json(silent=True) or {}
    if not d.get("target_type") or not d.get("target_id"):
        return jsonify({"error": "신고 대상이 필요합니다."}), 400
    media.create_report(_uid(), d["target_type"], int(d["target_id"]),
                        d.get("reason") or "other", d.get("detail"))
    return jsonify({"ok": True})


# ---- Admin ----
@app.route("/api/admin/summary")
@admin_required
def admin_summary():
    return jsonify({"ok": True, "summary": media.admin_summary()})


@app.route("/api/admin/users")
@admin_required
def admin_users():
    return jsonify({"ok": True, "users": media.list_all_users()})


@app.route("/api/admin/organizations")
@admin_required
def admin_orgs():
    return jsonify({"ok": True, "organizations": media.list_all_organizations()})


@app.route("/api/admin/organizations/<int:oid>/verify", methods=["POST"])
@admin_required
def admin_org_verify(oid):
    media.set_org_verification(oid, "verified"); return jsonify({"ok": True})


@app.route("/api/admin/organizations/<int:oid>/reject", methods=["POST"])
@admin_required
def admin_org_reject(oid):
    media.set_org_verification(oid, "rejected"); return jsonify({"ok": True})


@app.route("/api/admin/promotions")
@admin_required
def admin_promos():
    return jsonify({"ok": True, "promotions": media.list_pending_promotions()})


@app.route("/api/admin/promotions/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_promo_approve(pid):
    media.review_promotion(pid, _uid(), True); return jsonify({"ok": True})


@app.route("/api/admin/promotions/<int:pid>/reject", methods=["POST"])
@admin_required
def admin_promo_reject(pid):
    d = request.get_json(silent=True) or {}
    media.review_promotion(pid, _uid(), False, d.get("reason")); return jsonify({"ok": True})


@app.route("/api/admin/reports")
@admin_required
def admin_reports():
    return jsonify({"ok": True, "reports": media.list_reports(request.args.get("status", "pending"))})


@app.route("/api/admin/reports/<int:rid>/handle", methods=["POST"])
@admin_required
def admin_report_handle(rid):
    d = request.get_json(silent=True) or {}
    media.handle_report(rid, _uid(), d.get("status") or "resolved"); return jsonify({"ok": True})


if __name__ == "__main__":
    # macOS 는 5000 포트를 AirPlay 수신기가 점유하는 경우가 많아 5001 사용
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True, use_reloader=False)
