/* SNS Board — 5차 SPA 프론트엔드 (다크 프리미엄)
   기존 API 유지: /api/register /api/login /api/logout /api/me
   /api/posts(GET/POST) /api/posts/<id>(PUT/DELETE) /api/posts/<id>/like
   /api/posts/<id>/comments(GET/POST) /api/comments/<id>(PUT/DELETE) */
(() => {
"use strict";

const state = {
  currentUser: null, currentView: "home", currentCategory: "all",
  searchQuery: "", offset: 0, limit: 10, loading: false, hasMore: true,
};

const $ = (id) => document.getElementById(id);
const demoBoards = [
  { name: "AI 실무 활용방", desc: "업무 자동화와 AI 코딩 활용법을 나누는 공간입니다.", tags: ["AI","업무자동화","개발"], members: 1240, posts: 382 },
  { name: "여행 정보 공유방", desc: "가족 여행, 해외 여행, 특별한 여행지를 공유합니다.", tags: ["여행","맛집","가족"], members: 860, posts: 241 },
  { name: "회사생활 이야기", desc: "직장인의 고민과 노하우를 자유롭게 나눕니다.", tags: ["회사생활","커리어","일상"], members: 740, posts: 198 },
  { name: "유머 게시판", desc: "가볍게 웃고 쉬어가는 공간입니다.", tags: ["유머","일상","재미"], members: 1520, posts: 640 },
];
function getTrendData() {
  return [
    { keyword: "AI 코딩", posts: 328, comments: 1204 },
    { keyword: "여행 추천", posts: 220, comments: 740 },
    { keyword: "회사생활", posts: 180, comments: 620 },
    { keyword: "투자", posts: 142, comments: 510 },
    { keyword: "유머", posts: 390, comments: 980 },
  ];
}

/* ---------- utils ---------- */
function escapeHtml(v){ return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
function numberFormat(v){ return Number(v || 0).toLocaleString("ko-KR"); }
function formatDate(v){
  if(!v) return "";
  const d = new Date(String(v).replace(" ","T"));
  if(Number.isNaN(d.getTime())) return String(v).slice(5,16);
  return d.toLocaleString("ko-KR",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});
}
async function api(url, method="GET", body){
  const opt = { method, headers:{} };
  if(body !== undefined){ opt.headers["Content-Type"]="application/json"; opt.body=JSON.stringify(body); }
  const res = await fetch(url, opt);
  let data = {}; try{ data = await res.json(); }catch(_){}
  if(!res.ok) throw new Error(data.error || "오류가 발생했습니다.");
  return data;
}

/* ---------- 사용자/인증 ---------- */
async function loadMe(){
  try{ const d = await api("/api/me"); state.currentUser = d.user; }
  catch(_){ state.currentUser = null; }
  renderAuth();
  // 관리자 메뉴
  if(state.currentUser && state.currentUser.is_admin) $("adminLink").hidden = false;
}
function renderAuth(){
  const area = $("authArea"); area.innerHTML = "";
  const mob = $("mobileAuthBtn");
  if(state.currentUser){
    const nick = document.createElement("span"); nick.className="nick"; nick.textContent = state.currentUser.nickname;
    const out = document.createElement("button"); out.textContent="로그아웃";
    out.onclick = async () => { await api("/api/logout","POST"); state.currentUser=null; renderAuth();
      if(state.currentView==="home") resetAndLoadPosts(); else setView(state.currentView); };
    area.append(nick, out);
    $("composer").hidden = false; $("loginHint").hidden = true;
    mob.textContent = "로그아웃"; mob.onclick = out.onclick;
  } else {
    const login = document.createElement("button"); login.className="primary"; login.textContent="로그인";
    login.onclick = () => openAuthModal();
    area.append(login);
    $("composer").hidden = true; $("loginHint").hidden = false;
    mob.textContent = "로그인"; mob.onclick = () => openAuthModal();
  }
}
function openAuthModal(tab="login"){ $("authModal").hidden=false; switchAuthTab(tab); $("authError").textContent=""; }
function closeAuthModal(){ $("authModal").hidden=true; $("loginForm").reset(); $("registerForm").reset(); $("authError").textContent=""; }
function switchAuthTab(tab){
  const isLogin = tab==="login";
  $("tabLogin").classList.toggle("active", isLogin);
  $("tabRegister").classList.toggle("active", !isLogin);
  $("loginForm").hidden = !isLogin; $("registerForm").hidden = isLogin;
  $("authError").textContent="";
}

/* ---------- 뷰 전환 ---------- */
function setView(view){
  state.currentView = view;
  document.querySelectorAll("[data-view]").forEach((el)=> el.classList.toggle("active", el.dataset.view===view));
  updateViewHeader(view);
  renderCurrentView();
  window.scrollTo({top:0});
}
function updateViewHeader(view){
  const data = {
    home:["홈","관심 있는 이야기와 최신 글을 확인하세요."],
    explore:["탐색","게시판, 주제, 관심사를 쉽게 찾아보세요."],
    trends:["트렌드","지금 사람들이 많이 이야기하는 주제입니다."],
    boards:["게시판","추천 게시판과 인기 게시판을 둘러보세요."],
    notifications:["알림","댓글, 좋아요, 팔로우 소식을 확인하세요."],
    profile:["내 정보","내 활동과 관심사를 관리하세요."],
  };
  const s = data[view] || data.home;
  $("viewTitle").textContent = s[0]; $("viewSubtitle").textContent = s[1];
}
function renderCurrentView(){
  const c = $("viewContainer");
  // 칩/글쓰기는 home 에서만 의미 → home 외에는 칩 숨김
  $("interestChips").hidden = state.currentView !== "home";
  if(state.currentView==="home"){
    c.innerHTML = '<div id="postList" class="post-list"></div><div id="feedLoader" class="feed-loader" hidden>불러오는 중…</div><div id="emptyState" class="empty-state" hidden></div>';
    resetAndLoadPosts(); return;
  }
  if(state.currentView==="explore"){ renderExploreView(c); return; }
  if(state.currentView==="trends"){ renderTrendsView(c); return; }
  if(state.currentView==="boards"){ renderBoardsView(c); return; }
  if(state.currentView==="notifications"){ renderNotificationsView(c); return; }
  if(state.currentView==="profile"){ renderProfileView(c); return; }
}

/* ---------- 게시글 ---------- */
function resetAndLoadPosts(){
  state.offset = 0; state.hasMore = true;
  const list = $("postList"); if(list) showSkeleton();
  loadPosts();
}
function showSkeleton(){
  const postList = $("postList"); if(!postList) return;
  postList.innerHTML = Array.from({length:4}).map(()=>`
    <article class="skeleton-card">
      <div class="skeleton skeleton-line short"></div>
      <div class="skeleton skeleton-line long"></div>
      <div class="skeleton skeleton-line mid"></div>
      <div class="skeleton skeleton-line long"></div>
    </article>`).join("");
}
async function loadPosts(){
  if(state.loading || !state.hasMore) return;
  state.loading = true;
  const loader = $("feedLoader"); if(loader && state.offset>0) loader.hidden = false;
  try{
    const params = new URLSearchParams();
    params.set("offset", state.offset); params.set("limit", state.limit);
    if(state.currentCategory && state.currentCategory!=="all") params.set("category", state.currentCategory);
    if(state.searchQuery) params.set("search", state.searchQuery);
    const data = await api(`/api/posts?${params.toString()}`);
    const posts = Array.isArray(data.posts) ? data.posts : (data || []);
    const firstLoad = state.offset === 0;
    if(firstLoad){ const pl=$("postList"); if(pl) pl.innerHTML=""; }
    if(firstLoad && posts.length===0){
      const pl=$("postList"); if(pl) pl.innerHTML="";
      renderEmptyState(state.searchQuery ? "검색 결과가 없습니다." : "아직 글이 없습니다.",
                       state.searchQuery ? "다른 키워드로 다시 검색해보세요." : "첫 번째 이야기를 남겨보세요.");
    } else {
      const es=$("emptyState"); if(es) es.hidden = true;
      appendPosts(posts);
    }
    state.offset += posts.length;
    state.hasMore = (typeof data.has_more === "boolean") ? data.has_more : (posts.length >= state.limit);
  }catch(e){ console.error(e); }
  finally{ state.loading=false; const l=$("feedLoader"); if(l) l.hidden=true; }
}
function appendPosts(posts){
  const postList = $("postList"); if(!postList) return;
  const html = posts.map((post,index)=>{
    const ph = renderPost(post);
    if(index===2 && state.offset===0) return ph + renderFeedRecommendCard();
    return ph;
  }).join("");
  postList.insertAdjacentHTML("beforeend", html);
}
function renderFeedRecommendCard(){
  const b = demoBoards[0];
  return `<article class="trend-card"><div class="trend-keyword">추천 게시판</div>
    <div class="trend-summary">${escapeHtml(b.name)}에서 새로운 이야기를 만나보세요.</div>
    <div class="trend-actions"><button class="btn btn-primary" data-nav="explore">방문하기</button>
    <button class="btn btn-secondary" data-nav="explore">팔로우</button></div></article>`;
}
function renderPost(post){
  const isMine = post.mine || (state.currentUser && state.currentUser.id === post.user_id);
  return `
  <article class="post-card" data-post-id="${post.id}">
    <div class="post-meta">
      <div class="avatar"></div>
      <div class="post-author-wrap">
        <div><span class="author-name">${escapeHtml(post.nickname || "사용자")}</span>
          <span class="post-category">${escapeHtml(post.category || "자유")}</span></div>
        <div class="post-time">${formatDate(post.created_at)}${post.updated_at ? " · 수정됨" : ""}</div>
      </div>
    </div>
    <div class="post-content">${escapeHtml(post.content)}</div>
    <div class="post-actions">
      <button class="action-btn ${post.liked ? "liked":""}" data-action="like">♥ <span>${numberFormat(post.likes)}</span></button>
      <button class="action-btn" data-action="comments">💬 <span>${numberFormat(post.comment_count)}</span></button>
      <button class="action-btn share" data-action="share">↗ 공유</button>
    </div>
    ${isMine ? `<div class="post-owner-actions">
      <button class="btn btn-secondary" data-action="edit">수정</button>
      <button class="btn btn-danger" data-action="delete">삭제</button></div>` : ""}
    <div class="comments-panel" hidden></div>
  </article>`;
}
function renderEmptyState(title, desc){
  const empty = $("emptyState"); if(!empty) return;
  empty.hidden = false;
  empty.innerHTML = `<div class="empty-title">${escapeHtml(title)}</div><div class="empty-desc">${escapeHtml(desc)}</div>`;
}
function renderInlineEmpty(title, desc){
  return `<section class="empty-state"><div class="empty-title">${escapeHtml(title)}</div><div class="empty-desc">${escapeHtml(desc)}</div></section>`;
}

/* ---------- 게시글 액션 (위임) ---------- */
async function onPostAction(card, action){
  const id = card.dataset.postId;
  if(action==="like"){
    if(!state.currentUser) return openAuthModal();
    try{ const r = await api(`/api/posts/${id}/like`,"POST");
      const btn = card.querySelector('[data-action="like"]');
      btn.classList.toggle("liked", r.liked); btn.querySelector("span").textContent = numberFormat(r.likes);
    }catch(e){ alert(e.message); }
  } else if(action==="comments"){ toggleComments(card, id); }
  else if(action==="share"){ try{ await navigator.clipboard.writeText(location.origin + "/#post-"+id); }catch(_){} toast("링크를 복사했습니다."); }
  else if(action==="edit"){ editPost(card, id); }
  else if(action==="delete"){
    if(!confirm("이 글을 삭제할까요?")) return;
    try{ await api(`/api/posts/${id}`,"DELETE"); card.remove(); }catch(e){ alert(e.message); }
  }
}
function editPost(card, id){
  const body = card.querySelector(".post-content");
  if(card.querySelector(".edit-box")) return;
  const box = document.createElement("div"); box.className="edit-box";
  const ta = document.createElement("textarea"); ta.className="post-content-edit"; ta.value = body.textContent;
  const acts = document.createElement("div"); acts.className="edit-actions";
  const cancel = document.createElement("button"); cancel.textContent="취소";
  const save = document.createElement("button"); save.className="save"; save.textContent="저장";
  acts.append(cancel, save); box.append(ta, acts); body.replaceWith(box);
  ta.style.height="auto"; ta.style.height=ta.scrollHeight+"px"; ta.focus();
  cancel.onclick = () => box.replaceWith(body);
  save.onclick = async () => {
    const content = ta.value.trim(); if(!content) return;
    try{ const r = await api(`/api/posts/${id}`,"PUT",{content});
      body.textContent = r.post ? r.post.content : content; box.replaceWith(body);
    }catch(e){ alert(e.message); }
  };
}
async function toggleComments(card, id){
  const panel = card.querySelector(".comments-panel");
  if(!panel.hidden){ panel.hidden = true; panel.innerHTML=""; return; }
  panel.hidden = false; panel.innerHTML = '<div class="feed-loader">불러오는 중…</div>';
  try{
    const { comments } = await api(`/api/posts/${id}/comments`);
    panel.innerHTML = comments.map(commentHtml).join("");
    if(state.currentUser){
      const form = document.createElement("form"); form.className="comment-form";
      form.innerHTML = '<input type="text" placeholder="댓글 달기" maxlength="1000"><button type="submit" class="btn btn-primary">등록</button>';
      form.onsubmit = async (e) => { e.preventDefault();
        const input = form.querySelector("input"); const content = input.value.trim(); if(!content) return;
        try{ await api(`/api/posts/${id}/comments`,"POST",{content});
          await refreshComments(card, id);
          const btn = card.querySelector('[data-action="comments"] span');
          if(btn) btn.textContent = numberFormat((parseInt(btn.textContent.replace(/,/g,""))||0)+1);
        }catch(err){ alert(err.message); }
      };
      panel.appendChild(form);
    }
    bindCommentTools(card, id, panel);
  }catch(e){ panel.innerHTML = `<div class="feed-loader">${escapeHtml(e.message)}</div>`; }
}
async function refreshComments(card, id){
  const panel = card.querySelector(".comments-panel");
  const { comments } = await api(`/api/posts/${id}/comments`);
  panel.querySelectorAll(".comment-card").forEach(n=>n.remove());
  const form = panel.querySelector(".comment-form");
  comments.forEach(c => { const div = document.createElement("div"); div.innerHTML = commentHtml(c);
    panel.insertBefore(div.firstElementChild, form || null); });
  if(form) form.querySelector("input").value = "";
  bindCommentTools(card, id, panel);
}
function commentHtml(c){
  return `<div class="comment-card" data-comment-id="${c.id}">
    <div class="comment-author">${escapeHtml(c.nickname)} <span class="post-time">${formatDate(c.created_at)}${c.updated_at?" · 수정됨":""}</span></div>
    <div class="comment-content">${escapeHtml(c.content)}</div>
    ${c.mine ? '<div class="comment-tools"><button data-c="edit">수정</button><button data-c="delete">삭제</button></div>' : ''}
  </div>`;
}
function bindCommentTools(card, postId, panel){
  panel.querySelectorAll(".comment-card").forEach(cc=>{
    const cid = cc.dataset.commentId;
    const edit = cc.querySelector('[data-c="edit"]'); const del = cc.querySelector('[data-c="delete"]');
    if(edit) edit.onclick = () => {
      const body = cc.querySelector(".comment-content");
      if(cc.querySelector(".edit-box")) return;
      const box = document.createElement("div"); box.className="edit-box";
      const input = document.createElement("input"); input.value = body.textContent; input.maxLength=1000;
      const acts = document.createElement("div"); acts.className="edit-actions";
      const cancel = document.createElement("button"); cancel.textContent="취소";
      const save = document.createElement("button"); save.className="save"; save.textContent="저장";
      acts.append(cancel,save); box.append(input,acts); body.replaceWith(box); input.focus();
      cancel.onclick = () => box.replaceWith(body);
      save.onclick = async () => { const content=input.value.trim(); if(!content) return;
        try{ await api(`/api/comments/${cid}`,"PUT",{content}); body.textContent=content; box.replaceWith(body); }catch(e){ alert(e.message); } };
    };
    if(del) del.onclick = async () => {
      if(!confirm("댓글을 삭제할까요?")) return;
      try{ await api(`/api/comments/${cid}`,"DELETE"); cc.remove();
        const btn = card.querySelector('[data-action="comments"] span');
        if(btn) btn.textContent = numberFormat(Math.max(0,(parseInt(btn.textContent.replace(/,/g,""))||1)-1));
      }catch(e){ alert(e.message); }
    };
  });
}

/* ---------- 탐색/트렌드/게시판/알림/프로필 ---------- */
function renderBoardCard(board){
  return `<article class="board-card"><div class="board-cover"></div><div class="board-body">
    <h3 class="board-title">${escapeHtml(board.name)}</h3>
    <p class="board-desc">${escapeHtml(board.desc)}</p>
    <div class="chip-row">${board.tags.map(t=>`<span class="chip">#${escapeHtml(t)}</span>`).join("")}</div>
    <div class="board-stats"><span>멤버 ${numberFormat(board.members)}명</span><span>글 ${numberFormat(board.posts)}개</span></div>
    <div class="board-actions"><button class="btn btn-primary">방문하기</button><button class="btn btn-secondary">팔로우</button></div>
  </div></article>`;
}
function renderExploreView(container){
  container.innerHTML = `<section class="explore-grid">
    <div class="search-box"><span class="search-icon">⌕</span><input id="exploreSearchInput" type="search" placeholder="찾고 싶은 주제나 게시판을 입력하세요"></div>
    <div class="section-title-row"><h2 class="section-title">추천 관심사</h2></div>
    <div class="chip-row">${["AI","여행","투자","유머","회사생활","개발","선박","육아"].map(t=>`<button class="chip">#${t}</button>`).join("")}</div>
    <div class="section-title-row"><h2 class="section-title">지금 인기 있는 게시판</h2></div>
    <div class="card-grid">${demoBoards.map(renderBoardCard).join("")}</div>
  </section>`;
  const input = $("exploreSearchInput");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    const filtered = demoBoards.filter(b => b.name.toLowerCase().includes(q) || b.desc.toLowerCase().includes(q) || b.tags.some(t=>t.toLowerCase().includes(q)));
    const grid = container.querySelector(".card-grid");
    grid.innerHTML = filtered.length ? filtered.map(renderBoardCard).join("") : renderInlineEmpty("검색 결과가 없습니다.","다른 관심사를 검색해보세요.");
  });
}
function renderTrendsView(container){
  container.innerHTML = `<section class="explore-grid">${getTrendData().map(item=>`
    <article class="trend-card"><div class="trend-keyword">#${escapeHtml(item.keyword)}</div>
      <div class="trend-summary">오늘 글 ${numberFormat(item.posts)}개, 댓글 ${numberFormat(item.comments)}개</div>
      <div class="trend-actions"><button class="btn btn-primary" data-nav="home">관련 글 보기</button><button class="btn btn-secondary">주제방 입장</button></div>
    </article>`).join("")}</section>`;
}
function renderBoardsView(container){
  container.innerHTML = `<section class="explore-grid"><div class="section-title-row"><h2 class="section-title">추천 게시판</h2></div>
    <div class="card-grid">${demoBoards.map(renderBoardCard).join("")}</div></section>`;
}
function renderNotificationsView(container){
  container.innerHTML = renderInlineEmpty("아직 알림이 없습니다.","댓글, 좋아요, 팔로우 알림이 여기에 표시됩니다.");
}
function renderProfileView(container){
  if(!state.currentUser){
    container.innerHTML = `<section class="empty-state"><div class="empty-title">로그인이 필요합니다.</div>
      <div class="empty-desc">내 정보와 활동 기록을 보려면 로그인해주세요.</div>
      <button class="btn btn-primary" id="profileLoginBtn">로그인</button></section>`;
    $("profileLoginBtn").addEventListener("click", ()=>openAuthModal());
    return;
  }
  container.innerHTML = `<section class="post-card"><div class="post-meta"><div class="avatar"></div>
    <div><div class="author-name">${escapeHtml(state.currentUser.nickname || "사용자")}</div>
    <div class="post-time">${escapeHtml(state.currentUser.email || "")}</div></div></div>
    <div class="post-content">내가 쓴 글과 댓글, 팔로우한 게시판이 이곳에 표시됩니다.</div></section>`;
}
function renderRightPanel(){
  const trendList = $("trendList"), rec = $("recommendedBoards"), tags = $("popularTags");
  if(trendList) trendList.innerHTML = getTrendData().map((item,i)=>`
    <div class="trend-item"><div class="trend-rank">${i+1}위</div><div class="trend-title">#${escapeHtml(item.keyword)}</div>
      <div class="trend-meta">글 ${numberFormat(item.posts)}개, 댓글 ${numberFormat(item.comments)}개</div></div>`).join("");
  if(rec) rec.innerHTML = demoBoards.slice(0,3).map(b=>`
    <div class="trend-item"><div class="trend-title">${escapeHtml(b.name)}</div><div class="trend-meta">${escapeHtml(b.desc)}</div></div>`).join("");
  if(tags) tags.innerHTML = ["AI","여행","투자","유머","회사생활","개발"].map(t=>`<button class="chip">#${t}</button>`).join("");
}

/* ---------- toast ---------- */
let toastTimer=null;
function toast(msg){
  let t=$("toast"); if(!t){ t=document.createElement("div"); t.id="toast"; t.className="mtoast"; document.body.appendChild(t); }
  t.textContent=msg; t.style.display="block"; clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.style.display="none",2200);
}

/* ---------- 글쓰기 ---------- */
async function submitPost(){
  if(!state.currentUser) return openAuthModal();
  const ta = $("postContent"); const content = ta.value.trim(); if(!content) return;
  const category = (state.currentCategory && state.currentCategory!=="all") ? state.currentCategory : "자유";
  try{
    await api("/api/posts","POST",{content, category});
    ta.value=""; ta.style.height="";
    if(state.currentView!=="home") setView("home"); else resetAndLoadPosts();
  }catch(e){ alert(e.message); }
}
function focusComposer(){
  if(state.currentView!=="home") setView("home");
  if(!state.currentUser) return openAuthModal();
  window.scrollTo({top:0,behavior:"smooth"});
  const ta = $("postContent"); if(ta) ta.focus();
}

/* ---------- setup ---------- */
function setupSearch(){
  let timer=null;
  [$("mobileSearchInput"), $("rightSearchInput")].filter(Boolean).forEach((input)=>{
    input.addEventListener("input", ()=>{
      clearTimeout(timer); const v=input.value.trim();
      timer=setTimeout(()=>{ state.searchQuery=v; if(state.currentView!=="home"){ setView("home"); } else { resetAndLoadPosts(); } }, 300);
    });
  });
}
function setupTextareaAutoResize(){
  document.addEventListener("input",(e)=>{ const t=e.target.closest("textarea"); if(!t) return;
    t.style.height="auto"; t.style.height=Math.min(t.scrollHeight,300)+"px"; });
}
function setupInfiniteScroll(){
  window.addEventListener("scroll", ()=>{
    if(state.currentView!=="home" || state.loading || !state.hasMore) return;
    if(window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) loadPosts();
  });
}
function bind(){
  // 폼 네이티브 제출 차단(안전장치)
  document.addEventListener("submit",(e)=>{ if(e.target.closest("#loginForm,#registerForm")) e.preventDefault(); }, true);

  // 글쓰기 버튼
  $("submitPostBtn").addEventListener("click", submitPost);
  $("leftWriteBtn").addEventListener("click", focusComposer);

  // 카테고리 칩 + 뷰 전환 + 작성 (위임)
  document.addEventListener("click",(e)=>{
    const chip = e.target.closest("[data-category]");
    if(chip){ document.querySelectorAll("[data-category]").forEach(el=>el.classList.toggle("active", el===chip));
      state.currentCategory = chip.dataset.category; if(state.currentView!=="home") setView("home"); else resetAndLoadPosts(); return; }
    const writeBtn = e.target.closest('[data-action="write"]');
    if(writeBtn){ e.preventDefault(); focusComposer(); return; }
    const viewBtn = e.target.closest("[data-view]");
    if(viewBtn){ e.preventDefault(); setView(viewBtn.dataset.view); return; }
    const navBtn = e.target.closest("[data-nav]");
    if(navBtn){ e.preventDefault(); setView(navBtn.dataset.nav); return; }
    // 게시글 액션
    const actBtn = e.target.closest(".post-card [data-action]");
    if(actBtn){ const card = actBtn.closest(".post-card"); onPostAction(card, actBtn.dataset.action); return; }
  });

  // 모달
  $("tabLogin").onclick = ()=>switchAuthTab("login");
  $("tabRegister").onclick = ()=>switchAuthTab("register");
  $("authClose").onclick = closeAuthModal;
  $("authModal").addEventListener("click",(e)=>{ if(e.target.id==="authModal") closeAuthModal(); });
  $("loginForm").addEventListener("submit", async (e)=>{ e.preventDefault(); const f=e.target;
    try{ await api("/api/login","POST",{email:f.email.value, password:f.password.value});
      closeAuthModal(); await loadMe(); resetAndLoadPosts(); }
    catch(err){ $("authError").textContent=err.message; } });
  $("registerForm").addEventListener("submit", async (e)=>{ e.preventDefault(); const f=e.target;
    try{ await api("/api/register","POST",{nickname:f.nickname.value, email:f.email.value, password:f.password.value, password2:f.password2.value});
      closeAuthModal(); await loadMe(); resetAndLoadPosts(); }
    catch(err){ $("authError").textContent=err.message; } });
}

document.addEventListener("DOMContentLoaded", async ()=>{
  bind(); setupSearch(); setupTextareaAutoResize(); setupInfiniteScroll();
  await loadMe();
  renderRightPanel();
  setView("home");
});
})();
