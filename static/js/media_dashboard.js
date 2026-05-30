/* media_dashboard.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const VS = {pending:"검수중", verified:"인증완료", rejected:"반려"};

async function loadOrgs() {
  try {
    const { organizations } = await API.call("/api/organizations/mine");
    const sel = $("chOrg"); sel.innerHTML = '<option value="">(없음)</option>';
    const box = $("orgList"); box.innerHTML = organizations.length ? "" : '<p class="muted">조직이 없습니다.</p>';
    organizations.forEach(o => {
      const opt = document.createElement("option"); opt.value = o.id; opt.textContent = o.name; sel.appendChild(opt);
      const row = document.createElement("div"); row.className = "mrow";
      row.innerHTML = `<div class="main"><div>${esc(o.name)} <span class="pill">${VS[o.verification_status]||o.verification_status}</span></div><div class="sub">${esc(o.org_type)}</div></div>`;
      if (o.verification_status !== "verified") {
        const b = document.createElement("button"); b.className = "mbtn ghost"; b.textContent = "인증 신청";
        b.onclick = async () => { try { await API.call(`/api/organizations/${o.id}/verify-request`, "POST"); toast("인증 신청 완료. 관리자 검수 대기", "ok"); } catch(e){ toast(e.message,"error"); } };
        row.appendChild(b);
      }
      box.appendChild(row);
    });
  } catch (e) { needLogin(e); }
}
async function loadCats() {
  try { const { categories } = await API.call("/api/discovery/categories");
    const s = $("chCat"); s.innerHTML = '<option value="">(선택)</option>';
    categories.forEach(c => { const o = document.createElement("option"); o.value = c; o.textContent = c; s.appendChild(o); }); } catch(_){}
}
async function loadChannels() {
  try {
    const { channels } = await API.call("/api/channels/mine");
    const box = $("chList"); box.innerHTML = channels.length ? "" : '<p class="muted">채널이 없습니다.</p>';
    channels.forEach(c => { const row = document.createElement("div"); row.className = "mrow";
      row.innerHTML = `<div class="main"><div>${esc(c.name)} <span class="pill">${esc(c.channel_type)}</span>${c.official_badge?' <span class="b-official">공식</span>':''}</div></div><a class="mbtn ghost" href="/channel/${c.id}">보기</a>`;
      box.appendChild(row); });
  } catch (e) { needLogin(e); }
}
async function loadArticles() {
  try {
    const { articles } = await API.call("/api/articles/mine");
    const box = $("artList"); box.innerHTML = articles.length ? "" : '<p class="muted">작성한 기사가 없습니다.</p>';
    articles.forEach(a => { const row = document.createElement("div"); row.className = "mrow";
      row.innerHTML = `<div class="main"><div>${esc(a.title)} <span class="pill">${esc(a.status)}</span></div><div class="sub">${esc(a.channel_name||'-')} · ${esc(a.created_at)}</div></div>`;
      if (a.status === "published") { const v = document.createElement("a"); v.className="mbtn ghost"; v.href=`/article/${a.id}`; v.textContent="보기"; row.appendChild(v); }
      else { const b = document.createElement("button"); b.className="mbtn"; b.textContent="발행";
        b.onclick = async () => { try { await API.call(`/api/articles/${a.id}/publish`, "POST"); toast("발행 완료", "ok"); loadArticles(); } catch(e){ toast(e.message,"error"); } }; row.appendChild(b); }
      box.appendChild(row); });
  } catch (e) { needLogin(e); }
}
$("orgForm").addEventListener("submit", async (e) => { e.preventDefault();
  try { await API.call("/api/organizations", "POST", {name:$("orgName").value.trim(), org_type:$("orgType").value, description:$("orgDesc").value.trim()});
    $("orgName").value=""; toast("조직 생성됨", "ok"); loadOrgs(); } catch(e){ needLogin(e)||toast(e.message,"error"); } });
$("chForm").addEventListener("submit", async (e) => { e.preventDefault();
  try { await API.call("/api/channels", "POST", {name:$("chName").value.trim(), channel_type:$("chType").value, organization_id:$("chOrg").value||null, media_category:$("chCat").value||null, description:$("chDesc").value.trim()});
    $("chName").value=""; toast("채널 생성됨", "ok"); loadChannels(); } catch(e){ needLogin(e)||toast(e.message,"error"); } });
document.addEventListener("DOMContentLoaded", () => { loadOrgs(); loadCats(); loadChannels(); loadArticles(); });
})();
