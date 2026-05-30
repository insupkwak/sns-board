/* profile.js — 프로필 조회/수정/이미지 업로드 */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);

async function api(url, method = "GET", body, isForm = false) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body;
    else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  }
  const res = await fetch(url, opt);
  let data = {}; try { data = await res.json(); } catch (_) {}
  if (!res.ok || data.ok === false) throw new Error(data.error || "오류가 발생했습니다.");
  return data;
}
function msg(text, ok) { const m = $("profileMsg"); m.textContent = text; m.className = "form-msg " + (ok ? "ok" : "err"); }

async function load() {
  const { user } = await api("/api/profile");
  $("profileUserId").value = user.user_id;
  $("profileUsername").value = user.username;
  $("profileStatus").value = user.status_message || "";
  const av = $("profileAvatar");
  if (user.profile_image) av.style.backgroundImage = `url('${user.profile_image}')`;
  else av.textContent = (user.username || "?").charAt(0).toUpperCase();
}

$("profileForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/profile", "POST", {
      username: $("profileUsername").value.trim(),
      status_message: $("profileStatus").value.trim(),
    });
    msg("저장되었습니다.", true);
  } catch (err) { msg(err.message, false); }
});

$("changeImageBtn").addEventListener("click", () => $("profileImageInput").click());
$("profileImageInput").addEventListener("change", async () => {
  const file = $("profileImageInput").files[0];
  if (!file) return;
  if (file.size > 3 * 1024 * 1024) { msg("이미지는 3MB 이하만 가능합니다.", false); return; }
  try {
    const fd = new FormData(); fd.append("file", file);
    const { profile_image } = await api("/api/profile/image", "POST", fd, true);
    $("profileAvatar").style.backgroundImage = `url('${profile_image}')`;
    $("profileAvatar").textContent = "";
    msg("이미지가 변경되었습니다.", true);
  } catch (err) { msg(err.message, false); }
});

document.addEventListener("DOMContentLoaded", load);
})();
