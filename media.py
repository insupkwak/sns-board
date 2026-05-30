"""
media.py — 3차 고도화(미디어 플랫폼) DB 계층
- 조직(언론사/방송사/기업), 공식/뉴스 채널, 채널 구독, 카테고리,
  홍보 캠페인 + 성과 이벤트, 뉴스 기사 + 통계, 신고
- 기존 SQLite(storage.py) 위에 테이블/컬럼을 마이그레이션으로 추가
"""
import storage
from storage import get_db, close_db, now, _rows, _row, _table_columns, _ensure_column

CATEGORIES = ["뉴스","정치","경제","사회","국제","스포츠","연예","IT",
              "선박","해운","금융","교육","지역","기업","커뮤니티","공지"]

CHANNEL_TYPES = {"chat","channel","news_channel","discussion","direct","notice"}


# ---------------------------------------------------------------------------
# 초기화 / 마이그레이션
# ---------------------------------------------------------------------------
MEDIA_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT,
    org_type TEXT DEFAULT 'media',
    description TEXT,
    logo_url TEXT,
    website_url TEXT,
    contact_email TEXT,
    verification_status TEXT DEFAULT 'pending',
    verified_at TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS organization_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'editor',
    joined_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS room_followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    notification_enabled INTEGER DEFAULT 1,
    followed_at TEXT NOT NULL,
    UNIQUE(room_id, user_id)
);
CREATE TABLE IF NOT EXISTS room_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT,
    parent_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS room_promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    image_url TEXT,
    target_url TEXT,
    category_id INTEGER,
    status TEXT DEFAULT 'draft',
    promotion_type TEXT DEFAULT 'free',
    placement TEXT DEFAULT 'search_top',
    start_at TEXT,
    end_at TEXT,
    priority_score INTEGER DEFAULT 0,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS promotion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promotion_id INTEGER NOT NULL,
    room_id INTEGER,
    user_id INTEGER,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER,
    organization_id INTEGER,
    author_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    subtitle TEXT,
    summary TEXT,
    body TEXT,
    source_url TEXT,
    cover_image_url TEXT,
    status TEXT DEFAULT 'draft',
    article_type TEXT DEFAULT 'news',
    category_id INTEGER,
    is_breaking INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    is_comments_enabled INTEGER DEFAULT 1,
    published_at TEXT,
    scheduled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS article_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    tag TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS article_stats (
    article_id INTEGER PRIMARY KEY,
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    report_count INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS article_likes (
    article_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (article_id, user_id)
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    reason TEXT,
    detail TEXT,
    status TEXT DEFAULT 'pending',
    handled_by INTEGER,
    handled_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_room ON articles(room_id, id);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status, published_at);
CREATE INDEX IF NOT EXISTS idx_followers_room ON room_followers(room_id);
CREATE INDEX IF NOT EXISTS idx_promotions_status ON room_promotions(status);
"""


def init_media_db():
    conn = get_db()
    try:
        conn.executescript(MEDIA_SCHEMA)
        # rooms 컬럼 확장
        _ensure_column(conn, "rooms", "slug", "slug TEXT")
        _ensure_column(conn, "rooms", "visibility", "visibility TEXT DEFAULT 'public'")
        _ensure_column(conn, "rooms", "category_id", "category_id INTEGER")
        _ensure_column(conn, "rooms", "organization_id", "organization_id INTEGER")
        _ensure_column(conn, "rooms", "cover_image_url", "cover_image_url TEXT")
        _ensure_column(conn, "rooms", "official_badge", "official_badge INTEGER DEFAULT 0")
        _ensure_column(conn, "rooms", "is_promotable", "is_promotable INTEGER DEFAULT 1")
        _ensure_column(conn, "rooms", "is_deleted", "is_deleted INTEGER DEFAULT 0")
        # messages 컬럼 확장(기사 공유 메시지)
        _ensure_column(conn, "messages", "content_type", "content_type TEXT DEFAULT 'text'")
        _ensure_column(conn, "messages", "article_id", "article_id INTEGER")
        # users 컬럼(역할/이메일/인증) — 선택
        _ensure_column(conn, "users", "email", "email TEXT")
        _ensure_column(conn, "users", "role", "role TEXT DEFAULT 'user'")
        conn.commit()
        # 카테고리 seed
        cnt = conn.execute("SELECT COUNT(*) c FROM room_categories").fetchone()["c"]
        if cnt == 0:
            for i, name in enumerate(CATEGORIES):
                conn.execute("INSERT INTO room_categories (name, slug, sort_order, is_active)"
                             " VALUES (?,?,?,1)", (name, name, i))
            conn.commit()
    finally:
        close_db(conn)


def list_categories():
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT * FROM room_categories WHERE is_active=1 ORDER BY sort_order").fetchall())
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------
def create_organization(name, org_type, created_by, description=None,
                        website_url=None, contact_email=None):
    conn = get_db()
    try:
        slug = (name or "").strip().lower().replace(" ", "-")
        cur = conn.execute(
            "INSERT INTO organizations (name, slug, org_type, description, website_url,"
            " contact_email, verification_status, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (name, slug, org_type, description, website_url, contact_email,
             "pending", created_by, now()))
        oid = cur.lastrowid
        conn.execute("INSERT INTO organization_members (organization_id, user_id, role,"
                     " joined_at) VALUES (?,?,?,?)", (oid, created_by, "owner", now()))
        # 사용자 role 승격
        conn.execute("UPDATE users SET role='publisher' WHERE id=? AND role='user'",
                     (created_by,))
        conn.commit()
        return oid
    finally:
        close_db(conn)


def get_organization(oid):
    conn = get_db()
    try:
        return _row(conn.execute("SELECT * FROM organizations WHERE id=?", (oid,)).fetchone())
    finally:
        close_db(conn)


def list_organizations_for_user(uid):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT o.* FROM organizations o JOIN organization_members m"
            " ON m.organization_id=o.id WHERE m.user_id=? ORDER BY o.id DESC",
            (uid,)).fetchall())
    finally:
        close_db(conn)


def request_org_verification(oid):
    conn = get_db()
    try:
        conn.execute("UPDATE organizations SET verification_status='pending', updated_at=?"
                     " WHERE id=?", (now(), oid))
        conn.commit()
    finally:
        close_db(conn)


def set_org_verification(oid, status, official_badge_rooms=False):
    conn = get_db()
    try:
        conn.execute("UPDATE organizations SET verification_status=?, verified_at=?,"
                     " updated_at=? WHERE id=?",
                     (status, now() if status == "verified" else None, now(), oid))
        if status == "verified":
            conn.execute("UPDATE rooms SET official_badge=1 WHERE organization_id=?", (oid,))
        conn.commit()
    finally:
        close_db(conn)


def is_org_member(oid, uid):
    conn = get_db()
    try:
        return conn.execute("SELECT 1 FROM organization_members WHERE organization_id=?"
                            " AND user_id=?", (oid, uid)).fetchone() is not None
    finally:
        close_db(conn)


def add_org_member(oid, uid, role="editor"):
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM organization_members WHERE organization_id=?"
                            " AND user_id=?", (oid, uid)).fetchone():
            conn.execute("INSERT INTO organization_members (organization_id, user_id, role,"
                         " joined_at) VALUES (?,?,?,?)", (oid, uid, role, now()))
            conn.commit()
    finally:
        close_db(conn)


def list_org_members(oid):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT u.id, u.username, u.user_id, m.role FROM organization_members m"
            " JOIN users u ON u.id=m.user_id WHERE m.organization_id=?", (oid,)).fetchall())
    finally:
        close_db(conn)


def list_all_organizations():
    conn = get_db()
    try:
        return _rows(conn.execute("SELECT * FROM organizations ORDER BY id DESC").fetchall())
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Channels (rooms 확장)
# ---------------------------------------------------------------------------
def create_channel(name, created_by, room_type="channel", description=None,
                   organization_id=None, category_id=None, visibility="public"):
    if room_type not in CHANNEL_TYPES:
        room_type = "channel"
    conn = get_db()
    try:
        slug = (name or "").strip().lower().replace(" ", "-")
        official = 0
        if organization_id:
            org = conn.execute("SELECT verification_status FROM organizations WHERE id=?",
                               (organization_id,)).fetchone()
            official = 1 if (org and org["verification_status"] == "verified") else 0
        cur = conn.execute(
            "INSERT INTO rooms (name, slug, description, room_type, visibility, category_id,"
            " organization_id, created_by, cover_image_url, official_badge, is_promotable,"
            " is_notice, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, slug, description, room_type, visibility, category_id, organization_id,
             created_by, None, official, 1, 1 if room_type == "notice" else 0, now()))
        rid = cur.lastrowid
        conn.execute("INSERT INTO room_members (room_id, user_id, role, joined_at)"
                     " VALUES (?,?,?,?)", (rid, created_by, "owner", now()))
        conn.commit()
        return rid
    finally:
        close_db(conn)


def follow_room(room_id, user_id):
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO room_followers (room_id, user_id, followed_at)"
                     " VALUES (?,?,?)", (room_id, user_id, now()))
        # 구독자도 멤버로 추가(채널 입장 가능)
        if not conn.execute("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
                            (room_id, user_id)).fetchone():
            conn.execute("INSERT INTO room_members (room_id, user_id, role, joined_at)"
                         " VALUES (?,?,?,?)", (room_id, user_id, "viewer", now()))
        conn.commit()
    finally:
        close_db(conn)


def unfollow_room(room_id, user_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM room_followers WHERE room_id=? AND user_id=?",
                     (room_id, user_id))
        conn.commit()
    finally:
        close_db(conn)


def is_following(room_id, user_id):
    conn = get_db()
    try:
        return conn.execute("SELECT 1 FROM room_followers WHERE room_id=? AND user_id=?",
                            (room_id, user_id)).fetchone() is not None
    finally:
        close_db(conn)


def follower_count(room_id):
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) c FROM room_followers WHERE room_id=?",
                            (room_id,)).fetchone()["c"]
    finally:
        close_db(conn)


def get_channel_full(room_id, viewer_id=None):
    conn = get_db()
    try:
        r = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["follower_count"] = conn.execute(
            "SELECT COUNT(*) c FROM room_followers WHERE room_id=?", (room_id,)).fetchone()["c"]
        d["member_count"] = conn.execute(
            "SELECT COUNT(*) c FROM room_members WHERE room_id=?", (room_id,)).fetchone()["c"]
        org = None
        if r["organization_id"]:
            o = conn.execute("SELECT id,name,org_type,verification_status FROM organizations"
                             " WHERE id=?", (r["organization_id"],)).fetchone()
            org = dict(o) if o else None
        d["organization"] = org
        cat = None
        if r["category_id"]:
            c = conn.execute("SELECT name FROM room_categories WHERE id=?",
                             (r["category_id"],)).fetchone()
            cat = c["name"] if c else None
        d["category"] = cat
        d["is_following"] = (is_following(room_id, viewer_id) if viewer_id else False)
        return d
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Discovery (검색 / 추천)
# ---------------------------------------------------------------------------
def _room_card(conn, r, promoted=False, promotion_id=None):
    fc = conn.execute("SELECT COUNT(*) c FROM room_followers WHERE room_id=?",
                      (r["id"],)).fetchone()["c"]
    org_name = None
    if r["organization_id"]:
        o = conn.execute("SELECT name FROM organizations WHERE id=?",
                         (r["organization_id"],)).fetchone()
        org_name = o["name"] if o else None
    cat = None
    if r["category_id"]:
        c = conn.execute("SELECT name FROM room_categories WHERE id=?",
                         (r["category_id"],)).fetchone()
        cat = c["name"] if c else None
    return {
        "result_type": "promoted_room" if promoted else "room",
        "room_id": r["id"], "name": r["name"], "description": r["description"],
        "room_type": r["room_type"], "organization_name": org_name,
        "official_badge": bool(r["official_badge"]), "cover_image_url": r["cover_image_url"],
        "follower_count": fc, "category": cat,
        "is_promoted": promoted, "sponsored_label": ("홍보" if promoted else None),
        "promotion_id": promotion_id,
    }


def _active_promoted_rooms(conn, limit=10, category_id=None):
    sql = ("SELECT p.id pid, r.* FROM room_promotions p JOIN rooms r ON r.id=p.room_id"
           " WHERE p.status='approved' AND r.is_deleted IS NOT 1")
    params = []
    if category_id:
        sql += " AND r.category_id=?"
        params.append(category_id)
    sql += " ORDER BY p.priority_score DESC, p.id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def discovery_search(q="", category_id=None, room_type=None, sort="relevance", limit=30):
    conn = get_db()
    try:
        promoted_cards = []
        seen = set()
        # 홍보 결과(상단) — 검색어/카테고리 매칭
        for pr in _active_promoted_rooms(conn, limit=5, category_id=category_id):
            if q and q.lower() not in ((pr["name"] or "")+(pr["description"] or "")).lower():
                continue
            promoted_cards.append(_room_card(conn, pr, promoted=True, promotion_id=pr["pid"]))
            seen.add(pr["id"])

        sql = ("SELECT * FROM rooms WHERE visibility='public' AND is_deleted IS NOT 1"
               " AND room_type IN ('channel','news_channel','discussion','chat','notice')")
        params = []
        if q:
            sql += " AND (name LIKE ? OR description LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        if category_id:
            sql += " AND category_id=?"; params.append(category_id)
        if room_type:
            sql += " AND room_type=?"; params.append(room_type)
        # 정렬
        if sort == "new":
            sql += " ORDER BY id DESC"
        elif sort == "official":
            sql += " ORDER BY official_badge DESC, id DESC"
        else:  # relevance/popular/active → 구독자/공식 우선 근사
            sql += " ORDER BY official_badge DESC, id DESC"
        sql += " LIMIT ?"; params.append(limit)
        rooms = conn.execute(sql, params).fetchall()
        cards = [_room_card(conn, r) for r in rooms if r["id"] not in seen]
        if sort == "popular":
            cards.sort(key=lambda x: x["follower_count"], reverse=True)
        return {"promoted": promoted_cards, "rooms": cards}
    finally:
        close_db(conn)


def discovery_home():
    conn = get_db()
    try:
        promoted = [_room_card(conn, r, promoted=True, promotion_id=r["pid"])
                    for r in _active_promoted_rooms(conn, limit=6)]
        official = [_room_card(conn, r) for r in conn.execute(
            "SELECT * FROM rooms WHERE official_badge=1 AND visibility='public'"
            " AND is_deleted IS NOT 1 ORDER BY id DESC LIMIT 10").fetchall()]
        # 인기 = 구독자수 상위
        pop_rows = conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM room_followers f WHERE f.room_id=r.id) fc"
            " FROM rooms r WHERE visibility='public' AND is_deleted IS NOT 1"
            " AND room_type IN ('channel','news_channel','discussion')"
            " ORDER BY fc DESC, id DESC LIMIT 10").fetchall()
        popular = [_room_card(conn, r) for r in pop_rows]
        latest = [_room_card(conn, r) for r in conn.execute(
            "SELECT * FROM rooms WHERE visibility='public' AND is_deleted IS NOT 1"
            " AND room_type IN ('channel','news_channel','discussion')"
            " ORDER BY id DESC LIMIT 10").fetchall()]
        return {"promoted": promoted, "official": official,
                "popular": popular, "latest": latest}
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------
def create_promotion(room_id, created_by, title, description=None, image_url=None,
                     target_url=None, category_id=None, placement="search_top",
                     start_at=None, end_at=None):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO room_promotions (room_id, created_by, title, description, image_url,"
            " target_url, category_id, status, placement, start_at, end_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (room_id, created_by, title, description, image_url, target_url, category_id,
             "draft", placement, start_at, end_at, now()))
        conn.commit()
        return cur.lastrowid
    finally:
        close_db(conn)


def get_promotion(pid):
    conn = get_db()
    try:
        return _row(conn.execute("SELECT * FROM room_promotions WHERE id=?", (pid,)).fetchone())
    finally:
        close_db(conn)


def list_my_promotions(uid):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT p.*, r.name room_name FROM room_promotions p JOIN rooms r ON r.id=p.room_id"
            " WHERE p.created_by=? ORDER BY p.id DESC", (uid,)).fetchall())
    finally:
        close_db(conn)


def submit_promotion(pid, uid):
    conn = get_db()
    try:
        p = conn.execute("SELECT * FROM room_promotions WHERE id=?", (pid,)).fetchone()
        if not p or p["created_by"] != uid:
            return False
        conn.execute("UPDATE room_promotions SET status='pending_review', updated_at=?"
                     " WHERE id=?", (now(), pid))
        conn.commit()
        return True
    finally:
        close_db(conn)


def review_promotion(pid, reviewer_id, approve, reason=None):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE room_promotions SET status=?, reviewed_by=?, reviewed_at=?,"
            " rejection_reason=?, priority_score=?, updated_at=? WHERE id=?",
            ("approved" if approve else "rejected", reviewer_id, now(),
             None if approve else (reason or "사유 미기재"),
             100 if approve else 0, now(), pid))
        conn.commit()
    finally:
        close_db(conn)


def set_promotion_status(pid, uid, status):
    conn = get_db()
    try:
        p = conn.execute("SELECT created_by FROM room_promotions WHERE id=?", (pid,)).fetchone()
        if not p or p["created_by"] != uid:
            return False
        conn.execute("UPDATE room_promotions SET status=?, updated_at=? WHERE id=?",
                     (status, now(), pid))
        conn.commit()
        return True
    finally:
        close_db(conn)


def list_pending_promotions():
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT p.*, r.name room_name FROM room_promotions p JOIN rooms r ON r.id=p.room_id"
            " WHERE p.status='pending_review' ORDER BY p.id").fetchall())
    finally:
        close_db(conn)


def log_promotion_event(promotion_id, room_id, user_id, event_type):
    conn = get_db()
    try:
        conn.execute("INSERT INTO promotion_events (promotion_id, room_id, user_id,"
                     " event_type, created_at) VALUES (?,?,?,?,?)",
                     (promotion_id, room_id, user_id, event_type, now()))
        conn.commit()
    finally:
        close_db(conn)


def promotion_stats(pid):
    conn = get_db()
    try:
        def cnt(t): return conn.execute(
            "SELECT COUNT(*) c FROM promotion_events WHERE promotion_id=? AND event_type=?",
            (pid, t)).fetchone()["c"]
        imp, clk, joi, fol = cnt("impression"), cnt("click"), cnt("join"), cnt("follow")
        ctr = round(clk/imp*100, 1) if imp else 0
        return {"impression": imp, "click": clk, "join": joi, "follow": fol, "ctr": ctr}
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------
def create_article(author_id, title, room_id=None, organization_id=None, subtitle=None,
                   summary=None, body=None, source_url=None, cover_image_url=None,
                   category_id=None, article_type="news", status="draft",
                   is_breaking=0, scheduled_at=None, tags=None):
    conn = get_db()
    try:
        published_at = now() if status == "published" else None
        cur = conn.execute(
            "INSERT INTO articles (room_id, organization_id, author_id, title, subtitle,"
            " summary, body, source_url, cover_image_url, status, article_type, category_id,"
            " is_breaking, published_at, scheduled_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (room_id, organization_id, author_id, title, subtitle, summary, body, source_url,
             cover_image_url, status, article_type, category_id, 1 if is_breaking else 0,
             published_at, scheduled_at, now()))
        aid = cur.lastrowid
        conn.execute("INSERT INTO article_stats (article_id, updated_at) VALUES (?,?)",
                     (aid, now()))
        for t in (tags or []):
            t = (t or "").strip()
            if t:
                conn.execute("INSERT INTO article_tags (article_id, tag) VALUES (?,?)", (aid, t))
        conn.commit()
        return aid
    finally:
        close_db(conn)


def get_article(aid, with_stats=True):
    conn = get_db()
    try:
        a = conn.execute(
            "SELECT a.*, u.username author_name, o.name org_name,"
            " c.name category_name, r.name room_name FROM articles a"
            " JOIN users u ON u.id=a.author_id"
            " LEFT JOIN organizations o ON o.id=a.organization_id"
            " LEFT JOIN room_categories c ON c.id=a.category_id"
            " LEFT JOIN rooms r ON r.id=a.room_id WHERE a.id=?", (aid,)).fetchone()
        if not a:
            return None
        d = dict(a)
        d["tags"] = [t["tag"] for t in conn.execute(
            "SELECT tag FROM article_tags WHERE article_id=?", (aid,)).fetchall()]
        if with_stats:
            s = conn.execute("SELECT * FROM article_stats WHERE article_id=?", (aid,)).fetchone()
            d["stats"] = dict(s) if s else {}
        return d
    finally:
        close_db(conn)


def update_article(aid, author_id, **fields):
    conn = get_db()
    try:
        a = conn.execute("SELECT author_id, status FROM articles WHERE id=?", (aid,)).fetchone()
        if not a or a["author_id"] != author_id:
            return False
        cols, params = [], []
        for k in ("title","subtitle","summary","body","source_url","cover_image_url",
                  "category_id","article_type","is_breaking","scheduled_at"):
            if k in fields and fields[k] is not None:
                cols.append(f"{k}=?"); params.append(fields[k])
        if cols:
            params += [now(), aid]
            conn.execute(f"UPDATE articles SET {', '.join(cols)}, updated_at=? WHERE id=?", params)
            conn.commit()
        return True
    finally:
        close_db(conn)


def publish_article(aid, status="published"):
    conn = get_db()
    try:
        conn.execute("UPDATE articles SET status=?, published_at=?, updated_at=? WHERE id=?",
                     (status, now() if status == "published" else None, now(), aid))
        conn.commit()
    finally:
        close_db(conn)


def hide_article(aid):
    conn = get_db()
    try:
        conn.execute("UPDATE articles SET status='hidden', updated_at=? WHERE id=?", (now(), aid))
        conn.commit()
    finally:
        close_db(conn)


def list_articles_for_room(room_id, limit=20, cursor=None):
    conn = get_db()
    try:
        sql = ("SELECT a.*, u.username author_name FROM articles a JOIN users u ON u.id=a.author_id"
               " WHERE a.room_id=? AND a.status='published'")
        params = [room_id]
        if cursor:
            sql += " AND a.id < ?"; params.append(cursor)
        sql += " ORDER BY a.is_pinned DESC, a.id DESC LIMIT ?"; params.append(limit)
        rows = _rows(conn.execute(sql, params).fetchall())
        return rows
    finally:
        close_db(conn)


def list_my_articles(author_id, status=None, limit=50):
    conn = get_db()
    try:
        sql = ("SELECT a.*, r.name room_name FROM articles a LEFT JOIN rooms r ON r.id=a.room_id"
               " WHERE a.author_id=?")
        params = [author_id]
        if status:
            sql += " AND a.status=?"; params.append(status)
        sql += " ORDER BY a.id DESC LIMIT ?"; params.append(limit)
        return _rows(conn.execute(sql, params).fetchall())
    finally:
        close_db(conn)


def search_articles(q, limit=30, cursor=None):
    conn = get_db()
    try:
        sql = ("SELECT a.*, u.username author_name, o.name org_name FROM articles a"
               " JOIN users u ON u.id=a.author_id LEFT JOIN organizations o"
               " ON o.id=a.organization_id WHERE a.status='published'")
        params = []
        if q:
            sql += " AND (a.title LIKE ? OR a.summary LIKE ? OR a.body LIKE ?)"
            params += [f"%{q}%", f"%{q}%", f"%{q}%"]
        if cursor:
            sql += " AND a.id < ?"; params.append(cursor)
        sql += " ORDER BY a.id DESC LIMIT ?"; params.append(limit)
        return _rows(conn.execute(sql, params).fetchall())
    finally:
        close_db(conn)


def _bump_stat(conn, aid, field, delta=1):
    conn.execute(f"UPDATE article_stats SET {field}={field}+?, updated_at=? WHERE article_id=?",
                 (delta, now(), aid))


def increment_view(aid):
    conn = get_db()
    try:
        _bump_stat(conn, aid, "view_count"); conn.commit()
    finally:
        close_db(conn)


def toggle_like(aid, uid):
    conn = get_db()
    try:
        ex = conn.execute("SELECT 1 FROM article_likes WHERE article_id=? AND user_id=?",
                          (aid, uid)).fetchone()
        if ex:
            conn.execute("DELETE FROM article_likes WHERE article_id=? AND user_id=?", (aid, uid))
            _bump_stat(conn, aid, "like_count", -1); liked = False
        else:
            conn.execute("INSERT INTO article_likes (article_id, user_id, created_at)"
                         " VALUES (?,?,?)", (aid, uid, now()))
            _bump_stat(conn, aid, "like_count", 1); liked = True
        conn.commit()
        c = conn.execute("SELECT like_count FROM article_stats WHERE article_id=?",
                         (aid,)).fetchone()
        return liked, (c["like_count"] if c else 0)
    finally:
        close_db(conn)


def share_article(aid):
    conn = get_db()
    try:
        _bump_stat(conn, aid, "share_count"); conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def create_report(reporter_id, target_type, target_id, reason, detail=None):
    conn = get_db()
    try:
        conn.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason, detail,"
                     " status, created_at) VALUES (?,?,?,?,?,?,?)",
                     (reporter_id, target_type, target_id, reason, detail, "pending", now()))
        if target_type == "article":
            _bump_stat(conn, target_id, "report_count")
        conn.commit()
    finally:
        close_db(conn)


def list_reports(status="pending"):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT r.*, u.username reporter FROM reports r JOIN users u ON u.id=r.reporter_id"
            " WHERE r.status=? ORDER BY r.id DESC", (status,)).fetchall())
    finally:
        close_db(conn)


def handle_report(report_id, handler_id, status="resolved"):
    conn = get_db()
    try:
        conn.execute("UPDATE reports SET status=?, handled_by=?, handled_at=? WHERE id=?",
                     (status, handler_id, now(), report_id))
        conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Admin summary 확장
# ---------------------------------------------------------------------------
def admin_media_summary():
    conn = get_db()
    try:
        def c(sql, *p): return conn.execute(sql, p).fetchone()["c"]
        return {
            "organizations": c("SELECT COUNT(*) c FROM organizations"),
            "official_rooms": c("SELECT COUNT(*) c FROM rooms WHERE official_badge=1"),
            "pending_promotions": c("SELECT COUNT(*) c FROM room_promotions WHERE status='pending_review'"),
            "pending_reports": c("SELECT COUNT(*) c FROM reports WHERE status='pending'"),
            "articles": c("SELECT COUNT(*) c FROM articles WHERE status='published'"),
        }
    finally:
        close_db(conn)
