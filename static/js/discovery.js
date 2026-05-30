/* discovery.js — 채널 검색/추천/홍보 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
let selectedCat = "";
let searchTimer = null;

function card(c) {
  const badge = c.official_badge ? '<span class="ofc-badge">공식</span>' : "";
  const sponsored = c.is_promoted ? '<span class="sponsored">홍보</span>' : "";
  const el = document.createElement("div");
  el.className = "channel-card" + (c.is_promoted ? " promoted" : "");
  el.innerHTML = `
    <div class="cc-cover">${c.cover_image_url ? `<img src="${esc(c.cover_image_url)}">` : "#"}</div>
    <div class="cc-body">
      <div class="cc-title">${esc(c.name)} ${badge} ${sponsored}</div>
      <div class="cc-org">${c.organization_name ? esc(c.organization_name)+" · " : ""}${esc(c.category||"")}</div>
      <div class="cc-desc">${esc((c.description||"").slice(0,70))}</div>
      <div class="cc-foot"><span>구독 ${c.follower_count||0}</span>
        <a class="btn-primary sm" href="/channel/${c.room_id}">입장</a></div>
    </div>`;
  if (c.is_promoted && c.promotion_id) {
    // 노출 기록
    API.call(`/api/discovery/promotions/${c.promotion_id}/event`, "POST", {event_type:"impression"}).catch(()=>{});
    el.querySelector("a").addEventListener("click", () =>
      API.call(`/api/discovery/promotions/${c.promotion_id}/event`, "POST", {event_type:"click"}).catch(()=>{}));
  }
  return el;
}

async function loadCategories() {
  try {
    const { categories } = await API.call("/api/discovery/categories");
    const box = $("catChips");
    const all = document.createElement("button");
    all.className = "chip active"; all.textContent = "전체";
    all.addEventListener("click", () => { selectedCat=""; setActive(all); run(); });
    box.appendChild(all);
    categories.forEach(c => {
      const b = document.createElement("button");
      b.className = "chip"; b.textContent = c.name;
      b.addEventListener("click", () => { selectedCat=c.id; setActive(b); run(); });
      box.appendChild(b);
    });
  } catch (e) { toast(e.message, "error"); }
}
function setActive(btn) {
  document.querySelectorAll(".chip").forEach(c=>c.classList.remove("active"));
  btn.classList.add("active");
}

async function run() {
  const q = $("discSearch").value.trim();
  const sort = $("discSort").value;
  try {
    const params = new URLSearchParams({ q, sort });
    if (selectedCat) params.set("category", selectedCat);
    const { promoted, rooms } = await API.call(`/api/discovery/search?${params}`);
    const ps = $("promotedSection"), pl = $("promotedList");
    pl.innerHTML = "";
    if (promoted && promoted.length) { ps.hidden = false; promoted.forEach(c=>pl.appendChild(card(c))); }
    else ps.hidden = true;
    const rl = $("resultsList"); rl.innerHTML = "";
    if (!rooms.length) rl.innerHTML = '<p class="muted">검색 결과가 없습니다.</p>';
    rooms.forEach(c => rl.appendChild(card(c)));
  } catch (e) { toast(e.message, "error"); }
}

$("discSearch").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer=setTimeout(run,300); });
$("discSort").addEventListener("change", run);
document.addEventListener("DOMContentLoaded", () => { loadCategories(); run(); });
})();
