"""
storage.py — DB 계층 (SQLite)
- 모든 DB 함수와 마이그레이션을 이곳에 모음
- 스레드/소켓 환경에서도 안전하도록 호출마다 짧은 커넥션을 연다
"""
import os
import sqlite3
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 서버리스(Vercel)는 파일시스템이 읽기전용 → /tmp 사용. 그 외엔 instance/sns.db
if os.getenv("VERCEL") or os.getenv("DB_DIR"):
    INSTANCE_DIR = os.getenv("DB_DIR", "/tmp")
else:
    INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

DB_PATH = os.path.join(INSTANCE_DIR, "sns.db")

GENERAL_ROOM_NAME = "General"


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    """새 커넥션 반환(호출 측에서 close). 대부분은 아래 _conn() 내부 헬퍼 사용."""
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_db(conn):
    try:
        conn.close()
    except Exception:
        pass


def _rows(rows):
    return [dict(r) for r in rows]


def _row(row):
    return dict(row) if row else None


def _table_columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn, table, column, ddl):
    """컬럼이 없으면 ALTER TABLE 로 추가(마이그레이션)."""
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


# ---------------------------------------------------------------------------
# 초기화 + 마이그레이션
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    user_id TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    profile_image TEXT,
    status_message TEXT,
    is_admin INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    room_type TEXT DEFAULT 'group',
    created_by INTEGER,
    is_notice INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS room_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member',
    is_pinned INTEGER DEFAULT 0,
    is_favorite INTEGER DEFAULT 0,
    last_read_message_id INTEGER DEFAULT 0,
    joined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS direct_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT,
    attachment_id INTEGER,
    reply_to_id INTEGER,
    is_edited INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_name TEXT NOT NULL,
    saved_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_type TEXT,
    file_size INTEGER,
    uploaded_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    room_id INTEGER,
    message_id INTEGER,
    title TEXT,
    body TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id, id);
CREATE INDEX IF NOT EXISTS idx_members_user ON room_members(user_id);
CREATE INDEX IF NOT EXISTS idx_members_room ON room_members(room_id);
"""


def init_db():
    """테이블 생성 + 누락 컬럼 마이그레이션 + 기본 데이터(General/관리자) 보장."""
    from werkzeug.security import generate_password_hash

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)

        # --- 마이그레이션: 기존 DB 에 누락 컬럼 추가 ---
        _ensure_column(conn, "users", "profile_image", "profile_image TEXT")
        _ensure_column(conn, "users", "status_message", "status_message TEXT")
        _ensure_column(conn, "users", "is_admin", "is_admin INTEGER DEFAULT 0")
        _ensure_column(conn, "users", "is_active", "is_active INTEGER DEFAULT 1")
        _ensure_column(conn, "users", "updated_at", "updated_at TEXT")

        _ensure_column(conn, "rooms", "description", "description TEXT")
        _ensure_column(conn, "rooms", "room_type", "room_type TEXT DEFAULT 'group'")
        _ensure_column(conn, "rooms", "is_notice", "is_notice INTEGER DEFAULT 0")
        _ensure_column(conn, "rooms", "updated_at", "updated_at TEXT")

        for col, ddl in [
            ("attachment_id", "attachment_id INTEGER"),
            ("reply_to_id", "reply_to_id INTEGER"),
            ("is_edited", "is_edited INTEGER DEFAULT 0"),
            ("is_deleted", "is_deleted INTEGER DEFAULT 0"),
            ("is_pinned", "is_pinned INTEGER DEFAULT 0"),
            ("updated_at", "updated_at TEXT"),
        ]:
            _ensure_column(conn, "messages", col, ddl)

        conn.commit()

        # --- 기본 관리자 계정 ---
        admin = conn.execute(
            "SELECT id FROM users WHERE user_id = 'admin'"
        ).fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (username, user_id, password_hash, status_message,"
                " is_admin, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
                ("Administrator", "admin",
                 generate_password_hash("admin1234"),
                 "Available", 1, 1, now()),
            )
            conn.commit()

        # --- General 방 자동 생성 + 모든 사용자 멤버십 보장 ---
        general = conn.execute(
            "SELECT id FROM rooms WHERE name = ? AND room_type = 'group'",
            (GENERAL_ROOM_NAME,),
        ).fetchone()
        if not general:
            cur = conn.execute(
                "INSERT INTO rooms (name, description, room_type, created_by,"
                " is_notice, created_at) VALUES (?,?,?,?,?,?)",
                (GENERAL_ROOM_NAME, "기본 공개 채팅방", "group", None, 0, now()),
            )
            general_id = cur.lastrowid
            conn.commit()
        else:
            general_id = general["id"]

        # General 방에 모든 사용자 자동 가입(없으면)
        users = conn.execute("SELECT id FROM users").fetchall()
        for u in users:
            exists = conn.execute(
                "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
                (general_id, u["id"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO room_members (room_id, user_id, role, joined_at)"
                    " VALUES (?,?,?,?)",
                    (general_id, u["id"], "member", now()),
                )
        conn.commit()
    finally:
        close_db(conn)


def get_general_room_id():
    conn = get_db()
    try:
        r = conn.execute(
            "SELECT id FROM rooms WHERE name=? AND room_type='group' ORDER BY id LIMIT 1",
            (GENERAL_ROOM_NAME,),
        ).fetchone()
        return r["id"] if r else None
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def create_user(username, user_id, password):
    from werkzeug.security import generate_password_hash
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, user_id, password_hash, status_message,"
            " is_admin, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
            (username, user_id, generate_password_hash(password),
             "Available", 0, 1, now()),
        )
        conn.commit()
        new_id = cur.lastrowid
        # 신규 사용자도 General 방에 자동 가입
        gid = conn.execute(
            "SELECT id FROM rooms WHERE name=? AND room_type='group' ORDER BY id LIMIT 1",
            (GENERAL_ROOM_NAME,),
        ).fetchone()
        if gid:
            conn.execute(
                "INSERT INTO room_members (room_id, user_id, role, joined_at)"
                " VALUES (?,?,?,?)",
                (gid["id"], new_id, "member", now()),
            )
            conn.commit()
        return new_id
    finally:
        close_db(conn)


def get_user_by_user_id(user_id):
    conn = get_db()
    try:
        return _row(conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())
    finally:
        close_db(conn)


def get_user_by_id(uid):
    conn = get_db()
    try:
        return _row(conn.execute(
            "SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    finally:
        close_db(conn)


def search_users(keyword, include_inactive=False):
    conn = get_db()
    try:
        kw = f"%{(keyword or '').strip()}%"
        sql = ("SELECT id, username, user_id, profile_image, status_message,"
               " is_admin, is_active FROM users"
               " WHERE (username LIKE ? OR user_id LIKE ?)")
        if not include_inactive:
            sql += " AND is_active = 1"
        sql += " ORDER BY username LIMIT 30"
        return _rows(conn.execute(sql, (kw, kw)).fetchall())
    finally:
        close_db(conn)


def update_user_profile(uid, username, status_message, profile_image=None):
    conn = get_db()
    try:
        if profile_image is not None:
            conn.execute(
                "UPDATE users SET username=?, status_message=?, profile_image=?,"
                " updated_at=? WHERE id=?",
                (username, status_message, profile_image, now(), uid))
        else:
            conn.execute(
                "UPDATE users SET username=?, status_message=?, updated_at=? WHERE id=?",
                (username, status_message, now(), uid))
        conn.commit()
    finally:
        close_db(conn)


def set_user_active(uid, is_active):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET is_active=?, updated_at=? WHERE id=?",
                     (1 if is_active else 0, now(), uid))
        conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
def create_room(name, created_by, description=None, room_type="group", is_notice=0):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO rooms (name, description, room_type, created_by, is_notice,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (name, description, room_type, created_by, is_notice, now()))
        rid = cur.lastrowid
        if created_by:
            conn.execute(
                "INSERT INTO room_members (room_id, user_id, role, joined_at)"
                " VALUES (?,?,?,?)", (rid, created_by, "owner", now()))
        conn.commit()
        return rid
    finally:
        close_db(conn)


def get_room(room_id):
    conn = get_db()
    try:
        return _row(conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone())
    finally:
        close_db(conn)


def _room_display_name(conn, room, viewer_id):
    """1:1 방은 상대방 이름으로 표시."""
    if room["room_type"] == "direct":
        other = conn.execute(
            "SELECT u.username FROM room_members m JOIN users u ON u.id=m.user_id"
            " WHERE m.room_id=? AND m.user_id<>? LIMIT 1",
            (room["id"], viewer_id)).fetchone()
        if other:
            return other["username"]
    return room["name"]


def get_rooms_for_user(user_id, keyword=None):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT r.*, m.is_pinned, m.is_favorite, m.last_read_message_id"
            " FROM rooms r JOIN room_members m ON m.room_id=r.id"
            " WHERE m.user_id=?", (user_id,)).fetchall()
        result = []
        for r in rows:
            name = _room_display_name(conn, r, user_id)
            if keyword:
                if (keyword.strip().lower() not in (name or "").lower()):
                    continue
            last = conn.execute(
                "SELECT m.*, u.username FROM messages m JOIN users u ON u.id=m.user_id"
                " WHERE m.room_id=? ORDER BY m.id DESC LIMIT 1", (r["id"],)).fetchone()
            unread = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE room_id=? AND id>? AND user_id<>?",
                (r["id"], r["last_read_message_id"] or 0, user_id)).fetchone()["c"]
            if last:
                if last["is_deleted"]:
                    preview = "삭제된 메시지"
                elif last["content"]:
                    preview = last["content"]
                elif last["attachment_id"]:
                    preview = "[첨부파일]"
                else:
                    preview = ""
                last_time = last["created_at"]
                last_id = last["id"]
            else:
                preview, last_time, last_id = "", r["created_at"], 0
            result.append({
                "id": r["id"], "name": name, "description": r["description"],
                "room_type": r["room_type"], "is_notice": r["is_notice"],
                "last_message": preview, "last_time": last_time, "last_id": last_id,
                "unread_count": unread,
                "is_pinned": r["is_pinned"], "is_favorite": r["is_favorite"],
            })
        # 정렬: 고정 우선 → 마지막 메시지 최신 → 생성 최신
        result.sort(key=lambda x: (
            -(x["is_pinned"] or 0), x["last_time"] or "", x["last_id"]), reverse=True)
        return result
    finally:
        close_db(conn)


def search_rooms_for_user(user_id, keyword):
    return get_rooms_for_user(user_id, keyword=keyword)


def update_room(room_id, name=None, description=None):
    conn = get_db()
    try:
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if not room:
            return
        conn.execute(
            "UPDATE rooms SET name=?, description=?, updated_at=? WHERE id=?",
            (name if name is not None else room["name"],
             description if description is not None else room["description"],
             now(), room_id))
        conn.commit()
    finally:
        close_db(conn)


def delete_room(room_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM room_members WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM direct_rooms WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM rooms WHERE id=?", (room_id,))
        conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Room members
# ---------------------------------------------------------------------------
def add_room_member(room_id, user_id, role="member"):
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
            (room_id, user_id)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO room_members (room_id, user_id, role, joined_at)"
                " VALUES (?,?,?,?)", (room_id, user_id, role, now()))
            conn.commit()
            return True
        return False
    finally:
        close_db(conn)


def remove_room_member(room_id, user_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM room_members WHERE room_id=? AND user_id=?",
                     (room_id, user_id))
        conn.commit()
    finally:
        close_db(conn)


def get_room_members(room_id):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT u.id, u.username, u.user_id, u.profile_image, u.status_message,"
            " m.role FROM room_members m JOIN users u ON u.id=m.user_id"
            " WHERE m.room_id=? ORDER BY m.role, u.username", (room_id,)).fetchall())
    finally:
        close_db(conn)


def is_room_member(room_id, user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
            (room_id, user_id)).fetchone() is not None
    finally:
        close_db(conn)


def get_member_role(room_id, user_id):
    conn = get_db()
    try:
        r = conn.execute(
            "SELECT role FROM room_members WHERE room_id=? AND user_id=?",
            (room_id, user_id)).fetchone()
        return r["role"] if r else None
    finally:
        close_db(conn)


def set_room_pinned(room_id, user_id, is_pinned):
    conn = get_db()
    try:
        conn.execute("UPDATE room_members SET is_pinned=? WHERE room_id=? AND user_id=?",
                     (1 if is_pinned else 0, room_id, user_id))
        conn.commit()
    finally:
        close_db(conn)


def set_room_favorite(room_id, user_id, is_favorite):
    conn = get_db()
    try:
        conn.execute("UPDATE room_members SET is_favorite=? WHERE room_id=? AND user_id=?",
                     (1 if is_favorite else 0, room_id, user_id))
        conn.commit()
    finally:
        close_db(conn)


def mark_room_read(room_id, user_id, message_id):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE room_members SET last_read_message_id=? WHERE room_id=? AND user_id=?"
            " AND last_read_message_id < ?",
            (message_id, room_id, user_id, message_id))
        conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Direct rooms (1:1)
# ---------------------------------------------------------------------------
def get_or_create_direct_room(user1_id, user2_id):
    a, b = sorted([int(user1_id), int(user2_id)])
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT room_id FROM direct_rooms WHERE user1_id=? AND user2_id=?",
            (a, b)).fetchone()
        if existing:
            return existing["room_id"]
        cur = conn.execute(
            "INSERT INTO rooms (name, room_type, created_by, created_at)"
            " VALUES (?,?,?,?)", ("Direct", "direct", a, now()))
        rid = cur.lastrowid
        conn.execute("INSERT INTO direct_rooms (room_id, user1_id, user2_id, created_at)"
                     " VALUES (?,?,?,?)", (rid, a, b, now()))
        for uid in (a, b):
            conn.execute("INSERT INTO room_members (room_id, user_id, role, joined_at)"
                         " VALUES (?,?,?,?)", (rid, uid, "member", now()))
        conn.commit()
        return rid
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
def _serialize_message(conn, m):
    user = conn.execute("SELECT username, profile_image FROM users WHERE id=?",
                        (m["user_id"],)).fetchone()
    attachment = None
    if m["attachment_id"]:
        a = conn.execute("SELECT * FROM attachments WHERE id=?",
                         (m["attachment_id"],)).fetchone()
        if a:
            attachment = {
                "id": a["id"], "original_name": a["original_name"],
                "url": a["file_url"], "file_type": a["file_type"],
                "file_size": a["file_size"],
            }
    reply = None
    if m["reply_to_id"]:
        r = conn.execute(
            "SELECT m.id, m.content, m.is_deleted, u.username FROM messages m"
            " JOIN users u ON u.id=m.user_id WHERE m.id=?", (m["reply_to_id"],)).fetchone()
        if r:
            reply = {
                "id": r["id"],
                "username": r["username"],
                "content": ("삭제된 메시지" if r["is_deleted"] else (r["content"] or "[첨부파일]")),
            }
    return {
        "id": m["id"], "room_id": m["room_id"], "user_id": m["user_id"],
        "username": user["username"] if user else "?",
        "profile_image": user["profile_image"] if user else None,
        "content": ("" if m["is_deleted"] else (m["content"] or "")),
        "created_at": m["created_at"],
        "is_edited": m["is_edited"], "is_deleted": m["is_deleted"],
        "is_pinned": m["is_pinned"],
        "reply_to": reply,
        "attachment": (None if m["is_deleted"] else attachment),
    }


def save_message(room_id, user_id, content=None, attachment_id=None, reply_to_id=None):
    content = (content or "").strip() or None
    if not content and not attachment_id:
        return None
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO messages (room_id, user_id, content, attachment_id, reply_to_id,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (room_id, user_id, content, attachment_id, reply_to_id, now()))
        conn.commit()
        return cur.lastrowid
    finally:
        close_db(conn)


def get_message(message_id):
    conn = get_db()
    try:
        m = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        return _serialize_message(conn, m) if m else None
    finally:
        close_db(conn)


def get_message_raw(message_id):
    conn = get_db()
    try:
        return _row(conn.execute("SELECT * FROM messages WHERE id=?",
                                 (message_id,)).fetchone())
    finally:
        close_db(conn)


def get_messages(room_id, limit=100, keyword=None):
    conn = get_db()
    try:
        if keyword and keyword.strip():
            rows = conn.execute(
                "SELECT * FROM messages WHERE room_id=? AND is_deleted=0"
                " AND content LIKE ? ORDER BY id DESC LIMIT ?",
                (room_id, f"%{keyword.strip()}%", limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM messages WHERE room_id=?"
                " ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (room_id, limit)).fetchall()
            return [_serialize_message(conn, m) for m in rows]
        # 검색 결과는 최신순 그대로
        return [_serialize_message(conn, m) for m in rows]
    finally:
        close_db(conn)


def get_pinned_messages(room_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE room_id=? AND is_pinned=1 AND is_deleted=0"
            " ORDER BY id DESC", (room_id,)).fetchall()
        return [_serialize_message(conn, m) for m in rows]
    finally:
        close_db(conn)


def edit_message(message_id, user_id, content):
    conn = get_db()
    try:
        m = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if not m or m["user_id"] != user_id or m["is_deleted"]:
            return False
        conn.execute(
            "UPDATE messages SET content=?, is_edited=1, updated_at=? WHERE id=?",
            ((content or "").strip(), now(), message_id))
        conn.commit()
        return True
    finally:
        close_db(conn)


def delete_message(message_id, user_id, is_admin=False):
    conn = get_db()
    try:
        m = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if not m:
            return False
        if m["user_id"] != user_id and not is_admin:
            return False
        conn.execute(
            "UPDATE messages SET is_deleted=1, content='', attachment_id=NULL,"
            " updated_at=? WHERE id=?", (now(), message_id))
        conn.commit()
        return True
    finally:
        close_db(conn)


def pin_message(message_id, is_pinned):
    conn = get_db()
    try:
        m = conn.execute("SELECT id FROM messages WHERE id=?", (message_id,)).fetchone()
        if not m:
            return False
        conn.execute("UPDATE messages SET is_pinned=? WHERE id=?",
                     (1 if is_pinned else 0, message_id))
        conn.commit()
        return True
    finally:
        close_db(conn)


def get_room_last_message(room_id):
    conn = get_db()
    try:
        m = conn.execute(
            "SELECT * FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 1",
            (room_id,)).fetchone()
        return _serialize_message(conn, m) if m else None
    finally:
        close_db(conn)


def get_room_unread_count(room_id, user_id):
    conn = get_db()
    try:
        mem = conn.execute(
            "SELECT last_read_message_id FROM room_members WHERE room_id=? AND user_id=?",
            (room_id, user_id)).fetchone()
        last_read = mem["last_read_message_id"] if mem else 0
        return conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE room_id=? AND id>? AND user_id<>?",
            (room_id, last_read or 0, user_id)).fetchone()["c"]
    finally:
        close_db(conn)


def get_room_member_ids(room_id):
    conn = get_db()
    try:
        return [r["user_id"] for r in conn.execute(
            "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------
def save_attachment(original_name, saved_name, file_path, file_url,
                    file_type, file_size, uploaded_by):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO attachments (original_name, saved_name, file_path, file_url,"
            " file_type, file_size, uploaded_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (original_name, saved_name, file_path, file_url, file_type,
             file_size, uploaded_by, now()))
        conn.commit()
        return cur.lastrowid
    finally:
        close_db(conn)


def get_attachment(attachment_id):
    conn = get_db()
    try:
        return _row(conn.execute("SELECT * FROM attachments WHERE id=?",
                                 (attachment_id,)).fetchone())
    finally:
        close_db(conn)


def delete_attachment(attachment_id, user_id):
    conn = get_db()
    try:
        a = conn.execute("SELECT * FROM attachments WHERE id=?",
                         (attachment_id,)).fetchone()
        if not a or a["uploaded_by"] != user_id:
            return False
        conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        conn.commit()
        try:
            if os.path.exists(a["file_path"]):
                os.remove(a["file_path"])
        except OSError:
            pass
        return True
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def create_notification(user_id, room_id, message_id, title, body):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, room_id, message_id, title, body,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (user_id, room_id, message_id, title, body, now()))
        conn.commit()
    finally:
        close_db(conn)


def get_notifications(user_id, limit=30):
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall())
    finally:
        close_db(conn)


def mark_notification_read(notification_id, user_id):
    conn = get_db()
    try:
        conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
                     (notification_id, user_id))
        conn.commit()
    finally:
        close_db(conn)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def get_admin_summary():
    conn = get_db()
    try:
        return {
            "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
            "rooms": conn.execute("SELECT COUNT(*) c FROM rooms").fetchone()["c"],
            "messages": conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE is_deleted=0").fetchone()["c"],
        }
    finally:
        close_db(conn)


def get_all_users():
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT id, username, user_id, profile_image, status_message, is_admin,"
            " is_active, created_at FROM users ORDER BY id").fetchall())
    finally:
        close_db(conn)


def get_all_rooms():
    conn = get_db()
    try:
        return _rows(conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM room_members WHERE room_id=r.id) members,"
            " (SELECT COUNT(*) FROM messages WHERE room_id=r.id) msgs"
            " FROM rooms r ORDER BY r.id").fetchall())
    finally:
        close_db(conn)
