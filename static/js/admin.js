/* admin.js — 관리자 페이지 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (v) => (v ?? "").toString().replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

async function api(url, method = "GET", body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch(url, opt);
  let data = {}; try { data = await res.json(); } catch (_) {}
  if (!res.ok || data.ok === false) throw new Error(data.error || "오류가 발생했습니다.");
  return data;
}
function toast(t, type) { const e = $("toast"); e.textContent = t; e.className = "toast " + (type||""); e.hidden = false; setTimeout(()=>e.hidden=true, 2400); }

async function loadSummary() {
  const { summary } = await api("/api/admin/summary");
  $("statUsers").textContent = summary.users;
  $("statRooms").textContent = summary.rooms;
  $("statMessages").textContent = summary.messages;
}

async function loadUsers() {
  const { users } = await api("/api/admin/users");
  const box = $("adminUsers"); box.innerHTML = "";
  users.forEach(u => {
    const row = document.createElement("div"); row.className = "admin-row";
    row.innerHTML = `<div class="ar-main"><div>${esc(u.username)} ` +
      `${u.is_admin ? '<span class="pill">admin</span>' : ''}</div>` +
      `<div class="ar-sub">@${esc(u.user_id)} · 가입 ${esc(u.created_at)}</div></div>` +
      `<span class="pill ${u.is_active ? "on":"off"}">${u.is_active ? "활성":"비활성"}</span>` +
      `<button class="btn-ghost" data-id="${u.id}" data-active="${u.is_active?0:1}">${u.is_active?"비활성화":"활성화"}</button>`;
    row.querySelector("button").addEventListener("click", async (e) => {
      const id = e.target.dataset.id, active = e.target.dataset.active === "1";
      try { await api(`/api/admin/users/${id}/active`, "POST", {active}); loadUsers(); }
      catch (err) { toast(err.message, "err"); }
    });
    box.appendChild(row);
  });
}

async function loadRooms() {
  const { rooms } = await api("/api/admin/rooms");
  const box = $("adminRooms"); box.innerHTML = "";
  rooms.forEach(r => {
    const row = document.createElement("div"); row.className = "admin-row";
    row.innerHTML = `<div class="ar-main"><div>${esc(r.name)} <span class="pill">${esc(r.room_type)}</span></div>` +
      `<div class="ar-sub">멤버 ${r.members} · 메시지 ${r.msgs}</div></div>` +
      `<button class="btn-ghost" data-id="${r.id}">삭제</button>`;
    row.querySelector("button").addEventListener("click", async (e) => {
      if (!confirm("이 채팅방을 삭제할까요?")) return;
      try { await api(`/api/admin/rooms/${e.target.dataset.id}`, "DELETE"); loadRooms(); loadSummary(); }
      catch (err) { toast(err.message, "err"); }
    });
    box.appendChild(row);
  });
}

$("noticeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/admin/notice", "POST", {
      name: $("noticeName").value.trim() || "공지",
      message: $("noticeMessage").value.trim(),
    });
    $("noticeMessage").value = "";
    toast("공지방이 생성되었습니다.", "ok");
    loadRooms(); loadSummary();
  } catch (err) { toast(err.message, "err"); }
});

document.addEventListener("DOMContentLoaded", () => {
  loadSummary().catch(()=>{}); loadUsers().catch(()=>{}); loadRooms().catch(()=>{});
});
})();
