/* channel.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const cid = window.__cid;
let ch = null;

async function load() {
  try {
    const { channel, articles } = await API.call(`/api/channels/${cid}`);
    ch = channel; head(channel); arts(articles);
  } catch (e) { $("head").textContent = e.message; }
}
function head(c) {
  const badge = c.official_badge ? '<span class="b-official">공식</span>' : "";
  $("head").innerHTML = `
    <div class="chan-cover">${c.cover_image_url ? `<img src="${esc(c.cover_image_url)}">` : ""}</div>
    <div class="chan-meta">
      <div class="chan-name">${esc(c.name)} ${badge}</div>
      <div class="cc-sub">${c.organization ? esc(c.organization.name)+" · " : ""}${esc(c.media_category||c.channel_type)}</div>
      <div>${esc(c.description||"")}</div>
      <div class="muted">구독 <b id="fc">${c.follower_count}</b></div>
      <div class="chan-actions">
        <button id="follow" class="mbtn">${c.is_following ? "구독 중" : "구독"}</button>
        <button id="report" class="mbtn ghost">신고</button>
      </div>
    </div>`;
  $("follow").onclick = toggle;
  $("report").onclick = report;
}
async function toggle() {
  try {
    const r = await API.call(`/api/channels/${cid}/follow`, "POST", {follow: !ch.is_following});
    ch.is_following = r.following; $("follow").textContent = r.following ? "구독 중" : "구독"; $("fc").textContent = r.follower_count;
    toast(r.following ? "구독했습니다." : "구독 해제", "ok");
  } catch (e) { if (!needLogin(e)) toast(e.message, "error"); }
}
async function report() {
  const reason = prompt("신고 사유 (spam, abuse, fake_news, copyright 등)", "spam"); if (!reason) return;
  try { await API.call("/api/reports", "POST", {target_type:"channel", target_id:cid, reason}); toast("신고 접수", "ok"); }
  catch (e) { if (!needLogin(e)) toast(e.message, "error"); }
}
function arts(list) {
  const box = $("articles");
  if (!list.length) { box.innerHTML = '<p class="muted">발행된 기사가 없습니다.</p>'; return; }
  box.innerHTML = "";
  list.forEach(a => { const el = document.createElement("a"); el.className = "arow"; el.href = `/article/${a.id}`;
    el.innerHTML = `${a.is_breaking ? '<span class="b-breaking">속보</span> ' : ""}<span class="at">${esc(a.title)}</span>`+
      `<div class="as">${esc(a.author_name)} · ${esc(a.published_at||a.created_at)}</div>`;
    box.appendChild(el); });
}
document.addEventListener("DOMContentLoaded", load);
})();
