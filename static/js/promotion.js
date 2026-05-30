/* promotion.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const ST = {draft:"초안", pending_review:"검토 대기", approved:"승인(노출중)", rejected:"반려", paused:"일시중지"};

async function loadChannels() {
  try {
    const { channels } = await API.call("/api/channels/mine");
    const s = $("channel"); s.innerHTML = "";
    if (!channels.length) s.innerHTML = '<option value="">(채널 없음 — 미디어에서 먼저 생성)</option>';
    channels.forEach(c => { const o = document.createElement("option"); o.value = c.id; o.textContent = c.name; s.appendChild(o); });
  } catch (e) { needLogin(e); }
}
async function loadMine() {
  try {
    const { promotions } = await API.call("/api/promotions/my");
    const box = $("list"); box.innerHTML = "";
    if (!promotions.length) { box.innerHTML = '<p class="muted">캠페인이 없습니다.</p>'; return; }
    for (const p of promotions) {
      let stats = "";
      try { const r = await API.call(`/api/promotions/${p.id}/stats`); stats = `노출 ${r.stats.impression} · 클릭 ${r.stats.click} · CTR ${r.stats.ctr}%`; } catch(_){}
      const row = document.createElement("div"); row.className = "mrow";
      row.innerHTML = `<div class="main"><div>${esc(p.title)} <span class="pill">${ST[p.status]||p.status}</span></div>
        <div class="sub">${esc(p.channel_name)} · ${stats}</div>
        ${p.rejection_reason ? `<div class="sub err">반려: ${esc(p.rejection_reason)}</div>` : ''}</div>`;
      if (p.status === "draft") row.appendChild(btn("검수 신청", `/api/promotions/${p.id}/submit`, "검수 신청 완료"));
      else if (p.status === "approved") row.appendChild(btn("일시중지", `/api/promotions/${p.id}/pause`, "일시중지됨", true));
      else if (p.status === "paused") row.appendChild(btn("재개", `/api/promotions/${p.id}/resume`, "재개됨", true));
      box.appendChild(row);
    }
  } catch (e) { needLogin(e) || toast(e.message, "error"); }
}
function btn(label, url, okmsg, ghost) {
  const b = document.createElement("button"); b.className = "mbtn" + (ghost ? " ghost" : ""); b.textContent = label;
  b.onclick = async () => { try { await API.call(url, "POST"); toast(okmsg, "ok"); loadMine(); } catch(e){ toast(e.message,"error"); } };
  return b;
}
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!$("channel").value || !$("title").value.trim()) { $("msg").textContent = "채널과 제목을 입력하세요."; $("msg").className = "mmsg err"; return; }
  try {
    await API.call("/api/promotions", "POST", {channel_id: $("channel").value, title: $("title").value.trim(),
      description: $("desc").value.trim(), placement: $("placement").value});
    $("title").value = ""; $("desc").value = "";
    $("msg").textContent = "캠페인 생성됨. 검수 신청을 누르세요."; $("msg").className = "mmsg ok"; loadMine();
  } catch (e) { if (!needLogin(e)) { $("msg").textContent = e.message; $("msg").className = "mmsg err"; } }
});
document.addEventListener("DOMContentLoaded", () => { loadChannels(); loadMine(); });
})();
