/* chat.js — Telegram 스타일 메신저 프론트엔드 */
(() => {
"use strict";

// ---------- 10.1 상태 변수 ----------
let currentUser = null;
let currentRoomId = null;
let currentRoom = null;
let selectedFile = null;
let uploadedAttachmentId = null;
let replyToMessageId = null;
let roomsCache = [];
let messagesCache = [];
let typingTimer = null;
let searchTimer = null;
let socket = null;

const $ = (id) => document.getElementById(id);
const elc = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

// ---------- 유틸 ----------
function escapeHtml(value) {
  return (value ?? "").toString()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function formatTime(value) {
  if (!value) return "";
  // 'YYYY-MM-DD HH:MM:SS' → 오늘이면 HH:MM, 아니면 MM-DD HH:MM
  const t = value.replace(" ", "T");
  const d = new Date(t);
  if (isNaN(d)) return value.slice(11, 16);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `${hh}:${mm}`;
  return `${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${hh}:${mm}`;
}
function formatFileSize(size) {
  if (!size) return "";
  if (size < 1024) return size + " B";
  if (size < 1024*1024) return (size/1024).toFixed(1) + " KB";
  return (size/1024/1024).toFixed(1) + " MB";
}
function isImageFile(fileType, fileName) {
  if (fileType && fileType.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp)$/i.test(fileName || "");
}
function avatarStyle(url) {
  return url ? `style="background-image:url('${escapeHtml(url)}')"` : "";
}
function avatarText(name) { return (name || "?").trim().charAt(0).toUpperCase(); }

let toastTimer = null;
function showToast(message, type = "info") {
  const t = $("toast");
  t.textContent = message;
  t.className = "toast " + (type === "error" ? "err" : type === "success" ? "ok" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}
function setLoading(isLoading) { document.body.style.cursor = isLoading ? "progress" : ""; }

async function api(url, method = "GET", body, isForm = false) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) { opt.body = body; }
    else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  }
  const res = await fetch(url, opt);
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok || data.ok === false) throw new Error(data.error || "오류가 발생했습니다.");
  return data;
}

// ---------- 초기화 ----------
async function init() {
  try { await loadMe(); } catch (_) { location.href = "/login"; return; }
  connectSocket();
  bindUI();
  await loadRooms();
  await loadNotifications();
}

async function loadMe() {
  const { user } = await api("/api/me");
  currentUser = user;
  $("myName").textContent = user.username;
  $("myStatus").textContent = user.status_message || user.user_id;
  const av = $("myAvatar");
  if (user.profile_image) av.style.backgroundImage = `url('${user.profile_image}')`;
  else av.textContent = avatarText(user.username);
}

// ---------- Socket ----------
function connectSocket() {
  socket = io();
  socket.on("connect", () => { if (currentRoomId) socket.emit("join_room", {room_id: currentRoomId}); });
  socket.on("receive_message", (m) => {
    if (m.room_id === currentRoomId) {
      messagesCache.push(m);
      appendMessage(m);
      scrollToBottom();
      api(`/api/rooms/${currentRoomId}/read`, "POST").catch(()=>{});
    }
  });
  socket.on("message_updated", (m) => { if (m.room_id === currentRoomId) reloadMessages(); });
  socket.on("message_deleted", (d) => { if (d.room_id === currentRoomId) reloadMessages(); });
  socket.on("message_pinned", (d) => { if (d.room_id === currentRoomId) { reloadMessages(); loadRoomMeta(); } });
  socket.on("room_updated", () => loadRooms());
  socket.on("room_created", () => loadRooms());
  socket.on("room_deleted", (d) => {
    loadRooms();
    if (d.room_id === currentRoomId) { closeRoom(); showToast("채팅방이 삭제되었습니다."); }
  });
  socket.on("typing", (d) => { if (d.room_id === currentRoomId) showTyping(d.username); });
  socket.on("stop_typing", (d) => { if (d.room_id === currentRoomId) hideTyping(); });
  socket.on("error_message", (d) => showToast(d.error || "오류", "error"));
}

// ---------- 채팅방 목록 ----------
async function loadRooms(keyword = "") {
  try {
    const url = keyword ? `/api/rooms/search?q=${encodeURIComponent(keyword)}` : "/api/rooms";
    const { rooms } = await api(url);
    roomsCache = rooms;
    renderRooms(rooms);
  } catch (e) { showToast(e.message, "error"); }
}

function renderRooms(rooms) {
  const list = $("roomList");
  list.innerHTML = "";
  if (!rooms.length) {
    const empty = elc("div", "notif-item");
    empty.textContent = "채팅방이 없습니다.";
    list.appendChild(empty); return;
  }
  rooms.forEach((r) => {
    const item = elc("div", "room-item" + (r.id === currentRoomId ? " active" : ""));
    item.dataset.roomId = r.id;
    const isDirect = r.room_type === "direct";
    item.innerHTML = `
      <div class="avatar">${isDirect ? "" : (r.room_type==="notice" ? "📢" : "#")}</div>
      <div class="room-info">
        <div class="room-top">
          <span class="room-name">${isDirect ? '<span class="direct-dot">●</span> ' : ""}${escapeHtml(r.name)}</span>
          <span class="room-time">${formatTime(r.last_time)}</span>
        </div>
        <div class="room-bottom">
          <span class="room-last">${escapeHtml(r.last_message || "")}</span>
          <span class="room-tags">
            ${r.is_pinned ? '<span class="tag-pin">📌</span>' : ""}
            ${r.is_favorite ? '<span class="tag-fav">⭐</span>' : ""}
            ${r.unread_count ? `<span class="badge">${r.unread_count}</span>` : ""}
          </span>
        </div>
      </div>`;
    item.addEventListener("click", () => selectRoom(r.id));
    list.appendChild(item);
  });
}

// ---------- 방 선택 ----------
async function selectRoom(roomId) {
  if (socket && currentRoomId) socket.emit("leave_room", {room_id: currentRoomId});
  currentRoomId = roomId;
  clearReply(); clearSelectedFile();
  $("emptyState").hidden = true;
  $("chatPanel").hidden = false;
  $("panelExtra").hidden = true;
  $("messageSearchBar").hidden = true;
  $("appShell").dataset.show = "chat";   // 모바일: 채팅창 표시

  document.querySelectorAll(".room-item").forEach(el =>
    el.classList.toggle("active", Number(el.dataset.roomId) === roomId));

  await loadRoomMeta();
  await loadMessages(roomId);
  if (socket) socket.emit("join_room", {room_id: roomId});
  loadRooms();
}

async function loadRoomMeta() {
  try {
    const { room, members, pinned, role } = await api(`/api/rooms/${currentRoomId}`);
    currentRoom = { ...room, members, role };
    $("chatTitle").textContent = room.display_name || room.name;
    $("chatSubTitle").textContent = room.room_type === "direct"
      ? "1:1 채팅" : `멤버 ${members.length}명`;
    // owner/admin 만 일부 버튼 노출
    const isManager = (role === "owner" || role === "admin");
    $("renameBtn").style.display = (room.room_type === "direct") ? "none" : "";
    $("inviteBtn").style.display = (room.room_type === "direct") ? "none" : "";
    $("deleteRoomBtn").style.display = isManager ? "" : "none";
    renderPinned(pinned);
  } catch (e) { showToast(e.message, "error"); }
}

function renderPinned(pinned) {
  const box = $("pinnedMessageBox");
  if (!pinned || !pinned.length) { box.hidden = true; box.innerHTML = ""; return; }
  const p = pinned[0];
  box.hidden = false;
  box.innerHTML = `<span class="p-label">📌 고정</span>${escapeHtml((p.content || "[첨부]").slice(0,80))}`;
}

function closeRoom() {
  currentRoomId = null; currentRoom = null;
  $("chatPanel").hidden = true;
  $("emptyState").hidden = false;
  $("appShell").dataset.show = "list";
}

// ---------- 메시지 ----------
async function loadMessages(roomId) {
  try {
    const { messages } = await api(`/api/rooms/${roomId}/messages`);
    messagesCache = messages;
    renderMessages(messages);
    scrollToBottom();
  } catch (e) { showToast(e.message, "error"); }
}
async function reloadMessages() { if (currentRoomId) await loadMessages(currentRoomId); }

function renderMessages(messages) {
  const list = $("messageList");
  list.innerHTML = "";
  messages.forEach(m => list.appendChild(renderMessage(m)));
}

function appendMessage(m) { $("messageList").appendChild(renderMessage(m)); }

function renderMessage(m) {
  const mine = m.user_id === currentUser.id;
  const wrap = elc("div", "message " + (mine ? "message-mine" : "message-other"));
  wrap.dataset.id = m.id;

  let inner = `<div class="message-meta">${escapeHtml(m.username)} · ${formatTime(m.created_at)}` +
              `${m.is_edited ? " · edited" : ""}${m.is_pinned ? ' <span class="pinned-flag">📌</span>' : ""}</div>`;

  if (m.is_deleted) {
    inner += `<div class="message-bubble deleted">삭제된 메시지</div>`;
    wrap.innerHTML = inner;
    return wrap;
  }

  let bubble = "";
  if (m.reply_to) {
    bubble += `<div class="reply-quote"><span class="rq-name">${escapeHtml(m.reply_to.username)}</span><br>${escapeHtml((m.reply_to.content||"").slice(0,80))}</div>`;
  }
  if (m.content) bubble += escapeHtml(m.content);
  if (m.attachment) {
    const a = m.attachment;
    if (isImageFile(a.file_type, a.original_name)) {
      bubble += `<a href="${escapeHtml(a.url)}" target="_blank"><img class="attach-image" src="${escapeHtml(a.url)}" alt=""></a>`;
    } else {
      bubble += `<div class="attach-file"><span class="af-icon">📄</span>` +
        `<div><div class="af-name">${escapeHtml(a.original_name)}</div>` +
        `<div class="af-size">${formatFileSize(a.file_size)}</div></div>` +
        `<a href="${escapeHtml(a.url)}" download>Download</a></div>`;
    }
  }
  inner += `<div class="message-bubble">${bubble}</div>`;

  // 액션 버튼
  const acts = [];
  acts.push(`<button data-act="reply">답장</button>`);
  if (mine) {
    if (m.content) acts.push(`<button data-act="edit">수정</button>`);
    acts.push(`<button data-act="delete">삭제</button>`);
  } else if (currentUser.is_admin) {
    acts.push(`<button data-act="delete">삭제</button>`);
  }
  if (currentRoom && (currentRoom.role === "owner" || currentRoom.role === "admin")) {
    acts.push(`<button data-act="pin">${m.is_pinned ? "고정해제" : "고정"}</button>`);
  }
  inner += `<div class="msg-actions">${acts.join("")}</div>`;
  wrap.innerHTML = inner;

  wrap.querySelectorAll(".msg-actions button").forEach(btn => {
    btn.addEventListener("click", () => {
      const act = btn.dataset.act;
      if (act === "reply") replyToMessage(m.id);
      else if (act === "edit") editMessage(m.id);
      else if (act === "delete") deleteMessage(m.id);
      else if (act === "pin") pinMessage(m.id, !m.is_pinned);
    });
  });
  return wrap;
}

async function sendMessage() {
  const input = $("messageInput");
  const content = input.value.trim();
  if (!content && !uploadedAttachmentId) return;
  if (content.length > 2000) { showToast("메시지가 너무 깁니다.", "error"); return; }
  socket.emit("send_message", {
    room_id: currentRoomId, content,
    attachment_id: uploadedAttachmentId, reply_to_id: replyToMessageId,
  });
  input.value = ""; input.style.height = "";
  clearSelectedFile(); clearReply();
  socket.emit("stop_typing", {room_id: currentRoomId});
}

async function editMessage(messageId) {
  const m = messagesCache.find(x => x.id === messageId);
  const next = prompt("메시지 수정", m ? m.content : "");
  if (next === null) return;
  const content = next.trim();
  if (!content) return;
  try { await api(`/api/messages/${messageId}`, "PUT", {content}); }
  catch (e) { showToast(e.message, "error"); }
}

async function deleteMessage(messageId) {
  if (!confirm("이 메시지를 삭제할까요?")) return;
  try { await api(`/api/messages/${messageId}`, "DELETE"); }
  catch (e) { showToast(e.message, "error"); }
}

async function pinMessage(messageId, pinned) {
  try { await api(`/api/messages/${messageId}/pin`, "POST", {pinned}); }
  catch (e) { showToast(e.message, "error"); }
}

function replyToMessage(messageId) {
  const m = messagesCache.find(x => x.id === messageId);
  if (!m) return;
  replyToMessageId = messageId;
  const box = $("replyPreviewBox");
  box.hidden = false;
  box.innerHTML = `<span class="rp-text">↩ ${escapeHtml(m.username)}: ${escapeHtml((m.content||"[첨부]").slice(0,60))}</span><button class="btn-ghost" id="cancelReply">✕</button>`;
  $("cancelReply").addEventListener("click", clearReply);
  $("messageInput").focus();
}
function clearReply() { replyToMessageId = null; $("replyPreviewBox").hidden = true; $("replyPreviewBox").innerHTML = ""; }

// ---------- 1:1 채팅 / 검색 ----------
async function startDirectChat(userId) {
  try {
    const { room } = await api("/api/direct/start", "POST", {target_user_id: userId});
    $("userSearchInput").value = "";
    $("userSearchResults").hidden = true;
    await loadRooms();
    selectRoom(room.id);
  } catch (e) { showToast(e.message, "error"); }
}

async function searchUsers(keyword) {
  const box = $("userSearchResults");
  if (!keyword.trim()) { box.hidden = true; return; }
  try {
    const { users } = await api(`/api/users/search?q=${encodeURIComponent(keyword)}`);
    box.innerHTML = "";
    users.filter(u => u.id !== currentUser.id).forEach(u => {
      const row = elc("div", "result");
      row.innerHTML = `<div class="avatar" ${avatarStyle(u.profile_image)}>${u.profile_image?"":avatarText(u.username)}</div>` +
        `<div><div class="room-name">${escapeHtml(u.username)}</div><div class="cu-status">@${escapeHtml(u.user_id)}</div></div>`;
      row.addEventListener("click", () => startDirectChat(u.id));
      box.appendChild(row);
    });
    box.hidden = users.length === 0;
  } catch (e) { showToast(e.message, "error"); }
}

function searchRooms(keyword) { loadRooms(keyword); }

async function searchMessages(keyword) {
  if (!currentRoomId) return;
  try {
    const { messages } = await api(`/api/rooms/${currentRoomId}/messages/search?q=${encodeURIComponent(keyword)}`);
    renderMessages(messages);
    if (!keyword) scrollToBottom();
  } catch (e) { showToast(e.message, "error"); }
}

// ---------- 첨부 ----------
function handleFileSelect() {
  const file = $("fileInput").files[0];
  if (!file) return;
  if (file.size > 10*1024*1024) { showToast("파일은 10MB 이하만 가능합니다.", "error"); $("fileInput").value=""; return; }
  selectedFile = file;
  const box = $("selectedFileBox");
  box.hidden = false;
  box.innerHTML = `<span class="sf-text">📎 ${escapeHtml(file.name)} (${formatFileSize(file.size)})</span><button class="btn-ghost" id="cancelFile">✕</button>`;
  $("cancelFile").addEventListener("click", clearSelectedFile);
  uploadSelectedFile();
}

async function uploadSelectedFile() {
  if (!selectedFile) return;
  setLoading(true);
  try {
    const fd = new FormData();
    fd.append("file", selectedFile);
    const { attachment } = await api("/api/attachments", "POST", fd, true);
    uploadedAttachmentId = attachment.id;
    showToast("첨부 준비 완료. 전송을 누르세요.", "success");
  } catch (e) { showToast(e.message, "error"); clearSelectedFile(); }
  finally { setLoading(false); }
}

function clearSelectedFile() {
  selectedFile = null; uploadedAttachmentId = null;
  $("fileInput").value = "";
  $("selectedFileBox").hidden = true; $("selectedFileBox").innerHTML = "";
}

// ---------- 알림 ----------
async function loadNotifications() {
  try {
    const { notifications } = await api("/api/notifications");
    renderNotifications(notifications.filter(n => !n.is_read).slice(0, 5));
  } catch (_) {}
}
function renderNotifications(list) {
  const box = $("notificationBox");
  box.innerHTML = "";
  list.forEach(n => {
    const item = elc("div", "notif-item");
    item.innerHTML = `<div class="n-title">🔔 ${escapeHtml(n.title || "알림")}</div><div class="n-body">${escapeHtml(n.body || "")}</div>`;
    item.addEventListener("click", () => {
      api(`/api/notifications/${n.id}/read`, "POST").catch(()=>{});
      if (n.room_id) selectRoom(n.room_id);
      item.remove();
    });
    box.appendChild(item);
  });
}

// ---------- 멤버/방 관리 ----------
async function showMembers() {
  const extra = $("panelExtra");
  if (!extra.hidden) { extra.hidden = true; return; }
  const { members } = await api(`/api/rooms/${currentRoomId}/members`);
  extra.hidden = false;
  extra.innerHTML = `<h4>멤버 ${members.length}명</h4>` + members.map(m =>
    `<div class="member-row"><div class="avatar" ${avatarStyle(m.profile_image)}>${m.profile_image?"":avatarText(m.username)}</div>` +
    `<div><div class="room-name">${escapeHtml(m.username)} <span class="cu-status">${m.role}</span></div></div></div>`).join("");
}

async function inviteMember() {
  const keyword = prompt("초대할 사용자 아이디 또는 이름 검색");
  if (!keyword) return;
  try {
    const { users } = await api(`/api/users/search?q=${encodeURIComponent(keyword)}`);
    const list = users.filter(u => u.id !== currentUser.id);
    if (!list.length) { showToast("사용자를 찾을 수 없습니다.", "error"); return; }
    const u = list[0];
    if (!confirm(`'${u.username}' 님을 초대할까요?`)) return;
    await api(`/api/rooms/${currentRoomId}/members`, "POST", {user_id: u.id});
    showToast("초대 완료", "success");
    loadRoomMeta();
  } catch (e) { showToast(e.message, "error"); }
}

async function renameRoom() {
  const name = prompt("새 채팅방 이름", currentRoom ? currentRoom.name : "");
  if (name === null) return;
  const description = prompt("설명 (선택)", currentRoom ? (currentRoom.description || "") : "");
  try {
    await api(`/api/rooms/${currentRoomId}`, "PUT", {name: name.trim(), description: (description||"").trim()});
    showToast("변경 완료", "success");
    loadRoomMeta(); loadRooms();
  } catch (e) { showToast(e.message, "error"); }
}

async function leaveRoom() {
  if (!confirm("이 채팅방에서 나갈까요?")) return;
  try {
    await api(`/api/rooms/${currentRoomId}/members/${currentUser.id}`, "DELETE");
    closeRoom(); loadRooms(); showToast("나갔습니다.");
  } catch (e) { showToast(e.message, "error"); }
}

async function deleteRoom() {
  if (!confirm("채팅방을 삭제할까요? 모든 메시지가 사라집니다.")) return;
  try {
    await api(`/api/rooms/${currentRoomId}`, "DELETE");
    closeRoom(); loadRooms(); showToast("삭제되었습니다.");
  } catch (e) { showToast(e.message, "error"); }
}

async function togglePinRoom() {
  const r = roomsCache.find(x => x.id === currentRoomId);
  try { await api(`/api/rooms/${currentRoomId}/pin`, "POST", {pinned: !(r && r.is_pinned)}); loadRooms(); }
  catch (e) { showToast(e.message, "error"); }
}

// ---------- 스크롤/타이핑 ----------
function scrollToBottom() { const l = $("messageList"); l.scrollTop = l.scrollHeight; }
function showTyping(name) { const t = $("typingIndicator"); t.hidden = false; t.textContent = `${name} 입력 중…`; }
function hideTyping() { $("typingIndicator").hidden = true; }

// ---------- 모바일 ----------
function handleMobileBack() { $("appShell").dataset.show = "list"; }

// ---------- UI 바인딩 ----------
function bindUI() {
  // 메시지 입력
  const input = $("messageInput");
  $("messageForm").addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
    if (socket && currentRoomId) {
      socket.emit("typing", {room_id: currentRoomId});
      clearTimeout(typingTimer);
      typingTimer = setTimeout(() => socket.emit("stop_typing", {room_id: currentRoomId}), 2000);
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // 첨부
  $("attachBtn").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", handleFileSelect);

  // 검색 (debounce 300ms)
  $("roomSearchInput").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => searchRooms(v), 300);
  });
  $("userSearchInput").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => searchUsers(v), 300);
  });
  $("messageSearchInput").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => searchMessages(v), 300);
  });

  // 새 그룹방
  $("openCreateRoom").addEventListener("click", () => {
    $("createRoomForm").hidden = false; $("openCreateRoom").hidden = true; });
  $("cancelCreateRoom").addEventListener("click", () => {
    $("createRoomForm").hidden = true; $("openCreateRoom").hidden = false; });
  $("createRoomForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("newRoomName").value.trim();
    if (!name) return;
    try {
      const { room } = await api("/api/rooms", "POST", {name, description: $("newRoomDesc").value.trim()});
      $("newRoomName").value = ""; $("newRoomDesc").value = "";
      $("createRoomForm").hidden = true; $("openCreateRoom").hidden = false;
      await loadRooms(); selectRoom(room.id);
    } catch (err) { showToast(err.message, "error"); }
  });

  // 헤더 액션
  $("mobileBackBtn").addEventListener("click", handleMobileBack);
  $("membersBtn").addEventListener("click", showMembers);
  $("inviteBtn").addEventListener("click", inviteMember);
  $("renameBtn").addEventListener("click", renameRoom);
  $("leaveBtn").addEventListener("click", leaveRoom);
  $("deleteRoomBtn").addEventListener("click", deleteRoom);
  $("pinToggleBtn").addEventListener("click", togglePinRoom);
  $("searchMsgToggle").addEventListener("click", () => {
    const bar = $("messageSearchBar");
    bar.hidden = !bar.hidden;
    if (!bar.hidden) $("messageSearchInput").focus();
  });
  $("closeMsgSearch").addEventListener("click", () => {
    $("messageSearchBar").hidden = true; $("messageSearchInput").value = ""; reloadMessages();
  });
}

document.addEventListener("DOMContentLoaded", init);
})();
