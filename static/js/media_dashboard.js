/* media_dashboard.js — 조직/채널/기사 운영 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const VS = {pending:"검수중", verified:"인증완료", rejected:"반려", suspended:"정지"};

async function loadOrgs() {
  try {
    const { organizations } = await API.call("/api/organizations/mine");
    const sel = $("chOrg"); sel.innerHTML = '<option value="">(없음)</option>';
    const box = $("orgList"); box.innerHTML = "";
    organizations.forEach(o => {
      const opt=document.createElement("option"); opt.value=o.id; opt.textContent=o.name; sel.appendChild(opt);
      const row=document.createElement("div"); row.className="admin-row";
      row.innerHTML=`<div class="ar-main"><div>${esc(o.name)} <span class="pill">${VS[o.verification_status]||o.verification_status}</span></div>
        <div class="ar-sub">${esc(o.org_type)}</div></div>`;
      if (o.verification_status !== "verified") {
        const b=document.createElement("button"); b.className="btn-ghost"; b.textContent="인증 신청";
        b.addEventListener("click", async ()=>{ try{ await API.call(`/api/organizations/${o.id}/verify-request`,"POST"); toast("인증 신청 완료. 관리자 검수 대기","success"); }catch(e){toast(e.message,"error");} });
        row.appendChild(b);
      }
      box.appendChild(row);
    });
  } catch (_) {}
}

async function loadCats() {
  try { const { categories } = await API.call("/api/discovery/categories");
    const sel=$("chCat"); sel.innerHTML='<option value="">(선택)</option>';
    categories.forEach(c=>{const o=document.createElement("option");o.value=c.id;o.textContent=c.name;sel.appendChild(o);});
  } catch (_) {}
}

async function loadChannels() {
  try {
    const { rooms } = await API.call("/api/rooms");
    const box=$("chList"); box.innerHTML="";
    const ch = rooms.filter(r=>["channel","news_channel","discussion"].includes(r.room_type));
    if (!ch.length) { box.innerHTML='<p class="muted">채널이 없습니다.</p>'; return; }
    ch.forEach(r=>{ const row=document.createElement("div"); row.className="admin-row";
      row.innerHTML=`<div class="ar-main"><div>${esc(r.name)} <span class="pill">${esc(r.room_type)}</span></div></div>
        <a class="btn-ghost" href="/channel/${r.id}">보기</a>`;
      box.appendChild(row); });
  } catch (_) {}
}

async function loadArticles() {
  try {
    const { articles } = await API.call("/api/articles/mine");
    const box=$("artList"); box.innerHTML="";
    if (!articles.length) { box.innerHTML='<p class="muted">작성한 기사가 없습니다.</p>'; return; }
    articles.forEach(a=>{ const row=document.createElement("div"); row.className="admin-row";
      row.innerHTML=`<div class="ar-main"><div>${esc(a.title)} <span class="pill">${esc(a.status)}</span></div>
        <div class="ar-sub">${esc(a.room_name||'-')} · ${esc(a.created_at)}</div></div>
        ${a.status==='published'?`<a class="btn-ghost" href="/article/${a.id}">보기</a>`:
          `<button class="btn-primary sm" data-id="${a.id}">발행</button>`}`;
      const pub=row.querySelector("button");
      if (pub) pub.addEventListener("click", async ()=>{ try{ await API.call(`/api/articles/${a.id}/publish`,"POST"); toast("발행 완료","success"); loadArticles(); }catch(e){toast(e.message,"error");} });
      box.appendChild(row); });
  } catch (_) {}
}

$("orgForm").addEventListener("submit", async (e)=>{ e.preventDefault();
  try { await API.call("/api/organizations","POST",{name:$("orgName").value.trim(),
    org_type:$("orgType").value, description:$("orgDesc").value.trim()});
    $("orgName").value=""; toast("조직을 만들었습니다.","success"); loadOrgs(); }
  catch(e){ toast(e.message,"error"); }
});

$("chForm").addEventListener("submit", async (e)=>{ e.preventDefault();
  try { await API.call("/api/channels","POST",{name:$("chName").value.trim(),
    room_type:$("chType").value, organization_id:$("chOrg").value||null,
    category_id:$("chCat").value||null, description:$("chDesc").value.trim()});
    $("chName").value=""; toast("채널을 만들었습니다.","success"); loadChannels(); }
  catch(e){ toast(e.message,"error"); }
});

document.addEventListener("DOMContentLoaded", ()=>{ loadOrgs(); loadCats(); loadChannels(); loadArticles(); });
})();
