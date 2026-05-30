/* channel.js — 채널 소개 + 구독 + 기사 목록 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const rid = window.__roomId;
let ch = null;

async function load() {
  try {
    const { channel, articles } = await API.call(`/api/channels/${rid}`);
    ch = channel;
    renderHead(channel);
    renderArticles(articles);
  } catch (e) { $("channelHead").textContent = e.message; }
}

function renderHead(c) {
  const badge = c.official_badge ? '<span class="ofc-badge">공식</span>' : "";
  $("channelHead").innerHTML = `
    <div class="ch-cover">${c.cover_image_url ? `<img src="${esc(c.cover_image_url)}">` : ""}</div>
    <div class="ch-meta">
      <div class="ch-name">${esc(c.name)} ${badge}</div>
      <div class="ch-sub">${c.organization ? esc(c.organization.name)+" · " : ""}${esc(c.category||c.room_type)}</div>
      <div class="ch-desc">${esc(c.description||"")}</div>
      <div class="ch-stats">구독 <b id="followCount">${c.follower_count}</b> · 멤버 ${c.member_count}</div>
      <div class="ch-actions">
        <button id="followBtn" class="btn-primary">${c.is_following ? "구독 중" : "구독"}</button>
        <a class="btn-soft inline" href="/chat">채팅 입장</a>
        <button id="reportBtn" class="btn-ghost">신고</button>
      </div>
    </div>`;
  $("followBtn").addEventListener("click", toggleFollow);
  $("reportBtn").addEventListener("click", reportChannel);
}

async function toggleFollow() {
  try {
    const { following, follower_count } = await API.call(
      `/api/channels/${rid}/follow`, "POST", {follow: !ch.is_following});
    ch.is_following = following;
    $("followBtn").textContent = following ? "구독 중" : "구독";
    $("followCount").textContent = follower_count;
    toast(following ? "구독했습니다." : "구독을 해제했습니다.", "success");
  } catch (e) {
    if ((e.message||"").includes("로그인")) location.href = "/login";
    else toast(e.message, "error");
  }
}

async function reportChannel() {
  const reason = prompt("신고 사유 (spam, abuse, fake_news, copyright 등)", "spam");
  if (!reason) return;
  try { await API.call("/api/reports", "POST", {target_type:"room", target_id:rid, reason});
    toast("신고가 접수되었습니다.", "success"); }
  catch (e) { toast(e.message, "error"); }
}

function renderArticles(list) {
  const box = $("channelArticles");
  if (!list || !list.length) { box.innerHTML = '<p class="muted">발행된 기사가 없습니다.</p>'; return; }
  box.innerHTML = "";
  list.forEach(a => {
    const el = document.createElement("a");
    el.className = "article-row"; el.href = `/article/${a.id}`;
    el.innerHTML = `${a.is_breaking ? '<span class="breaking">속보</span> ' : ""}` +
      `${a.is_pinned ? '📌 ' : ''}<span class="ar-title">${esc(a.title)}</span>` +
      `<div class="ar-sub">${esc(a.author_name)} · ${esc(a.published_at||a.created_at)}</div>`;
    box.appendChild(el);
  });
}

document.addEventListener("DOMContentLoaded", load);
})();
