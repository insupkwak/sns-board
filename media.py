"""
media.py — 3차 고도화(미디어 기능)를 '게시판' 위에 올리는 DB 계층
- 조직(언론사/방송사/기업), 콘텐츠 채널, 채널 구독, 미디어 카테고리,
  홍보 캠페인 + 성과 이벤트, 뉴스 기사 + 통계, 신고
- 게시판과 동일한 SQLite(data/board.db) 사용. 기사 발행 시 게시판 피드에도 글 생성.
"""
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getenv("VERCEL") or os.getenv("DB_DIR"):
    DB_PATH = os.path.join(os.getenv("DB_DIR", "/tmp"), "board.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "data", "board.db")

MEDIA_CATEGORIES = ["뉴스","정치","경제","사회","국제","스포츠","연예","IT",
                    "선박","해운","금융","교육","지역","기업","커뮤니티","공지"]

CHANNEL_TYPES = {"channel", "news_channel", "discussion"}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _rows(rs): return [dict(r) for r in rs]
def _row(r): return dict(r) if r else None
def _cols(conn, t): return {r["name"] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()}
def _ensure(conn, t, col, ddl):
    if col not in _cols(conn, t):
        conn.execute(f"ALTER TABLE {t} ADD COLUMN {ddl}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, org_type TEXT DEFAULT 'media',
  description TEXT, website_url TEXT, contact_email TEXT,
  verification_status TEXT DEFAULT 'pending', verified_at TEXT,
  created_by INTEGER, created_at TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS organization_members (
  id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL, role TEXT DEFAULT 'editor', joined_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT,
  channel_type TEXT DEFAULT 'channel', visibility TEXT DEFAULT 'public',
  media_category TEXT, organization_id INTEGER, created_by INTEGER NOT NULL,
  cover_image_url TEXT, official_badge INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS channel_followers (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  followed_at TEXT NOT NULL, UNIQUE(channel_id, user_id));
CREATE TABLE IF NOT EXISTS promotions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER NOT NULL, created_by INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT, image_url TEXT, media_category TEXT,
  status TEXT DEFAULT 'draft', placement TEXT DEFAULT 'search_top', priority_score INTEGER DEFAULT 0,
  reviewed_by INTEGER, reviewed_at TEXT, rejection_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS promotion_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, promotion_id INTEGER NOT NULL, channel_id INTEGER,
  user_id INTEGER, event_type TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER, organization_id INTEGER,
  author_id INTEGER NOT NULL, post_id INTEGER, title TEXT NOT NULL, subtitle TEXT, summary TEXT,
  body TEXT, source_url TEXT, cover_image_url TEXT, status TEXT DEFAULT 'draft',
  article_type TEXT DEFAULT 'news', media_category TEXT, is_breaking INTEGER DEFAULT 0,
  is_pinned INTEGER DEFAULT 0, published_at TEXT, scheduled_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT, deleted_at TEXT);
CREATE TABLE IF NOT EXISTS article_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL, tag TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS article_stats (
  article_id INTEGER PRIMARY KEY, view_count INTEGER DEFAULT 0, like_count INTEGER DEFAULT 0,
  share_count INTEGER DEFAULT 0, report_count INTEGER DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS article_likes (
  article_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (article_id, user_id));
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER NOT NULL, target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL, reason TEXT, detail TEXT, status TEXT DEFAULT 'pending',
  handled_by INTEGER, handled_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_articles_channel ON articles(channel_id, id);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_followers_channel ON channel_followers(channel_id);
"""


def init_media_db():
    """미디어 테이블 생성 + users.is_admin/role 마이그레이션 + 기본 관리자 seed."""
    from werkzeug.security import generate_password_hash
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _conn()
    try:
        conn.executescript(SCHEMA)
        _ensure(conn, "users", "is_admin", "is_admin INTEGER DEFAULT 0")
        _ensure(conn, "users", "role", "role TEXT DEFAULT 'user'")
        conn.commit()
        # 기본 관리자 (게시판은 이메일 로그인)
        admin = conn.execute("SELECT id FROM users WHERE email='admin@board.local'").fetchone()
        if not admin:
            conn.execute("INSERT INTO users (email, nickname, password_hash, is_admin, role)"
                         " VALUES (?,?,?,1,'admin')",
                         ("admin@board.local", "관리자", generate_password_hash("admin1234")))
        else:
            conn.execute("UPDATE users SET is_admin=1, role='admin' WHERE email='admin@board.local'")
        conn.commit()
    finally:
        conn.close()


def list_media_categories():
    return list(MEDIA_CATEGORIES)


def is_admin(uid):
    conn = _conn()
    try:
        r = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        return bool(r and r["is_admin"])
    finally:
        conn.close()


# --------------------------- Organizations ---------------------------
def create_organization(name, org_type, created_by, description=None,
                        website_url=None, contact_email=None):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO organizations (name, org_type, description, website_url, contact_email,"
            " verification_status, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (name, org_type, description, website_url, contact_email, "pending", created_by, now()))
        oid = cur.lastrowid
        conn.execute("INSERT INTO organization_members (organization_id, user_id, role, joined_at)"
                     " VALUES (?,?,?,?)", (oid, created_by, "owner", now()))
        conn.execute("UPDATE users SET role='publisher' WHERE id=? AND (role IS NULL OR role='user')",
                     (created_by,))
        conn.commit()
        return oid
    finally:
        conn.close()


def get_organization(oid):
    conn = _conn()
    try:
        return _row(conn.execute("SELECT * FROM organizations WHERE id=?", (oid,)).fetchone())
    finally:
        conn.close()


def list_organizations_for_user(uid):
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT o.* FROM organizations o JOIN organization_members m ON m.organization_id=o.id"
            " WHERE m.user_id=? ORDER BY o.id DESC", (uid,)).fetchall())
    finally:
        conn.close()


def is_org_member(oid, uid):
    conn = _conn()
    try:
        return conn.execute("SELECT 1 FROM organization_members WHERE organization_id=? AND user_id=?",
                            (oid, uid)).fetchone() is not None
    finally:
        conn.close()


def request_org_verification(oid):
    conn = _conn()
    try:
        conn.execute("UPDATE organizations SET verification_status='pending', updated_at=? WHERE id=?",
                     (now(), oid)); conn.commit()
    finally:
        conn.close()


def set_org_verification(oid, status):
    conn = _conn()
    try:
        conn.execute("UPDATE organizations SET verification_status=?, verified_at=?, updated_at=? WHERE id=?",
                     (status, now() if status == "verified" else None, now(), oid))
        if status == "verified":
            conn.execute("UPDATE channels SET official_badge=1 WHERE organization_id=?", (oid,))
        conn.commit()
    finally:
        conn.close()


def list_all_organizations():
    conn = _conn()
    try:
        return _rows(conn.execute("SELECT * FROM organizations ORDER BY id DESC").fetchall())
    finally:
        conn.close()


# --------------------------- Channels ---------------------------
def create_channel(name, created_by, channel_type="channel", description=None,
                   organization_id=None, media_category=None, visibility="public"):
    if channel_type not in CHANNEL_TYPES:
        channel_type = "channel"
    conn = _conn()
    try:
        official = 0
        if organization_id:
            o = conn.execute("SELECT verification_status FROM organizations WHERE id=?",
                             (organization_id,)).fetchone()
            official = 1 if (o and o["verification_status"] == "verified") else 0
        cur = conn.execute(
            "INSERT INTO channels (name, description, channel_type, visibility, media_category,"
            " organization_id, created_by, official_badge, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, description, channel_type, visibility, media_category, organization_id,
             created_by, official, now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_channel(cid, viewer_id=None):
    conn = _conn()
    try:
        r = conn.execute("SELECT * FROM channels WHERE id=? AND is_deleted=0", (cid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["follower_count"] = conn.execute(
            "SELECT COUNT(*) c FROM channel_followers WHERE channel_id=?", (cid,)).fetchone()["c"]
        org = None
        if r["organization_id"]:
            o = conn.execute("SELECT id,name,org_type,verification_status FROM organizations WHERE id=?",
                             (r["organization_id"],)).fetchone()
            org = dict(o) if o else None
        d["organization"] = org
        d["is_following"] = False
        if viewer_id:
            d["is_following"] = conn.execute(
                "SELECT 1 FROM channel_followers WHERE channel_id=? AND user_id=?",
                (cid, viewer_id)).fetchone() is not None
        return d
    finally:
        conn.close()


def list_my_channels(uid):
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT * FROM channels WHERE created_by=? AND is_deleted=0 ORDER BY id DESC",
            (uid,)).fetchall())
    finally:
        conn.close()


def follow_channel(cid, uid, follow=True):
    conn = _conn()
    try:
        if follow:
            conn.execute("INSERT OR IGNORE INTO channel_followers (channel_id, user_id, followed_at)"
                         " VALUES (?,?,?)", (cid, uid, now()))
        else:
            conn.execute("DELETE FROM channel_followers WHERE channel_id=? AND user_id=?", (cid, uid))
        conn.commit()
        c = conn.execute("SELECT COUNT(*) c FROM channel_followers WHERE channel_id=?", (cid,)).fetchone()["c"]
        return follow, c
    finally:
        conn.close()


def delete_channel(cid):
    conn = _conn()
    try:
        conn.execute("UPDATE channels SET is_deleted=1 WHERE id=?", (cid,)); conn.commit()
    finally:
        conn.close()


def _channel_card(conn, c, promoted=False, promotion_id=None):
    fc = conn.execute("SELECT COUNT(*) c FROM channel_followers WHERE channel_id=?", (c["id"],)).fetchone()["c"]
    org = None
    if c["organization_id"]:
        o = conn.execute("SELECT name FROM organizations WHERE id=?", (c["organization_id"],)).fetchone()
        org = o["name"] if o else None
    return {
        "result_type": "promoted_channel" if promoted else "channel",
        "channel_id": c["id"], "name": c["name"], "description": c["description"],
        "channel_type": c["channel_type"], "organization_name": org,
        "official_badge": bool(c["official_badge"]), "cover_image_url": c["cover_image_url"],
        "follower_count": fc, "media_category": c["media_category"],
        "is_promoted": promoted, "sponsored_label": ("홍보" if promoted else None),
        "promotion_id": promotion_id,
    }


def discovery_search(q="", category=None, sort="relevance", limit=30):
    conn = _conn()
    try:
        promoted, seen = [], set()
        prs = conn.execute(
            "SELECT pr.id pid, ch.* FROM promotions pr JOIN channels ch ON ch.id=pr.channel_id"
            " WHERE pr.status='approved' AND ch.is_deleted=0 ORDER BY pr.priority_score DESC, pr.id DESC LIMIT 5"
        ).fetchall()
        for c in prs:
            if q and q.lower() not in ((c["name"] or "")+(c["description"] or "")).lower():
                continue
            if category and c["media_category"] != category:
                continue
            promoted.append(_channel_card(conn, c, True, c["pid"])); seen.add(c["id"])
        sql = "SELECT * FROM channels WHERE is_deleted=0 AND visibility='public'"
        params = []
        if q:
            sql += " AND (name LIKE ? OR description LIKE ?)"; params += [f"%{q}%", f"%{q}%"]
        if category:
            sql += " AND media_category=?"; params.append(category)
        sql += " ORDER BY official_badge DESC, id DESC LIMIT ?"; params.append(limit)
        rooms = [_channel_card(conn, c) for c in conn.execute(sql, params).fetchall() if c["id"] not in seen]
        if sort == "popular":
            rooms.sort(key=lambda x: x["follower_count"], reverse=True)
        return {"promoted": promoted, "channels": rooms}
    finally:
        conn.close()


def discovery_home():
    conn = _conn()
    try:
        prs = conn.execute(
            "SELECT pr.id pid, ch.* FROM promotions pr JOIN channels ch ON ch.id=pr.channel_id"
            " WHERE pr.status='approved' AND ch.is_deleted=0 ORDER BY pr.priority_score DESC LIMIT 6").fetchall()
        promoted = [_channel_card(conn, c, True, c["pid"]) for c in prs]
        official = [_channel_card(conn, c) for c in conn.execute(
            "SELECT * FROM channels WHERE official_badge=1 AND is_deleted=0 ORDER BY id DESC LIMIT 10").fetchall()]
        pop = conn.execute(
            "SELECT ch.*, (SELECT COUNT(*) FROM channel_followers f WHERE f.channel_id=ch.id) fc"
            " FROM channels ch WHERE is_deleted=0 ORDER BY fc DESC, id DESC LIMIT 10").fetchall()
        popular = [_channel_card(conn, c) for c in pop]
        latest = [_channel_card(conn, c) for c in conn.execute(
            "SELECT * FROM channels WHERE is_deleted=0 ORDER BY id DESC LIMIT 10").fetchall()]
        return {"promoted": promoted, "official": official, "popular": popular, "latest": latest}
    finally:
        conn.close()


# --------------------------- Promotions ---------------------------
def create_promotion(channel_id, created_by, title, description=None, image_url=None,
                     media_category=None, placement="search_top"):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO promotions (channel_id, created_by, title, description, image_url,"
            " media_category, status, placement, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (channel_id, created_by, title, description, image_url, media_category,
             "draft", placement, now()))
        conn.commit(); return cur.lastrowid
    finally:
        conn.close()


def get_promotion(pid):
    conn = _conn()
    try:
        return _row(conn.execute("SELECT * FROM promotions WHERE id=?", (pid,)).fetchone())
    finally:
        conn.close()


def channel_owner(cid):
    conn = _conn()
    try:
        r = conn.execute("SELECT created_by FROM channels WHERE id=?", (cid,)).fetchone()
        return r["created_by"] if r else None
    finally:
        conn.close()


def list_my_promotions(uid):
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT p.*, c.name channel_name FROM promotions p JOIN channels c ON c.id=p.channel_id"
            " WHERE p.created_by=? ORDER BY p.id DESC", (uid,)).fetchall())
    finally:
        conn.close()


def submit_promotion(pid, uid):
    conn = _conn()
    try:
        p = conn.execute("SELECT created_by FROM promotions WHERE id=?", (pid,)).fetchone()
        if not p or p["created_by"] != uid:
            return False
        conn.execute("UPDATE promotions SET status='pending_review', updated_at=? WHERE id=?", (now(), pid))
        conn.commit(); return True
    finally:
        conn.close()


def set_promotion_status(pid, uid, status):
    conn = _conn()
    try:
        p = conn.execute("SELECT created_by FROM promotions WHERE id=?", (pid,)).fetchone()
        if not p or p["created_by"] != uid:
            return False
        conn.execute("UPDATE promotions SET status=?, updated_at=? WHERE id=?", (status, now(), pid))
        conn.commit(); return True
    finally:
        conn.close()


def review_promotion(pid, reviewer, approve, reason=None):
    conn = _conn()
    try:
        conn.execute("UPDATE promotions SET status=?, reviewed_by=?, reviewed_at=?, rejection_reason=?,"
                     " priority_score=?, updated_at=? WHERE id=?",
                     ("approved" if approve else "rejected", reviewer, now(),
                      None if approve else (reason or "사유 미기재"), 100 if approve else 0, now(), pid))
        conn.commit()
    finally:
        conn.close()


def list_pending_promotions():
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT p.*, c.name channel_name FROM promotions p JOIN channels c ON c.id=p.channel_id"
            " WHERE p.status='pending_review' ORDER BY p.id").fetchall())
    finally:
        conn.close()


def log_promotion_event(pid, channel_id, uid, event_type):
    conn = _conn()
    try:
        conn.execute("INSERT INTO promotion_events (promotion_id, channel_id, user_id, event_type, created_at)"
                     " VALUES (?,?,?,?,?)", (pid, channel_id, uid, event_type, now())); conn.commit()
    finally:
        conn.close()


def promotion_stats(pid):
    conn = _conn()
    try:
        def c(t): return conn.execute("SELECT COUNT(*) c FROM promotion_events WHERE promotion_id=? AND event_type=?",
                                      (pid, t)).fetchone()["c"]
        imp, clk = c("impression"), c("click")
        return {"impression": imp, "click": clk, "ctr": round(clk/imp*100, 1) if imp else 0}
    finally:
        conn.close()


# --------------------------- Articles ---------------------------
def create_article(author_id, title, channel_id=None, organization_id=None, subtitle=None,
                   summary=None, body=None, source_url=None, cover_image_url=None,
                   media_category=None, article_type="news", status="draft", is_breaking=0,
                   scheduled_at=None, tags=None):
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO articles (channel_id, organization_id, author_id, title, subtitle, summary,"
            " body, source_url, cover_image_url, status, article_type, media_category, is_breaking,"
            " published_at, scheduled_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (channel_id, organization_id, author_id, title, subtitle, summary, body, source_url,
             cover_image_url, status, article_type, media_category, 1 if is_breaking else 0,
             now() if status == "published" else None, scheduled_at, now()))
        aid = cur.lastrowid
        conn.execute("INSERT INTO article_stats (article_id, updated_at) VALUES (?,?)", (aid, now()))
        for t in (tags or []):
            if t.strip():
                conn.execute("INSERT INTO article_tags (article_id, tag) VALUES (?,?)", (aid, t.strip()))
        conn.commit(); return aid
    finally:
        conn.close()


def get_article(aid):
    conn = _conn()
    try:
        a = conn.execute(
            "SELECT a.*, u.nickname author_name, o.name org_name, c.name channel_name"
            " FROM articles a JOIN users u ON u.id=a.author_id"
            " LEFT JOIN organizations o ON o.id=a.organization_id"
            " LEFT JOIN channels c ON c.id=a.channel_id WHERE a.id=?", (aid,)).fetchone()
        if not a:
            return None
        d = dict(a)
        d["tags"] = [t["tag"] for t in conn.execute("SELECT tag FROM article_tags WHERE article_id=?", (aid,)).fetchall()]
        s = conn.execute("SELECT * FROM article_stats WHERE article_id=?", (aid,)).fetchone()
        d["stats"] = dict(s) if s else {}
        return d
    finally:
        conn.close()


def set_article_post(aid, post_id):
    conn = _conn()
    try:
        conn.execute("UPDATE articles SET post_id=? WHERE id=?", (post_id, aid)); conn.commit()
    finally:
        conn.close()


def update_article(aid, author_id, **f):
    conn = _conn()
    try:
        a = conn.execute("SELECT author_id FROM articles WHERE id=?", (aid,)).fetchone()
        if not a or a["author_id"] != author_id:
            return False
        cols, params = [], []
        for k in ("title","subtitle","summary","body","source_url","cover_image_url",
                  "media_category","is_breaking"):
            if k in f and f[k] is not None:
                cols.append(f"{k}=?"); params.append(f[k])
        if cols:
            params += [now(), aid]
            conn.execute(f"UPDATE articles SET {', '.join(cols)}, updated_at=? WHERE id=?", params); conn.commit()
        return True
    finally:
        conn.close()


def publish_article(aid):
    conn = _conn()
    try:
        conn.execute("UPDATE articles SET status='published', published_at=?, updated_at=? WHERE id=?",
                     (now(), now(), aid)); conn.commit()
    finally:
        conn.close()


def hide_article(aid):
    conn = _conn()
    try:
        conn.execute("UPDATE articles SET status='hidden', updated_at=? WHERE id=?", (now(), aid)); conn.commit()
    finally:
        conn.close()


def list_articles_for_channel(cid, limit=20):
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT a.*, u.nickname author_name FROM articles a JOIN users u ON u.id=a.author_id"
            " WHERE a.channel_id=? AND a.status='published' ORDER BY a.is_pinned DESC, a.id DESC LIMIT ?",
            (cid, limit)).fetchall())
    finally:
        conn.close()


def list_my_articles(author_id, status=None, limit=50):
    conn = _conn()
    try:
        sql = ("SELECT a.*, c.name channel_name FROM articles a LEFT JOIN channels c ON c.id=a.channel_id"
               " WHERE a.author_id=?"); params = [author_id]
        if status:
            sql += " AND a.status=?"; params.append(status)
        sql += " ORDER BY a.id DESC LIMIT ?"; params.append(limit)
        return _rows(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_articles(q, limit=30):
    conn = _conn()
    try:
        sql = ("SELECT a.*, u.nickname author_name, o.name org_name FROM articles a"
               " JOIN users u ON u.id=a.author_id LEFT JOIN organizations o ON o.id=a.organization_id"
               " WHERE a.status='published'"); params = []
        if q:
            sql += " AND (a.title LIKE ? OR a.summary LIKE ? OR a.body LIKE ?)"; params += [f"%{q}%"]*3
        sql += " ORDER BY a.id DESC LIMIT ?"; params.append(limit)
        return _rows(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def _bump(conn, aid, field, d=1):
    conn.execute(f"UPDATE article_stats SET {field}={field}+?, updated_at=? WHERE article_id=?", (d, now(), aid))


def increment_view(aid):
    conn = _conn()
    try:
        _bump(conn, aid, "view_count"); conn.commit()
    finally:
        conn.close()


def toggle_article_like(aid, uid):
    conn = _conn()
    try:
        ex = conn.execute("SELECT 1 FROM article_likes WHERE article_id=? AND user_id=?", (aid, uid)).fetchone()
        if ex:
            conn.execute("DELETE FROM article_likes WHERE article_id=? AND user_id=?", (aid, uid)); _bump(conn, aid, "like_count", -1); liked = False
        else:
            conn.execute("INSERT INTO article_likes (article_id, user_id, created_at) VALUES (?,?,?)", (aid, uid, now())); _bump(conn, aid, "like_count", 1); liked = True
        conn.commit()
        c = conn.execute("SELECT like_count FROM article_stats WHERE article_id=?", (aid,)).fetchone()
        return liked, (c["like_count"] if c else 0)
    finally:
        conn.close()


def article_liked(aid, uid):
    conn = _conn()
    try:
        return conn.execute("SELECT 1 FROM article_likes WHERE article_id=? AND user_id=?", (aid, uid)).fetchone() is not None
    finally:
        conn.close()


def share_article(aid):
    conn = _conn()
    try:
        _bump(conn, aid, "share_count"); conn.commit()
    finally:
        conn.close()


# --------------------------- Reports ---------------------------
def create_report(reporter_id, target_type, target_id, reason, detail=None):
    conn = _conn()
    try:
        conn.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, detail, status, created_at)"
                     " VALUES (?,?,?,?,?,?,?)", (reporter_id, target_type, target_id, reason, detail, "pending", now()))
        if target_type == "article":
            _bump(conn, target_id, "report_count")
        conn.commit()
    finally:
        conn.close()


def list_reports(status="pending"):
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT r.*, u.nickname reporter FROM reports r JOIN users u ON u.id=r.reporter_id"
            " WHERE r.status=? ORDER BY r.id DESC", (status,)).fetchall())
    finally:
        conn.close()


def handle_report(rid, handler, status="resolved"):
    conn = _conn()
    try:
        conn.execute("UPDATE reports SET status=?, handled_by=?, handled_at=? WHERE id=?",
                     (status, handler, now(), rid)); conn.commit()
    finally:
        conn.close()


# --------------------------- Admin summary ---------------------------
def admin_summary():
    conn = _conn()
    try:
        def c(sql): return conn.execute(sql).fetchone()["c"]
        return {
            "users": c("SELECT COUNT(*) c FROM users"),
            "posts": c("SELECT COUNT(*) c FROM posts"),
            "organizations": c("SELECT COUNT(*) c FROM organizations"),
            "channels": c("SELECT COUNT(*) c FROM channels WHERE is_deleted=0"),
            "official_channels": c("SELECT COUNT(*) c FROM channels WHERE official_badge=1"),
            "articles": c("SELECT COUNT(*) c FROM articles WHERE status='published'"),
            "pending_promotions": c("SELECT COUNT(*) c FROM promotions WHERE status='pending_review'"),
            "pending_reports": c("SELECT COUNT(*) c FROM reports WHERE status='pending'"),
        }
    finally:
        conn.close()


def list_all_users():
    conn = _conn()
    try:
        return _rows(conn.execute(
            "SELECT id, email, nickname, is_admin, created_at FROM users ORDER BY id").fetchall())
    finally:
        conn.close()
