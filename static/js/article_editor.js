/* article_editor.js */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
function msg(t, ok) { const m = $("msg"); m.textContent = t; m.className = "mmsg " + (ok ? "ok" : "err"); }

async function load() {
  try {
    const { channels } = await API.call("/api/channels/mine");
    const s = $("channel"); s.innerHTML = '<option value="">(채널 없음 / 개인 초안)</option>';
    channels.forEach(c => { const o = document.createElement("option"); o.value = c.id; o.textContent = c.name; s.appendChild(o); });
  } catch (e) { if (needLogin(e)) return; }
  try {
    const { categories } = await API.call("/api/discovery/categories");
    const s = $("category"); s.innerHTML = '<option value="">(선택)</option>';
    categories.forEach(c => { const o = document.createElement("option"); o.value = c; o.textContent = c; s.appendChild(o); });
  } catch (_) {}
}
function payload(status) {
  return { channel_id: $("channel").value || null, title: $("title").value.trim(),
    subtitle: $("subtitle").value.trim(), summary: $("summary").value.trim(), body: $("body").value,
    media_category: $("category").value || null, tags: $("tags").value, source_url: $("source").value.trim(),
    is_breaking: $("breaking").checked, status };
}
async function submit(status) {
  if (!$("title").value.trim()) { msg("제목을 입력하세요.", false); return; }
  try {
    const { article } = await API.call("/api/articles", "POST", payload(status));
    if (status === "published") location.href = `/article/${article.id}`;
    else msg("임시저장되었습니다. (미디어 대시보드에서 발행 가능)", true);
  } catch (e) { if (!needLogin(e)) msg(e.message, false); }
}
$("form").addEventListener("submit", (e) => { e.preventDefault(); submit("published"); });
$("draft").addEventListener("click", () => submit("draft"));
document.addEventListener("DOMContentLoaded", load);
})();
