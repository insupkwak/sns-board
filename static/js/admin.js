/* admin.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const VS = {pending:"검수중", verified:"인증완료", rejected:"반려"};

async function start() {
  try {
    const { summary } = await API.call("/api/admin/summary");
    $("panel").hidden = false;
    $("sUsers").textContent = summary.users; $("sPosts").textContent = summary.posts;
    $("sOrgs").textContent = summary.organizations; $("sChannels").textContent = summary.channels;
    $("sArticles").textContent = summary.articles; $("sPromo").textContent = summary.pending_promotions;
    $("sReports").textContent = summary.pending_reports; $("sOfficial").textContent = summary.official_channels;
    loadOrgs(); loadPromos(); loadReports();
  } catch (e) { $("gate").hidden = false; }
}

async function loadOrgs() {
  const { organizations } = await API.call("/api/admin/organizations");
  const box = $("orgs"); box.innerHTML = organizations.length ? "" : '<p class="muted">조직이 없습니다.</p>';
  organizations.forEach(o => { const row = document.createElement("div"); row.className = "mrow";
    row.innerHTML = `<div class="main"><div>${esc(o.name)} <span class="pill">${VS[o.verification_status]||o.verification_status}</span></div><div class="sub">${esc(o.org_type)}</div></div>`;
    if (o.verification_status !== "verified") {
      row.appendChild(act("인증", `/api/admin/organizations/${o.id}/verify`, ()=>{loadOrgs();start();}));
      row.appendChild(act("반려", `/api/admin/organizations/${o.id}/reject`, loadOrgs, true));
    }
    box.appendChild(row); });
}
async function loadPromos() {
  const { promotions } = await API.call("/api/admin/promotions");
  const box = $("promos"); box.innerHTML = promotions.length ? "" : '<p class="muted">대기 중인 홍보가 없습니다.</p>';
  promotions.forEach(p => { const row = document.createElement("div"); row.className = "mrow";
    row.innerHTML = `<div class="main"><div>${esc(p.title)}</div><div class="sub">채널: ${esc(p.channel_name)} · 위치: ${esc(p.placement)}</div></div>`;
    row.appendChild(act("승인", `/api/admin/promotions/${p.id}/approve`, ()=>{loadPromos();start();}));
    const r = document.createElement("button"); r.className = "mbtn ghost"; r.textContent = "반려";
    r.onclick = async () => { const reason = prompt("반려 사유", "정책 위반")||""; try { await API.call(`/api/admin/promotions/${p.id}/reject`, "POST", {reason}); loadPromos(); start(); } catch(e){ toast(e.message,"error"); } };
    row.appendChild(r); box.appendChild(row); });
}
async function loadReports() {
  const { reports } = await API.call("/api/admin/reports");
  const box = $("reports"); box.innerHTML = reports.length ? "" : '<p class="muted">대기 중인 신고가 없습니다.</p>';
  reports.forEach(rp => { const row = document.createElement("div"); row.className = "mrow";
    row.innerHTML = `<div class="main"><div>${esc(rp.target_type)} #${rp.target_id} · ${esc(rp.reason)}</div><div class="sub">신고자 ${esc(rp.reporter)} · ${esc(rp.created_at)}</div></div>`;
    row.appendChild(act("처리완료", `/api/admin/reports/${rp.id}/handle`, ()=>{loadReports();start();}));
    box.appendChild(row); });
}
function act(label, url, after, ghost) {
  const b = document.createElement("button"); b.className = "mbtn" + (ghost ? " ghost" : ""); b.textContent = label;
  b.onclick = async () => { try { await API.call(url, "POST"); toast("처리됨", "ok"); after && after(); } catch(e){ toast(e.message,"error"); } };
  return b;
}
document.addEventListener("DOMContentLoaded", start);
})();
