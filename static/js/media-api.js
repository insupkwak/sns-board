/* media-api.js — 미디어 페이지 공통 헬퍼 (게시판 밝은 테마) */
window.API = (() => {
  async function call(url, method = "GET", body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const res = await fetch(url, opt);
    let data = {}; try { data = await res.json(); } catch (_) {}
    if (!res.ok || data.ok === false || data.error) throw new Error(data.error || "오류가 발생했습니다.");
    return data;
  }
  return { call };
})();
window.esc = (v) => (v ?? "").toString()
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
window.toast = (msg, type="info") => {
  let t = document.getElementById("mtoast");
  if (!t) { t = document.createElement("div"); t.id = "mtoast"; t.className = "mtoast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.style.background = type === "error" ? "#c0392b" : type === "ok" ? "#1a7f37" : "#1a1d21";
  t.style.display = "block";
  clearTimeout(window.__mt); window.__mt = setTimeout(() => t.style.display = "none", 2600);
};
/* 로그인 안내 (게시판 메인에서 로그인) */
window.needLogin = (e) => { if ((e.message||"").includes("로그인")) { toast("로그인이 필요합니다. 게시판에서 로그인하세요.", "error"); setTimeout(()=>location.href="/", 1200); return true; } return false; };
