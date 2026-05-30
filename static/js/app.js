/* SNS 게시판 프론트엔드 */
(() => {
    "use strict";

    let me = null;
    let currentCategory = "";
    let offset = 0;
    const PAGE = 10;
    let loading = false;
    let reachedEnd = false;

    const $ = (sel) => document.querySelector(sel);
    const el = (tag, cls) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        return e;
    };

    // 글쓰기 칸: 기본 높이 유지하다가 내용이 넘치면 자동 확장
    function autoGrow(el) {
        el.style.height = "auto";
        const max = parseInt(getComputedStyle(el).maxHeight, 10) || Infinity;
        el.style.height = Math.min(el.scrollHeight, max) + "px";
        el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
    }
    function resetGrow(el) {
        el.style.height = "";        // CSS 의 고정 높이로 복귀
        el.style.overflowY = "hidden";
    }

    // ---------- API ----------
    async function api(url, method = "GET", body) {
        const opt = { method, headers: {} };
        if (body !== undefined) {
            opt.headers["Content-Type"] = "application/json";
            opt.body = JSON.stringify(body);
        }
        const res = await fetch(url, opt);
        let data = {};
        try { data = await res.json(); } catch (_) {}
        if (!res.ok) throw new Error(data.error || "오류가 발생했습니다.");
        return data;
    }

    // ---------- 시간 표시 ----------
    function timeText(s) {
        if (!s) return "";
        // 'YYYY-MM-DD HH:MM:SS' (localtime) → 보기 좋게
        return s.replace(/-/g, ".").slice(2, 16); // YY.MM.DD HH:MM
    }

    // ---------- 인증 UI ----------
    function renderAuth() {
        const area = $("#auth-area");
        area.innerHTML = "";
        if (me) {
            const nick = el("span", "nick");
            nick.textContent = me.nickname;
            const out = el("button");
            out.textContent = "로그아웃";
            out.onclick = async () => {
                await api("/api/logout", "POST");
                me = null;
                renderAuth();
                reload();
            };
            area.append(nick, out);
            $("#composer").hidden = false;
            $("#login-hint").hidden = true;
        } else {
            const login = el("button", "primary");
            login.textContent = "로그인";
            login.onclick = () => openModal("login");
            area.append(login);
            $("#composer").hidden = true;
            $("#login-hint").hidden = false;
        }
    }

    // ---------- 모달 ----------
    function openModal(tab) {
        $("#modal").hidden = false;
        switchTab(tab);
        $("#auth-error").textContent = "";
    }
    function closeModal() {
        $("#modal").hidden = true;
        $("#login-form").reset();
        $("#register-form").reset();
        $("#auth-error").textContent = "";
    }
    function switchTab(tab) {
        const isLogin = tab === "login";
        $("#tab-login").classList.toggle("active", isLogin);
        $("#tab-register").classList.toggle("active", !isLogin);
        $("#login-form").hidden = !isLogin;
        $("#register-form").hidden = isLogin;
        $("#auth-error").textContent = "";
    }

    // ---------- 게시글 렌더 ----------
    function postNode(p) {
        const node = el("article", "post");
        node.dataset.id = p.id;

        // 헤더
        const head = el("div", "post-head");
        const badge = el("span", "badge");
        badge.textContent = p.category;
        const nick = el("span", "nick");
        nick.textContent = p.nickname;
        const time = el("span");
        time.textContent = timeText(p.created_at);
        head.append(badge, nick, time);
        if (p.updated_at) {
            const ed = el("span", "edited");
            ed.textContent = "(수정됨)";
            head.append(ed);
        }

        // 본문 (제목 없이 본문만)
        const body = el("div", "post-body");
        body.textContent = p.content;

        // 액션
        const actions = el("div", "post-actions");
        const like = el("button", "act" + (p.liked ? " liked" : ""));
        like.innerHTML = `♥ 좋아요 <b class="like-n">${p.likes}</b>`;
        like.onclick = () => toggleLike(p, like);

        const cmt = el("button", "act");
        cmt.textContent = `댓글 ${p.comment_count}`;
        cmt.onclick = () => toggleComments(node, p, cmt);

        actions.append(like, cmt);

        if (p.mine) {
            const edit = el("button", "act");
            edit.textContent = "수정";
            edit.onclick = () => editPost(node, p, body);
            const del = el("button", "act del");
            del.textContent = "삭제";
            del.onclick = () => removePost(node, p);
            actions.append(edit, del);
        }

        node.append(head, body, actions);
        return node;
    }

    async function toggleLike(p, btn) {
        if (!me) return openModal("login");
        try {
            const r = await api(`/api/posts/${p.id}/like`, "POST");
            p.liked = r.liked;
            p.likes = r.likes;
            btn.classList.toggle("liked", r.liked);
            btn.querySelector(".like-n").textContent = r.likes;
        } catch (e) { alert(e.message); }
    }

    function editPost(node, p, bodyEl) {
        if (node.querySelector(".edit-box")) return;
        const box = el("div", "edit-box");
        const ta = el("textarea", "post-content-edit");
        ta.value = p.content;
        ta.addEventListener("input", () => autoGrow(ta));
        const acts = el("div", "edit-actions");
        const save = el("button", "save");
        save.textContent = "저장";
        const cancel = el("button");
        cancel.textContent = "취소";
        acts.append(cancel, save);
        box.append(ta, acts);
        bodyEl.replaceWith(box);
        autoGrow(ta);   // 기존 내용 줄 수에 맞춰 초기 높이 설정

        cancel.onclick = () => box.replaceWith(bodyEl);
        save.onclick = async () => {
            const content = ta.value.trim();
            if (!content) return;
            try {
                const r = await api(`/api/posts/${p.id}`, "PUT", { content });
                p.content = r.post.content;
                p.updated_at = r.post.updated_at;
                bodyEl.textContent = p.content;
                box.replaceWith(bodyEl);
                if (!node.querySelector(".edited")) {
                    const ed = el("span", "edited");
                    ed.textContent = "(수정됨)";
                    node.querySelector(".post-head").append(ed);
                }
            } catch (e) { alert(e.message); }
        };
    }

    async function removePost(node, p) {
        if (!confirm("이 게시글을 삭제할까요?")) return;
        try {
            await api(`/api/posts/${p.id}`, "DELETE");
            node.remove();
        } catch (e) { alert(e.message); }
    }

    // ---------- 댓글 ----------
    async function toggleComments(node, p, btn) {
        const existing = node.querySelector(".comments");
        if (existing) { existing.remove(); return; }

        const wrap = el("div", "comments");
        wrap.textContent = "불러오는 중…";
        node.append(wrap);
        try {
            const { comments } = await api(`/api/posts/${p.id}/comments`);
            wrap.textContent = "";
            comments.forEach((c) => wrap.append(commentNode(p, c, btn)));

            if (me) {
                const form = el("form", "comment-form");
                const input = el("input");
                input.placeholder = "댓글 달기";
                input.maxLength = 1000;
                const send = el("button");
                send.type = "submit";
                send.textContent = "등록";
                form.append(input, send);
                form.onsubmit = async (ev) => {
                    ev.preventDefault();
                    const content = input.value.trim();
                    if (!content) return;
                    try {
                        await api(`/api/posts/${p.id}/comments`, "POST", { content });
                        input.value = "";
                        const c = {
                            id: Date.now(), content, nickname: me.nickname,
                            user_id: me.id, created_at: null, updated_at: null, mine: true,
                        };
                        // 정확한 데이터를 위해 다시 로드
                        const fresh = await api(`/api/posts/${p.id}/comments`);
                        wrap.querySelectorAll(".comment").forEach((n) => n.remove());
                        fresh.comments.forEach((cc) =>
                            wrap.insertBefore(commentNode(p, cc, btn), form));
                        p.comment_count = fresh.comments.length;
                        btn.textContent = `댓글 ${p.comment_count}`;
                    } catch (e) { alert(e.message); }
                };
                wrap.append(form);
            }
        } catch (e) {
            wrap.textContent = e.message;
        }
    }

    function commentNode(p, c, btn) {
        const node = el("div", "comment");
        const main = el("div", "c-main");
        const meta = el("div", "c-meta");
        const nick = el("span", "nick");
        nick.textContent = c.nickname;
        const t = el("span");
        t.textContent = " · " + timeText(c.created_at) + (c.updated_at ? " (수정됨)" : "");
        meta.append(nick, t);
        const cbody = el("div", "c-body");
        cbody.textContent = c.content;
        main.append(meta, cbody);
        node.append(main);

        if (c.mine) {
            const tools = el("div", "c-tools");
            const ed = el("button");
            ed.textContent = "수정";
            ed.onclick = () => editComment(node, main, cbody, c);
            const del = el("button");
            del.textContent = "삭제";
            del.onclick = async () => {
                if (!confirm("댓글을 삭제할까요?")) return;
                try {
                    await api(`/api/comments/${c.id}`, "DELETE");
                    node.remove();
                    p.comment_count = Math.max(0, p.comment_count - 1);
                    btn.textContent = `댓글 ${p.comment_count}`;
                } catch (e) { alert(e.message); }
            };
            tools.append(ed, del);
            node.append(tools);
        }
        return node;
    }

    function editComment(node, main, cbody, c) {
        if (main.querySelector(".edit-box")) return;
        const box = el("div", "edit-box");
        const input = el("input");
        input.value = c.content;
        input.maxLength = 1000;
        const acts = el("div", "edit-actions");
        const save = el("button", "save");
        save.textContent = "저장";
        const cancel = el("button");
        cancel.textContent = "취소";
        acts.append(cancel, save);
        box.append(input, acts);
        cbody.replaceWith(box);

        cancel.onclick = () => box.replaceWith(cbody);
        save.onclick = async () => {
            const content = input.value.trim();
            if (!content) return;
            try {
                await api(`/api/comments/${c.id}`, "PUT", { content });
                c.content = content;
                cbody.textContent = content;
                box.replaceWith(cbody);
            } catch (e) { alert(e.message); }
        };
    }

    // ---------- 피드 로드 (무한스크롤) ----------
    async function loadMore() {
        if (loading || reachedEnd) return;
        loading = true;
        $("#loader").hidden = false;
        try {
            const q = new URLSearchParams({ offset, limit: PAGE });
            if (currentCategory) q.set("category", currentCategory);
            const { posts, has_more } = await api(`/api/posts?${q}`);
            const container = $("#posts");
            posts.forEach((p) => container.append(postNode(p)));
            offset += posts.length;
            if (!has_more) {
                reachedEnd = true;
                $("#end").hidden = false;
            }
        } catch (e) {
            console.error(e);
        } finally {
            loading = false;
            $("#loader").hidden = true;
        }
    }

    function reload() {
        offset = 0;
        reachedEnd = false;
        $("#posts").innerHTML = "";
        $("#end").hidden = true;
        loadMore();
    }

    // ---------- 이벤트 ----------
    function bind() {
        // [안전장치] 모든 폼의 네이티브 제출(페이지 새로고침/메인 이동) 원천 차단.
        // 캡처 단계라 개별 onsubmit 핸들러보다 먼저 실행되며, fetch 처리는 그대로 동작.
        document.addEventListener("submit", (e) => e.preventDefault(), true);

        // 카테고리 메뉴
        $("#category-nav").addEventListener("click", (e) => {
            const btn = e.target.closest(".cat");
            if (!btn) return;
            document.querySelectorAll(".cat").forEach((c) => c.classList.remove("active"));
            btn.classList.add("active");
            currentCategory = btn.dataset.category || "";
            reload();
        });

        // 글쓰기 칸 자동 높이 조절
        const postContent = $("#post-content");
        postContent.addEventListener("input", () => autoGrow(postContent));

        // 글쓰기
        $("#post-submit").onclick = async () => {
            const content = $("#post-content").value.trim();
            const category = $("#post-category").value;
            if (!content) return;
            try {
                const { post } = await api("/api/posts", "POST", { content, category });
                $("#post-content").value = "";
                resetGrow($("#post-content"));   // 게시 후 기본 높이로 복귀
                // 현재 카테고리 필터에 맞으면 최상단에 추가
                if (!currentCategory || currentCategory === post.category) {
                    const c = $("#posts");
                    c.insertBefore(postNode(post), c.firstChild);
                    offset += 1;
                }
            } catch (e) { alert(e.message); }
        };

        // 모달 탭/닫기
        $("#tab-login").onclick = () => switchTab("login");
        $("#tab-register").onclick = () => switchTab("register");
        $("#modal-close").onclick = closeModal;
        // 배경 클릭으로 닫기: 마우스 다운과 업이 '모두' 배경에서 일어난 경우만.
        // (폼 안에서 클릭하다 실수로 바깥에서 떼어도 창이 닫히지 않도록)
        let downOnBackdrop = false;
        $("#modal").addEventListener("mousedown", (e) => {
            downOnBackdrop = e.target.id === "modal";
        });
        $("#modal").addEventListener("click", (e) => {
            if (e.target.id === "modal" && downOnBackdrop) closeModal();
        });

        // 로그인
        $("#login-form").onsubmit = async (e) => {
            e.preventDefault();
            const f = e.target;
            try {
                const { user } = await api("/api/login", "POST", {
                    email: f.email.value, password: f.password.value,
                });
                me = user;
                closeModal();
                renderAuth();
                reload();
            } catch (err) { $("#auth-error").textContent = err.message; }
        };

        // 회원가입
        $("#register-form").onsubmit = async (e) => {
            e.preventDefault();
            const f = e.target;
            try {
                const { user } = await api("/api/register", "POST", {
                    email: f.email.value,
                    nickname: f.nickname.value,
                    password: f.password.value,
                    password2: f.password2.value,
                });
                me = user;
                closeModal();
                renderAuth();
                reload();
            } catch (err) { $("#auth-error").textContent = err.message; }
        };

        // 무한스크롤
        window.addEventListener("scroll", () => {
            if (window.innerHeight + window.scrollY >=
                document.body.offsetHeight - 400) {
                loadMore();
            }
        });
    }

    // ---------- 시작 ----------
    async function init() {
        bind();
        try {
            const data = await api("/api/me");
            me = data.user;
        } catch (_) {}
        renderAuth();
        reload();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
