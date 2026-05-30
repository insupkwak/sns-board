/* api.js — 공통 fetch/escape/toast 헬퍼 (미디어 페이지 공용) */
window.API = (() => {
  async function call(url, method = "GET", body, isForm = false) {
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
  return { call };
})();
window.esc = (v) => (v ?? "").toString()
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
window.toast = (msg, type="info") => {
  const t = document.getElementById("toast"); if (!t) { alert(msg); return; }
  t.textContent = msg; t.className = "toast " + (type==="error"?"err":type==="success"?"ok":"");
  t.hidden = false; clearTimeout(window.__tt); window.__tt = setTimeout(()=>t.hidden=true, 2600);
};
