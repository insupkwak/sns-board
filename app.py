"""
app.py — Telegram 스타일 내부용 SNS / 메신저 (Flask + Flask-SocketIO + SQLite)
실행: python app.py  →  http://127.0.0.1:5000
"""
# ----------------------------------------------------------------------------
# 1. import
# ----------------------------------------------------------------------------
import os
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, send_from_directory, abort)
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import storage
import media

# ----------------------------------------------------------------------------
# 2. 기본 경로 설정
# ----------------------------------------------------------------------------
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.getenv("VERCEL") or os.getenv("UPLOAD_DIR"):
    UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "/tmp/uploads")
else:
    UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
ATTACH_DIR = os.path.join(UPLOAD_ROOT, "attachments")
PROFILE_DIR = os.path.join(UPLOAD_ROOT, "profiles")
os.makedirs(ATTACH_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

# ----------------------------------------------------------------------------
# 3. Flask app 설정
# ----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-telegram-sns-secret")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# 제한 기준
MSG_MAX = 2000
ROOM_NAME_MAX = 50
STATUS_MAX = 100
PROFILE_IMG_MAX = 3 * 1024 * 1024

ATTACH_EXT = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt",
              "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip"}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

# ----------------------------------------------------------------------------
# 5. SocketIO 설정 (threading 모드 — 추가 의존성 없이 바로 실행)
# ----------------------------------------------------------------------------
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

storage.init_db()
media.init_media_db()

# 접속 상태 추적
online_users = {}   # uid -> set(sid)
sid_user = {}       # sid -> uid
sid_room = {}       # sid -> room_id (현재 보고 있는 방)


# ----------------------------------------------------------------------------
# 6. 공통 유틸
# ----------------------------------------------------------------------------
def current_user():
    uid = session.get("uid")
    return storage.get_user_by_id(uid) if uid else None


def ok(**kw):
    d = {"ok": True}
    d.update(kw)
    return jsonify(d)


def err(message, code=400):
    return jsonify({"ok": False, "error": message}), code


def ext_of(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def user_currently_in_room(uid, room_id):
    for sid in online_users.get(uid, set()):
        if sid_room.get(sid) == room_id:
            return True
    return False


# ----------------------------------------------------------------------------
# 7~8. 로그인/관리자 확인 decorator
# ----------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        if not session.get("uid"):
            if request.path.startswith("/api"):
                return err("로그인이 필요합니다.", 401)
            return redirect(url_for("login_page"))
        return view(*a, **k)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        u = current_user()
        if not u:
            return err("로그인이 필요합니다.", 401) if request.path.startswith("/api") \
                else redirect(url_for("login_page"))
        if not u["is_admin"]:
            return err("관리자 권한이 필요합니다.", 403) if request.path.startswith("/api") \
                else abort(403)
        return view(*a, **k)
    return wrapped


# ----------------------------------------------------------------------------
# 10. 페이지 route
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("chat_page") if session.get("uid") else url_for("login_page"))


@app.route("/login")
def login_page():
    if session.get("uid"):
        return redirect(url_for("chat_page"))
    return render_template("login.html")


@app.route("/register")
def register_page():
    if session.get("uid"):
        return redirect(url_for("chat_page"))
    return render_template("register.html")


@app.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html", user=current_user())


@app.route("/profile")
@login_required
def profile_page():
    return render_template("profile.html", user=current_user())


@app.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", user=current_user())


@app.route("/discovery")
def discovery_page():
    return render_template("discovery.html", user=current_user())


@app.route("/channel/<int:room_id>")
def channel_page(room_id):
    return render_template("channel.html", user=current_user(), room_id=room_id)


@app.route("/article/new")
@login_required
def article_editor_page():
    return render_template("article_editor.html", user=current_user())


@app.route("/article/<int:article_id>")
def article_detail_page(article_id):
    return render_template("article_detail.html", user=current_user(), article_id=article_id)


@app.route("/promotions")
@login_required
def promotion_center_page():
    return render_template("promotion_center.html", user=current_user())


@app.route("/media")
@login_required
def media_dashboard_page():
    return render_template("media_dashboard.html", user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ----------------------------------------------------------------------------
# 11. Auth route
# ----------------------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login_post():
    data = request.get_json(silent=True) or request.form
    user_id = (data.get("user_id") or "").strip()
    password = data.get("password") or ""
    if not user_id or not password:
        return err("아이디와 비밀번호를 입력하세요.")
    u = storage.get_user_by_user_id(user_id)
    if not u or not check_password_hash(u["password_hash"], password):
        return err("아이디 또는 비밀번호가 올바르지 않습니다.", 401)
    if not u["is_active"]:
        return err("비활성화된 계정입니다. 관리자에게 문의하세요.", 403)
    session["uid"] = u["id"]
    return ok(redirect="/chat")


@app.route("/register", methods=["POST"])
def register_post():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    user_id = (data.get("user_id") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""

    if not username or not user_id or not password:
        return err("모든 항목을 입력하세요.")
    if len(username) > 30:
        return err("이름은 30자 이하로 입력하세요.")
    if len(password) < 4:
        return err("비밀번호는 4자 이상이어야 합니다.")
    if password != password2:
        return err("비밀번호가 일치하지 않습니다.")
    if storage.get_user_by_user_id(user_id):
        return err("이미 사용 중인 아이디입니다.", 409)

    storage.create_user(username, user_id, password)
    return ok(redirect="/login")


# ----------------------------------------------------------------------------
# 12. User API
# ----------------------------------------------------------------------------
@app.route("/api/me")
@login_required
def api_me():
    u = current_user()
    return ok(user={
        "id": u["id"], "username": u["username"], "user_id": u["user_id"],
        "profile_image": u["profile_image"], "status_message": u["status_message"],
        "is_admin": u["is_admin"],
    })


@app.route("/api/users/search")
@login_required
def api_users_search():
    me = current_user()
    keyword = request.args.get("q", "")
    users = storage.search_users(keyword, include_inactive=bool(me["is_admin"]))
    return ok(users=users)


@app.route("/api/users/<int:uid>")
@login_required
def api_user_get(uid):
    u = storage.get_user_by_id(uid)
    if not u:
        return err("사용자를 찾을 수 없습니다.", 404)
    return ok(user={
        "id": u["id"], "username": u["username"], "user_id": u["user_id"],
        "profile_image": u["profile_image"], "status_message": u["status_message"],
    })


# ----------------------------------------------------------------------------
# 13. Room API
# ----------------------------------------------------------------------------
@app.route("/api/rooms")
@login_required
def api_rooms():
    return ok(rooms=storage.get_rooms_for_user(session["uid"]))


@app.route("/api/rooms", methods=["POST"])
@login_required
def api_rooms_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip() or None
    if not name:
        return err("채팅방 이름을 입력하세요.")
    if len(name) > ROOM_NAME_MAX:
        return err(f"채팅방 이름은 {ROOM_NAME_MAX}자 이하로 입력하세요.")
    rid = storage.create_room(name, session["uid"], description=description)
    room = storage.get_room(rid)
    socketio.emit("room_created", {"room_id": rid}, room=f"user:{session['uid']}")
    return ok(room=room)


@app.route("/api/rooms/search")
@login_required
def api_rooms_search():
    return ok(rooms=storage.search_rooms_for_user(session["uid"], request.args.get("q", "")))


@app.route("/api/rooms/<int:room_id>")
@login_required
def api_room_get(room_id):
    if not storage.is_room_member(room_id, session["uid"]):
        return err("접근 권한이 없습니다.", 403)
    room = storage.get_room(room_id)
    if not room:
        return err("채팅방을 찾을 수 없습니다.", 404)
    # 1:1 방 표시 이름 보정
    name = room["name"]
    if room["room_type"] == "direct":
        for m in storage.get_room_members(room_id):
            if m["id"] != session["uid"]:
                name = m["username"]
                break
    return ok(room={**room, "display_name": name},
              members=storage.get_room_members(room_id),
              pinned=storage.get_pinned_messages(room_id),
              role=storage.get_member_role(room_id, session["uid"]))


@app.route("/api/rooms/<int:room_id>", methods=["PUT"])
@login_required
def api_room_update(room_id):
    role = storage.get_member_role(room_id, session["uid"])
    if role not in ("owner", "admin"):
        return err("이름/설명 변경 권한이 없습니다.", 403)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() or None
    if name and len(name) > ROOM_NAME_MAX:
        return err(f"채팅방 이름은 {ROOM_NAME_MAX}자 이하로 입력하세요.")
    storage.update_room(room_id, name=name,
                        description=(data.get("description") or "").strip())
    socketio.emit("room_updated", {"room_id": room_id}, room=f"room:{room_id}")
    return ok(room=storage.get_room(room_id))


@app.route("/api/rooms/<int:room_id>", methods=["DELETE"])
@login_required
def api_room_delete(room_id):
    room = storage.get_room(room_id)
    if not room:
        return err("채팅방을 찾을 수 없습니다.", 404)
    role = storage.get_member_role(room_id, session["uid"])
    u = current_user()
    if role != "owner" and not u["is_admin"]:
        return err("삭제 권한이 없습니다.", 403)
    storage.delete_room(room_id)
    socketio.emit("room_deleted", {"room_id": room_id}, room=f"room:{room_id}")
    return ok()


@app.route("/api/rooms/<int:room_id>/members", methods=["POST"])
@login_required
def api_room_invite(room_id):
    if not storage.is_room_member(room_id, session["uid"]):
        return err("접근 권한이 없습니다.", 403)
    data = request.get_json(silent=True) or {}
    target = data.get("user_id")
    if not target:
        return err("초대할 사용자를 선택하세요.")
    if not storage.get_user_by_id(target):
        return err("사용자를 찾을 수 없습니다.", 404)
    added = storage.add_room_member(room_id, int(target))
    if added:
        socketio.emit("room_created", {"room_id": room_id}, room=f"user:{target}")
        socketio.emit("room_updated", {"room_id": room_id}, room=f"room:{room_id}")
    return ok(added=added)


@app.route("/api/rooms/<int:room_id>/members")
@login_required
def api_room_members(room_id):
    if not storage.is_room_member(room_id, session["uid"]):
        return err("접근 권한이 없습니다.", 403)
    return ok(members=storage.get_room_members(room_id))


@app.route("/api/rooms/<int:room_id>/members/<int:uid>", methods=["DELETE"])
@login_required
def api_room_leave(room_id, uid):
    me = current_user()
    # 본인 나가기 또는 owner/admin 이 내보내기
    role = storage.get_member_role(room_id, session["uid"])
    if uid != session["uid"] and role not in ("owner", "admin") and not me["is_admin"]:
        return err("권한이 없습니다.", 403)
    storage.remove_room_member(room_id, uid)
    socketio.emit("room_deleted", {"room_id": room_id}, room=f"user:{uid}")
    socketio.emit("room_updated", {"room_id": room_id}, room=f"room:{room_id}")
    return ok()


@app.route("/api/rooms/<int:room_id>/pin", methods=["POST"])
@login_required
def api_room_pin(room_id):
    data = request.get_json(silent=True) or {}
    storage.set_room_pinned(room_id, session["uid"], bool(data.get("pinned")))
    return ok()


@app.route("/api/rooms/<int:room_id>/favorite", methods=["POST"])
@login_required
def api_room_favorite(room_id):
    data = request.get_json(silent=True) or {}
    storage.set_room_favorite(room_id, session["uid"], bool(data.get("favorite")))
    return ok()


@app.route("/api/rooms/<int:room_id>/read", methods=["POST"])
@login_required
def api_room_read(room_id):
    last = storage.get_room_last_message(room_id)
    if last:
        storage.mark_room_read(room_id, session["uid"], last["id"])
    return ok()


@app.route("/api/direct/start", methods=["POST"])
@login_required
def api_direct_start():
    data = request.get_json(silent=True) or {}
    target = data.get("target_user_id")
    if not target or int(target) == session["uid"]:
        return err("올바른 상대를 선택하세요.")
    if not storage.get_user_by_id(target):
        return err("사용자를 찾을 수 없습니다.", 404)
    rid = storage.get_or_create_direct_room(session["uid"], int(target))
    other = storage.get_user_by_id(target)
    socketio.emit("room_created", {"room_id": rid}, room=f"user:{target}")
    return ok(room={"id": rid, "name": other["username"], "room_type": "direct"})


# ----------------------------------------------------------------------------
# 14. Message API
# ----------------------------------------------------------------------------
@app.route("/api/rooms/<int:room_id>/messages")
@login_required
def api_messages(room_id):
    if not storage.is_room_member(room_id, session["uid"]):
        return err("접근 권한이 없습니다.", 403)
    msgs = storage.get_messages(room_id, limit=100)
    if msgs:
        storage.mark_room_read(room_id, session["uid"], msgs[-1]["id"])
    return ok(messages=msgs)


@app.route("/api/rooms/<int:room_id>/messages/search")
@login_required
def api_messages_search(room_id):
    if not storage.is_room_member(room_id, session["uid"]):
        return err("접근 권한이 없습니다.", 403)
    msgs = storage.get_messages(room_id, limit=100, keyword=request.args.get("q", ""))
    return ok(messages=msgs)


@app.route("/api/messages/<int:message_id>", methods=["PUT"])
@login_required
def api_message_edit(message_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return err("내용을 입력하세요.")
    if len(content) > MSG_MAX:
        return err(f"메시지는 {MSG_MAX}자 이하여야 합니다.")
    if not storage.edit_message(message_id, session["uid"], content):
        return err("수정할 수 없습니다.", 403)
    m = storage.get_message(message_id)
    socketio.emit("message_updated", m, room=f"room:{m['room_id']}")
    return ok(message=m)


@app.route("/api/messages/<int:message_id>", methods=["DELETE"])
@login_required
def api_message_delete(message_id):
    raw = storage.get_message_raw(message_id)
    if not raw:
        return err("메시지를 찾을 수 없습니다.", 404)
    u = current_user()
    if not storage.delete_message(message_id, session["uid"], is_admin=bool(u["is_admin"])):
        return err("삭제 권한이 없습니다.", 403)
    socketio.emit("message_deleted",
                  {"id": message_id, "room_id": raw["room_id"]},
                  room=f"room:{raw['room_id']}")
    return ok()


@app.route("/api/messages/<int:message_id>/pin", methods=["POST"])
@login_required
def api_message_pin(message_id):
    raw = storage.get_message_raw(message_id)
    if not raw:
        return err("메시지를 찾을 수 없습니다.", 404)
    role = storage.get_member_role(raw["room_id"], session["uid"])
    if role not in ("owner", "admin"):
        return err("고정 권한이 없습니다.", 403)
    data = request.get_json(silent=True) or {}
    storage.pin_message(message_id, bool(data.get("pinned")))
    socketio.emit("message_pinned",
                  {"id": message_id, "room_id": raw["room_id"],
                   "pinned": bool(data.get("pinned"))},
                  room=f"room:{raw['room_id']}")
    return ok()


# ----------------------------------------------------------------------------
# 15. Attachment API
# ----------------------------------------------------------------------------
@app.route("/api/attachments", methods=["POST"])
@login_required
def api_attachment_upload():
    if "file" not in request.files:
        return err("파일이 없습니다.")
    f = request.files["file"]
    if not f or not f.filename:
        return err("파일이 없습니다.")
    ext = ext_of(f.filename)
    if ext not in ATTACH_EXT:
        return err("허용되지 않은 파일 형식입니다.")
    safe = secure_filename(f.filename) or f"file.{ext}"
    saved = f"{uuid.uuid4().hex}_{safe}"
    path = os.path.join(ATTACH_DIR, saved)
    f.save(path)
    size = os.path.getsize(path)
    if size > 10 * 1024 * 1024:
        os.remove(path)
        return err("파일은 10MB 이하만 가능합니다.")
    file_url = f"/uploads/attachments/{saved}"
    aid = storage.save_attachment(f.filename, saved, path, file_url,
                                  f.mimetype, size, session["uid"])
    return ok(attachment={"id": aid, "original_name": f.filename, "url": file_url,
                          "file_type": f.mimetype, "file_size": size})


@app.route("/api/attachments/<int:attachment_id>", methods=["DELETE"])
@login_required
def api_attachment_delete(attachment_id):
    if not storage.delete_attachment(attachment_id, session["uid"]):
        return err("삭제 권한이 없습니다.", 403)
    return ok()


@app.route("/uploads/attachments/<path:filename>")
def serve_attachment(filename):
    return send_from_directory(ATTACH_DIR, filename)


@app.route("/uploads/profiles/<path:filename>")
def serve_profile(filename):
    return send_from_directory(PROFILE_DIR, filename)


# ----------------------------------------------------------------------------
# 16. Profile API
# ----------------------------------------------------------------------------
@app.route("/api/profile")
@login_required
def api_profile_get():
    u = current_user()
    return ok(user={
        "id": u["id"], "username": u["username"], "user_id": u["user_id"],
        "profile_image": u["profile_image"], "status_message": u["status_message"],
    })


@app.route("/api/profile", methods=["POST"])
@login_required
def api_profile_update():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    status_message = (data.get("status_message") or "").strip()
    if not username:
        return err("이름을 입력하세요.")
    if len(username) > 30:
        return err("이름은 30자 이하로 입력하세요.")
    if len(status_message) > STATUS_MAX:
        return err(f"상태 메시지는 {STATUS_MAX}자 이하로 입력하세요.")
    storage.update_user_profile(session["uid"], username, status_message)
    return ok(user=storage.get_user_by_id(session["uid"]))


@app.route("/api/profile/image", methods=["POST"])
@login_required
def api_profile_image():
    if "file" not in request.files:
        return err("이미지가 없습니다.")
    f = request.files["file"]
    if not f or not f.filename:
        return err("이미지가 없습니다.")
    ext = ext_of(f.filename)
    if ext not in IMAGE_EXT:
        return err("이미지 파일만 업로드할 수 있습니다.")
    safe = secure_filename(f.filename) or f"img.{ext}"
    saved = f"{uuid.uuid4().hex}_{safe}"
    path = os.path.join(PROFILE_DIR, saved)
    f.save(path)
    if os.path.getsize(path) > PROFILE_IMG_MAX:
        os.remove(path)
        return err("프로필 이미지는 3MB 이하만 가능합니다.")
    url = f"/uploads/profiles/{saved}"
    u = current_user()
    storage.update_user_profile(session["uid"], u["username"],
                                u["status_message"] or "", profile_image=url)
    return ok(profile_image=url)


# ----------------------------------------------------------------------------
# Notification API
# ----------------------------------------------------------------------------
@app.route("/api/notifications")
@login_required
def api_notifications():
    return ok(notifications=storage.get_notifications(session["uid"]))


@app.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def api_notification_read(nid):
    storage.mark_notification_read(nid, session["uid"])
    return ok()


# ----------------------------------------------------------------------------
# 17. Admin API
# ----------------------------------------------------------------------------
@app.route("/api/admin/summary")
@admin_required
def api_admin_summary():
    return ok(summary=storage.get_admin_summary())


@app.route("/api/admin/users")
@admin_required
def api_admin_users():
    return ok(users=storage.get_all_users())


@app.route("/api/admin/users/<int:uid>/active", methods=["POST"])
@admin_required
def api_admin_user_active(uid):
    data = request.get_json(silent=True) or {}
    storage.set_user_active(uid, bool(data.get("active")))
    return ok()


@app.route("/api/admin/rooms")
@admin_required
def api_admin_rooms():
    return ok(rooms=storage.get_all_rooms())


@app.route("/api/admin/rooms/<int:room_id>", methods=["DELETE"])
@admin_required
def api_admin_room_delete(room_id):
    storage.delete_room(room_id)
    socketio.emit("room_deleted", {"room_id": room_id}, room=f"room:{room_id}")
    return ok()


@app.route("/api/admin/notice", methods=["POST"])
@admin_required
def api_admin_notice():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "공지").strip()
    message = (data.get("message") or "").strip()
    rid = storage.create_room(name, session["uid"], description="공지방",
                              room_type="notice", is_notice=1)
    # 모든 사용자 초대
    for u in storage.get_all_users():
        storage.add_room_member(rid, u["id"])
    if message:
        mid = storage.save_message(rid, session["uid"], content=message)
        socketio.emit("receive_message", storage.get_message(mid), room=f"room:{rid}")
    socketio.emit("room_created", {"room_id": rid})
    return ok(room_id=rid)


# ============================================================================
#  3차 고도화: 미디어 플랫폼 API
# ============================================================================

# ---- Organizations ----
@app.route("/api/organizations", methods=["POST"])
@login_required
def api_org_create():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    org_type = d.get("org_type") or "media"
    if not name:
        return err("조직명을 입력하세요.")
    oid = media.create_organization(name, org_type, session["uid"],
                                    description=(d.get("description") or "").strip() or None,
                                    website_url=d.get("website_url"),
                                    contact_email=d.get("contact_email"))
    return ok(organization=media.get_organization(oid))


@app.route("/api/organizations/mine")
@login_required
def api_org_mine():
    return ok(organizations=media.list_organizations_for_user(session["uid"]))


@app.route("/api/organizations/<int:oid>")
def api_org_get(oid):
    o = media.get_organization(oid)
    if not o:
        return err("조직을 찾을 수 없습니다.", 404)
    return ok(organization=o, members=media.list_org_members(oid))


@app.route("/api/organizations/<int:oid>/verify-request", methods=["POST"])
@login_required
def api_org_verify_request(oid):
    if not media.is_org_member(oid, session["uid"]):
        return err("권한이 없습니다.", 403)
    media.request_org_verification(oid)
    return ok()


@app.route("/api/organizations/<int:oid>/members", methods=["POST"])
@login_required
def api_org_add_member(oid):
    if not media.is_org_member(oid, session["uid"]):
        return err("권한이 없습니다.", 403)
    d = request.get_json(silent=True) or {}
    media.add_org_member(oid, int(d.get("user_id")), d.get("role") or "editor")
    return ok()


# ---- Channels ----
@app.route("/api/channels", methods=["POST"])
@login_required
def api_channel_create():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        return err("채널 이름을 입력하세요.")
    org_id = d.get("organization_id")
    if org_id and not media.is_org_member(int(org_id), session["uid"]):
        return err("해당 조직의 멤버가 아닙니다.", 403)
    rid = media.create_channel(
        name, session["uid"], room_type=d.get("room_type") or "channel",
        description=(d.get("description") or "").strip() or None,
        organization_id=int(org_id) if org_id else None,
        category_id=d.get("category_id"), visibility=d.get("visibility") or "public")
    socketio.emit("room_created", {"room_id": rid}, room=f"user:{session['uid']}")
    return ok(room=media.get_channel_full(rid, session["uid"]))


@app.route("/api/channels/<int:room_id>")
def api_channel_get(room_id):
    ch = media.get_channel_full(room_id, session.get("uid"))
    if not ch:
        return err("채널을 찾을 수 없습니다.", 404)
    return ok(channel=ch,
              articles=media.list_articles_for_room(room_id, limit=20))


@app.route("/api/channels/<int:room_id>/follow", methods=["POST"])
@login_required
def api_channel_follow(room_id):
    d = request.get_json(silent=True) or {}
    if d.get("follow") is False:
        media.unfollow_room(room_id, session["uid"]); following = False
    else:
        media.follow_room(room_id, session["uid"]); following = True
        socketio.emit("room_created", {"room_id": room_id}, room=f"user:{session['uid']}")
    return ok(following=following, follower_count=media.follower_count(room_id))


# ---- Discovery ----
@app.route("/api/discovery/home")
def api_discovery_home():
    return ok(data=media.discovery_home())


@app.route("/api/discovery/categories")
def api_discovery_categories():
    return ok(categories=media.list_categories())


@app.route("/api/discovery/search")
def api_discovery_search():
    cat = request.args.get("category")
    res = media.discovery_search(
        q=request.args.get("q", "").strip(),
        category_id=int(cat) if cat and cat.isdigit() else None,
        room_type=request.args.get("type") or None,
        sort=request.args.get("sort") or "relevance",
        limit=min(50, int(request.args.get("limit", 30) or 30)))
    return ok(data=res["promoted"] + res["rooms"],
              promoted=res["promoted"], rooms=res["rooms"])


@app.route("/api/discovery/promotions/<int:pid>/event", methods=["POST"])
def api_promotion_event(pid):
    d = request.get_json(silent=True) or {}
    et = d.get("event_type") or "impression"
    if et not in ("impression", "click", "join", "follow", "dismiss"):
        return err("잘못된 이벤트입니다.")
    p = media.get_promotion(pid)
    media.log_promotion_event(pid, p["room_id"] if p else None, session.get("uid"), et)
    return ok()


# ---- Promotions ----
@app.route("/api/promotions/my")
@login_required
def api_promotions_my():
    return ok(promotions=media.list_my_promotions(session["uid"]))


@app.route("/api/promotions", methods=["POST"])
@login_required
def api_promotion_create():
    d = request.get_json(silent=True) or {}
    room_id = d.get("room_id")
    title = (d.get("title") or "").strip()
    if not room_id or not title:
        return err("채널과 홍보 제목을 입력하세요.")
    if storage.get_member_role(int(room_id), session["uid"]) not in ("owner", "admin"):
        return err("해당 채널의 운영자만 홍보할 수 있습니다.", 403)
    pid = media.create_promotion(int(room_id), session["uid"], title,
                                 description=(d.get("description") or "").strip() or None,
                                 image_url=d.get("image_url"),
                                 placement=d.get("placement") or "search_top",
                                 start_at=d.get("start_at"), end_at=d.get("end_at"))
    return ok(promotion=media.get_promotion(pid))


@app.route("/api/promotions/<int:pid>/submit", methods=["POST"])
@login_required
def api_promotion_submit(pid):
    if not media.submit_promotion(pid, session["uid"]):
        return err("권한이 없습니다.", 403)
    return ok()


@app.route("/api/promotions/<int:pid>/pause", methods=["POST"])
@login_required
def api_promotion_pause(pid):
    media.set_promotion_status(pid, session["uid"], "paused")
    return ok()


@app.route("/api/promotions/<int:pid>/resume", methods=["POST"])
@login_required
def api_promotion_resume(pid):
    media.set_promotion_status(pid, session["uid"], "approved")
    return ok()


@app.route("/api/promotions/<int:pid>/stats")
@login_required
def api_promotion_stats(pid):
    return ok(stats=media.promotion_stats(pid))


# ---- Articles ----
def _can_publish_to_room(uid, room_id, org_id):
    u = current_user()
    if u and u["is_admin"]:
        return True
    if room_id and storage.get_member_role(room_id, uid) in ("owner", "admin", "editor"):
        return True
    if org_id and media.is_org_member(org_id, uid):
        return True
    return (room_id is None and org_id is None)  # 개인 초안


@app.route("/api/articles", methods=["POST"])
@login_required
def api_article_create():
    d = request.get_json(silent=True) or {}
    title = (d.get("title") or "").strip()
    if not title:
        return err("기사 제목을 입력하세요.")
    room_id = d.get("room_id") and int(d["room_id"])
    org_id = d.get("organization_id") and int(d["organization_id"])
    if not _can_publish_to_room(session["uid"], room_id, org_id):
        return err("이 채널/조직에 발행할 권한이 없습니다.", 403)
    status = d.get("status") or "draft"
    aid = media.create_article(
        session["uid"], title, room_id=room_id, organization_id=org_id,
        subtitle=d.get("subtitle"), summary=d.get("summary"), body=d.get("body"),
        source_url=d.get("source_url"), cover_image_url=d.get("cover_image_url"),
        category_id=d.get("category_id"), article_type=d.get("article_type") or "news",
        status=status, is_breaking=1 if d.get("is_breaking") else 0,
        scheduled_at=d.get("scheduled_at"),
        tags=[t.strip() for t in (d.get("tags") or "").split(",") if t.strip()])
    if status == "published":
        _publish_effects(aid)
    return ok(article=media.get_article(aid))


def _publish_effects(aid):
    """발행 후: 채널에 기사 공유 메시지 생성 + 실시간 이벤트."""
    a = media.get_article(aid)
    if not a or not a["room_id"]:
        return
    rid = a["room_id"]
    body = f"[기사] {a['title']}"
    if a.get("summary"):
        body += f"\n{a['summary']}"
    body += f"\n▶ /article/{aid}"
    # 메시지 직접 삽입(content_type=article_share)
    conn = storage.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO messages (room_id, user_id, content, content_type, article_id,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (rid, a["author_id"], body, "article_share", aid, storage.now()))
        conn.commit()
        mid = cur.lastrowid
    finally:
        storage.close_db(conn)
    msg = storage.get_message(mid)
    socketio.emit("receive_message", msg, room=f"room:{rid}")
    socketio.emit("article_published",
                  {"room_id": rid, "article_id": aid, "title": a["title"],
                   "summary": a.get("summary"), "cover_image_url": a.get("cover_image_url")},
                  room=f"room:{rid}")
    for member_id in storage.get_room_member_ids(rid):
        socketio.emit("room_updated", {"room_id": rid}, room=f"user:{member_id}")
        if member_id != a["author_id"]:
            storage.create_notification(member_id, rid, mid, "새 기사", a["title"])
    if a.get("is_breaking"):
        socketio.emit("breaking_news",
                      {"room_id": rid, "article_id": aid, "title": a["title"],
                       "summary": a.get("summary"),
                       "cover_image_url": a.get("cover_image_url")})


@app.route("/api/articles/<int:aid>")
def api_article_get(aid):
    a = media.get_article(aid)
    if not a or a["status"] == "deleted":
        return err("기사를 찾을 수 없습니다.", 404)
    if a["status"] != "published":
        u = current_user()
        if not u or (u["id"] != a["author_id"] and not u["is_admin"]):
            return err("비공개 기사입니다.", 403)
    else:
        media.increment_view(aid)
        a = media.get_article(aid)
    liked = False
    if session.get("uid"):
        conn = storage.get_db()
        try:
            liked = conn.execute("SELECT 1 FROM article_likes WHERE article_id=? AND user_id=?",
                                 (aid, session["uid"])).fetchone() is not None
        finally:
            storage.close_db(conn)
    return ok(article=a, liked=liked)


@app.route("/api/articles/<int:aid>", methods=["PUT"])
@login_required
def api_article_update(aid):
    d = request.get_json(silent=True) or {}
    if not media.update_article(aid, session["uid"], **d):
        return err("수정 권한이 없습니다.", 403)
    return ok(article=media.get_article(aid))


@app.route("/api/articles/<int:aid>/publish", methods=["POST"])
@login_required
def api_article_publish(aid):
    a = media.get_article(aid)
    if not a:
        return err("기사를 찾을 수 없습니다.", 404)
    u = current_user()
    if a["author_id"] != session["uid"] and not u["is_admin"]:
        return err("발행 권한이 없습니다.", 403)
    media.publish_article(aid, "published")
    _publish_effects(aid)
    return ok(article=media.get_article(aid))


@app.route("/api/articles/<int:aid>/hide", methods=["POST"])
@login_required
def api_article_hide(aid):
    a = media.get_article(aid)
    u = current_user()
    if not a or (a["author_id"] != session["uid"] and not u["is_admin"]):
        return err("권한이 없습니다.", 403)
    media.hide_article(aid)
    return ok()


@app.route("/api/articles/<int:aid>/like", methods=["POST"])
@login_required
def api_article_like(aid):
    liked, count = media.toggle_like(aid, session["uid"])
    return ok(liked=liked, like_count=count)


@app.route("/api/articles/<int:aid>/share", methods=["POST"])
@login_required
def api_article_share(aid):
    media.share_article(aid)
    return ok()


@app.route("/api/articles/<int:aid>/report", methods=["POST"])
@login_required
def api_article_report(aid):
    d = request.get_json(silent=True) or {}
    media.create_report(session["uid"], "article", aid,
                        d.get("reason") or "other", d.get("detail"))
    return ok()


@app.route("/api/rooms/<int:room_id>/articles")
def api_room_articles(room_id):
    cur = request.args.get("cursor")
    return ok(articles=media.list_articles_for_room(
        room_id, cursor=int(cur) if cur and cur.isdigit() else None))


@app.route("/api/articles")
def api_articles_search():
    cur = request.args.get("cursor")
    return ok(articles=media.search_articles(
        request.args.get("q", "").strip(),
        cursor=int(cur) if cur and cur.isdigit() else None))


@app.route("/api/articles/mine")
@login_required
def api_articles_mine():
    return ok(articles=media.list_my_articles(session["uid"], request.args.get("status")))


# ---- Reports ----
@app.route("/api/reports", methods=["POST"])
@login_required
def api_report_create():
    d = request.get_json(silent=True) or {}
    if not d.get("target_type") or not d.get("target_id"):
        return err("신고 대상이 필요합니다.")
    media.create_report(session["uid"], d["target_type"], int(d["target_id"]),
                        d.get("reason") or "other", d.get("detail"))
    return ok()


# ---- Admin (media) ----
@app.route("/api/admin/media-summary")
@admin_required
def api_admin_media_summary():
    return ok(summary=media.admin_media_summary())


@app.route("/api/admin/organizations")
@admin_required
def api_admin_orgs():
    return ok(organizations=media.list_all_organizations())


@app.route("/api/admin/organizations/<int:oid>/verify", methods=["POST"])
@admin_required
def api_admin_org_verify(oid):
    media.set_org_verification(oid, "verified")
    return ok()


@app.route("/api/admin/organizations/<int:oid>/reject", methods=["POST"])
@admin_required
def api_admin_org_reject(oid):
    media.set_org_verification(oid, "rejected")
    return ok()


@app.route("/api/admin/promotions")
@admin_required
def api_admin_promotions():
    return ok(promotions=media.list_pending_promotions())


@app.route("/api/admin/promotions/<int:pid>/approve", methods=["POST"])
@admin_required
def api_admin_promo_approve(pid):
    media.review_promotion(pid, session["uid"], True)
    p = media.get_promotion(pid)
    if p:
        socketio.emit("promotion_updated", {"promotion_id": pid, "room_id": p["room_id"]})
    return ok()


@app.route("/api/admin/promotions/<int:pid>/reject", methods=["POST"])
@admin_required
def api_admin_promo_reject(pid):
    d = request.get_json(silent=True) or {}
    media.review_promotion(pid, session["uid"], False, d.get("reason"))
    return ok()


@app.route("/api/admin/reports")
@admin_required
def api_admin_reports():
    return ok(reports=media.list_reports(request.args.get("status", "pending")))


@app.route("/api/admin/reports/<int:rid>/handle", methods=["POST"])
@admin_required
def api_admin_report_handle(rid):
    d = request.get_json(silent=True) or {}
    media.handle_report(rid, session["uid"], d.get("status") or "resolved")
    return ok()


# ----------------------------------------------------------------------------
# 18. SocketIO events
# ----------------------------------------------------------------------------
@socketio.on("connect")
def on_connect():
    uid = session.get("uid")
    if not uid:
        return
    sid = request.sid
    sid_user[sid] = uid
    online_users.setdefault(uid, set()).add(sid)
    join_room(f"user:{uid}")            # 개인 알림 채널
    socketio.emit("user_online", {"user_id": uid})


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    uid = sid_user.pop(sid, None)
    sid_room.pop(sid, None)
    if uid and uid in online_users:
        online_users[uid].discard(sid)
        if not online_users[uid]:
            online_users.pop(uid, None)
            socketio.emit("user_offline", {"user_id": uid})


@socketio.on("join_room")
def on_join(data):
    uid = session.get("uid")
    if not uid:
        return
    room_id = data.get("room_id")
    if not room_id or not storage.is_room_member(room_id, uid):
        emit("error_message", {"error": "접근 권한이 없습니다."})
        return
    sid = request.sid
    prev = sid_room.get(sid)
    if prev:
        leave_room(f"room:{prev}")
    join_room(f"room:{room_id}")
    sid_room[sid] = room_id
    last = storage.get_room_last_message(room_id)
    if last:
        storage.mark_room_read(room_id, uid, last["id"])


@socketio.on("leave_room")
def on_leave(data):
    room_id = data.get("room_id")
    if room_id:
        leave_room(f"room:{room_id}")
        if sid_room.get(request.sid) == room_id:
            sid_room.pop(request.sid, None)


@socketio.on("send_message")
def on_send(data):
    uid = session.get("uid")
    if not uid:
        emit("error_message", {"error": "로그인이 필요합니다."})
        return
    room_id = data.get("room_id")
    content = (data.get("content") or "").strip()
    attachment_id = data.get("attachment_id")
    reply_to_id = data.get("reply_to_id")

    if not room_id or not storage.is_room_member(room_id, uid):
        emit("error_message", {"error": "접근 권한이 없습니다."})
        return
    if not content and not attachment_id:
        return
    if len(content) > MSG_MAX:
        emit("error_message", {"error": f"메시지는 {MSG_MAX}자 이하여야 합니다."})
        return

    mid = storage.save_message(room_id, uid, content=content or None,
                               attachment_id=attachment_id, reply_to_id=reply_to_id)
    if not mid:
        return
    msg = storage.get_message(mid)
    storage.mark_room_read(room_id, uid, mid)

    # 같은 방 사용자에게 실시간 전송
    socketio.emit("receive_message", msg, room=f"room:{room_id}")

    # 방 멤버들 목록 갱신 + 미접속/다른 방 멤버 알림
    sender_name = msg["username"]
    preview = content if content else "[첨부파일]"
    for member_id in storage.get_room_member_ids(room_id):
        socketio.emit("room_updated", {"room_id": room_id}, room=f"user:{member_id}")
        if member_id != uid and not user_currently_in_room(member_id, room_id):
            storage.create_notification(member_id, room_id, mid, sender_name, preview)


@socketio.on("typing")
def on_typing(data):
    uid = session.get("uid")
    room_id = data.get("room_id")
    if not uid or not room_id:
        return
    u = storage.get_user_by_id(uid)
    emit("typing", {"room_id": room_id, "username": u["username"] if u else ""},
         room=f"room:{room_id}", include_self=False)


@socketio.on("stop_typing")
def on_stop_typing(data):
    room_id = data.get("room_id")
    if room_id:
        emit("stop_typing", {"room_id": room_id}, room=f"room:{room_id}",
             include_self=False)


# ----------------------------------------------------------------------------
# 19. 실행
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port, debug=True,
                 allow_unsafe_werkzeug=True)
