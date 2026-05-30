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

// ---- 3차: 미디어 운영 ----
async function loadMediaSummary() {
  const { summary } = await api("/api/admin/media-summary");
  $("statOrgs").textContent = summary.organizations;
  $("statPromo").textContent = summary.pending_promotions;
  $("statReports").textContent = summary.pending_reports;
  $("statArticles").textContent = summary.articles;
}

const VS = {pending:"검수중", verified:"인증완료", rejected:"반려", suspended:"정지"};
async function loadOrgs() {
  const { organizations } = await api("/api/admin/organizations");
  const box = $("adminOrgs"); box.innerHTML = "";
  if (!organizations.length) { box.innerHTML='<p class="muted">조직이 없습니다.</p>'; return; }
  organizations.forEach(o => {
    const row = document.createElement("div"); row.className="admin-row";
    row.innerHTML = `<div class="ar-main"><div>${esc(o.name)} <span class="pill">${VS[o.verification_status]||o.verification_status}</span></div>
      <div class="ar-sub">${esc(o.org_type)}</div></div>`;
    if (o.verification_status !== "verified") {
      const v=document.createElement("button"); v.className="btn-primary sm"; v.textContent="인증";
      v.addEventListener("click", async()=>{ await api(`/api/admin/organizations/${o.id}/verify`,"POST"); loadOrgs(); loadMediaSummary(); toast("인증 완료","ok"); });
      const r=document.createElement("button"); r.className="btn-ghost"; r.textContent="반려";
      r.addEventListener("click", async()=>{ await api(`/api/admin/organizations/${o.id}/reject`,"POST"); loadOrgs(); });
      row.appendChild(v); row.appendChild(r);
    }
    box.appendChild(row);
  });
}

async function loadPromos() {
  const { promotions } = await api("/api/admin/promotions");
  const box = $("adminPromos"); box.innerHTML="";
  if (!promotions.length) { box.innerHTML='<p class="muted">대기 중인 홍보가 없습니다.</p>'; return; }
  promotions.forEach(p => {
    const row=document.createElement("div"); row.className="admin-row";
    row.innerHTML=`<div class="ar-main"><div>${esc(p.title)}</div><div class="ar-sub">채널: ${esc(p.room_name)} · 위치: ${esc(p.placement)}</div></div>`;
    const a=document.createElement("button"); a.className="btn-primary sm"; a.textContent="승인";
    a.addEventListener("click", async()=>{ await api(`/api/admin/promotions/${p.id}/approve`,"POST"); loadPromos(); loadMediaSummary(); toast("승인됨(노출 시작)","ok"); });
    const r=document.createElement("button"); r.className="btn-ghost"; r.textContent="반려";
    r.addEventListener("click", async()=>{ const reason=prompt("반려 사유","홍보 정책 위반")||""; await api(`/api/admin/promotions/${p.id}/reject`,"POST",{reason}); loadPromos(); loadMediaSummary(); });
    row.appendChild(a); row.appendChild(r);
    box.appendChild(row);
  });
}

async function loadReports() {
  const { reports } = await api("/api/admin/reports");
  const box=$("adminReports"); box.innerHTML="";
  if (!reports.length) { box.innerHTML='<p class="muted">대기 중인 신고가 없습니다.</p>'; return; }
  reports.forEach(rp => {
    const row=document.createElement("div"); row.className="admin-row";
    row.innerHTML=`<div class="ar-main"><div>${esc(rp.target_type)} #${rp.target_id} · ${esc(rp.reason)}</div>
      <div class="ar-sub">신고자: ${esc(rp.reporter)} · ${esc(rp.created_at)}${rp.detail?' · '+esc(rp.detail):''}</div></div>`;
    const h=document.createElement("button"); h.className="btn-primary sm"; h.textContent="처리완료";
    h.addEventListener("click", async()=>{ await api(`/api/admin/reports/${rp.id}/handle`,"POST",{status:"resolved"}); loadReports(); loadMediaSummary(); });
    row.appendChild(h);
    box.appendChild(row);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadSummary().catch(()=>{}); loadUsers().catch(()=>{}); loadRooms().catch(()=>{});
  loadMediaSummary().catch(()=>{}); loadOrgs().catch(()=>{}); loadPromos().catch(()=>{}); loadReports().catch(()=>{});
});
})();
