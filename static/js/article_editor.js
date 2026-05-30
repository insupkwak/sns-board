/* article_editor.js — 기사 작성/임시저장/발행 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);

async function loadOptions() {
  // 내 채널(뉴스/채널) 목록 = 내가 운영하는 방
  try {
    const { rooms } = await API.call("/api/rooms");
    const sel = $("artRoom");
    sel.innerHTML = '<option value="">(채널 없음 / 개인 초안)</option>';
    rooms.filter(r => r.room_type === "news_channel" || r.room_type === "channel")
      .forEach(r => { const o=document.createElement("option"); o.value=r.id; o.textContent=r.name; sel.appendChild(o); });
  } catch (_) {}
  try {
    const { categories } = await API.call("/api/discovery/categories");
    const sel = $("artCategory");
    sel.innerHTML = '<option value="">(선택)</option>';
    categories.forEach(c => { const o=document.createElement("option"); o.value=c.id; o.textContent=c.name; sel.appendChild(o); });
  } catch (_) {}
}

function payload(status) {
  return {
    room_id: $("artRoom").value || null,
    title: $("artTitle").value.trim(),
    subtitle: $("artSubtitle").value.trim(),
    summary: $("artSummary").value.trim(),
    body: $("artBody").value,
    category_id: $("artCategory").value || null,
    tags: $("artTags").value,
    source_url: $("artSource").value.trim(),
    is_breaking: $("artBreaking").checked,
    status,
  };
}

async function submit(status) {
  if (!$("artTitle").value.trim()) { msg("제목을 입력하세요.", false); return; }
  try {
    const { article } = await API.call("/api/articles", "POST", payload(status));
    if (status === "published") location.href = `/article/${article.id}`;
    else msg("임시저장되었습니다. (내 기사 목록에서 확인)", true);
  } catch (e) { msg(e.message, false); }
}
function msg(t, ok) { const m=$("artMsg"); m.textContent=t; m.className="form-msg "+(ok?"ok":"err"); }

$("articleForm").addEventListener("submit", (e) => { e.preventDefault(); submit("published"); });
$("saveDraft").addEventListener("click", () => submit("draft"));
document.addEventListener("DOMContentLoaded", loadOptions);
})();
