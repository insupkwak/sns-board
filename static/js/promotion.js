/* promotion.js — 홍보 캠페인 생성/제출/성과 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const STATUS = {draft:"초안", pending_review:"검토 대기", approved:"승인(노출중)",
  rejected:"반려", paused:"일시중지", active:"진행", ended:"종료", suspended:"정지"};

async function loadRooms() {
  try {
    const { rooms } = await API.call("/api/rooms");
    const sel = $("promoRoom"); sel.innerHTML = "";
    const mine = rooms.filter(r => ["channel","news_channel","discussion","chat"].includes(r.room_type));
    if (!mine.length) sel.innerHTML = '<option value="">(운영 중인 채널 없음)</option>';
    mine.forEach(r => { const o=document.createElement("option"); o.value=r.id; o.textContent=r.name; sel.appendChild(o); });
  } catch (_) {}
}

async function loadMine() {
  try {
    const { promotions } = await API.call("/api/promotions/my");
    const box = $("promoList"); box.innerHTML = "";
    if (!promotions.length) { box.innerHTML = '<p class="muted">캠페인이 없습니다.</p>'; return; }
    for (const p of promotions) {
      const row = document.createElement("div"); row.className = "admin-row";
      let stats = "";
      try { const r = await API.call(`/api/promotions/${p.id}/stats`);
        stats = `노출 ${r.stats.impression} · 클릭 ${r.stats.click} · 입장 ${r.stats.join} · CTR ${r.stats.ctr}%`; } catch(_){}
      row.innerHTML = `<div class="ar-main"><div>${esc(p.title)} <span class="pill">${STATUS[p.status]||p.status}</span></div>
        <div class="ar-sub">${esc(p.room_name)} · ${stats}</div>
        ${p.rejection_reason ? `<div class="ar-sub err">반려: ${esc(p.rejection_reason)}</div>`:''}</div>
        <div class="promo-btns"></div>`;
      const btns = row.querySelector(".promo-btns");
      if (p.status === "draft") {
        const b = document.createElement("button"); b.className="btn-primary sm"; b.textContent="검수 신청";
        b.addEventListener("click", async ()=>{ try{ await API.call(`/api/promotions/${p.id}/submit`,"POST"); toast("검수 신청 완료","success"); loadMine(); }catch(e){toast(e.message,"error");} });
        btns.appendChild(b);
      } else if (p.status === "approved") {
        const b = document.createElement("button"); b.className="btn-ghost"; b.textContent="일시중지";
        b.addEventListener("click", async ()=>{ try{ await API.call(`/api/promotions/${p.id}/pause`,"POST"); loadMine(); }catch(e){toast(e.message,"error");} });
        btns.appendChild(b);
      } else if (p.status === "paused") {
        const b = document.createElement("button"); b.className="btn-ghost"; b.textContent="재개";
        b.addEventListener("click", async ()=>{ try{ await API.call(`/api/promotions/${p.id}/resume`,"POST"); loadMine(); }catch(e){toast(e.message,"error");} });
        btns.appendChild(b);
      }
      box.appendChild(row);
    }
  } catch (e) { toast(e.message, "error"); }
}

$("promoForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const room_id = $("promoRoom").value, title = $("promoTitle").value.trim();
  if (!room_id || !title) { $("promoMsg").textContent="채널과 제목을 입력하세요."; $("promoMsg").className="form-msg err"; return; }
  try {
    await API.call("/api/promotions", "POST", {room_id, title,
      description:$("promoDesc").value.trim(), placement:$("promoPlacement").value});
    $("promoTitle").value=""; $("promoDesc").value="";
    $("promoMsg").textContent="캠페인을 만들었습니다. 검수 신청을 누르세요."; $("promoMsg").className="form-msg ok";
    loadMine();
  } catch (err) { $("promoMsg").textContent=err.message; $("promoMsg").className="form-msg err"; }
});

document.addEventListener("DOMContentLoaded", () => { loadRooms(); loadMine(); });
})();
