/* discovery.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
let cat = "", timer = null;

function card(c) {
  const el = document.createElement("div");
  el.className = "ccard" + (c.is_promoted ? " promoted" : "");
  const badges = (c.official_badge ? '<span class="b-official">공식</span> ' : "") +
                 (c.is_promoted ? '<span class="b-sponsored">홍보</span>' : "");
  el.innerHTML = `
    <div class="cc-cover">${c.cover_image_url ? `<img src="${esc(c.cover_image_url)}">` : "#"}</div>
    <div class="cc-body">
      <div class="cc-title">${esc(c.name)} ${badges}</div>
      <div class="cc-sub">${c.organization_name ? esc(c.organization_name)+" · " : ""}${esc(c.media_category||"")}</div>
      <div class="cc-desc">${esc((c.description||"").slice(0,70))}</div>
      <div class="cc-foot"><span>구독 ${c.follower_count||0}</span><a class="mbtn" href="/channel/${c.channel_id}">입장</a></div>
    </div>`;
  if (c.is_promoted && c.promotion_id) {
    API.call(`/api/discovery/promotions/${c.promotion_id}/event`, "POST", {event_type:"impression"}).catch(()=>{});
    el.querySelector("a").addEventListener("click", () =>
      API.call(`/api/discovery/promotions/${c.promotion_id}/event`, "POST", {event_type:"click"}).catch(()=>{}));
  }
  return el;
}

async function loadCats() {
  try {
    const { categories } = await API.call("/api/discovery/categories");
    const box = $("chips");
    const all = document.createElement("button"); all.className = "chip active"; all.textContent = "전체";
    all.onclick = () => { cat = ""; active(all); run(); }; box.appendChild(all);
    categories.forEach(c => { const b = document.createElement("button"); b.className = "chip"; b.textContent = c;
      b.onclick = () => { cat = c; active(b); run(); }; box.appendChild(b); });
  } catch (_) {}
}
function active(b){ document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active")); b.classList.add("active"); }

async function run() {
  try {
    const p = new URLSearchParams({ q: $("q").value.trim(), sort: $("sort").value });
    if (cat) p.set("category", cat);
    const { promoted, channels } = await API.call(`/api/discovery/search?${p}`);
    const ps = $("promotedSec"), pl = $("promoted"); pl.innerHTML = "";
    if (promoted.length) { ps.hidden = false; promoted.forEach(c => pl.appendChild(card(c))); } else ps.hidden = true;
    const r = $("results"); r.innerHTML = "";
    if (!channels.length) r.innerHTML = '<p class="muted">검색 결과가 없습니다.</p>';
    channels.forEach(c => r.appendChild(card(c)));
  } catch (e) { toast(e.message, "error"); }
}

$("q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 300); });
$("sort").addEventListener("change", run);
document.addEventListener("DOMContentLoaded", () => { loadCats(); run(); });
})();
