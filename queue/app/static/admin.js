// 관리자 화면
(() => {
  const $ = (id) => document.getElementById(id);
  const STATUS_TEXT = {
    waiting: "대기중",
    called: "호출됨",
    done: "완료",
    cancelled: "손님 취소",
    no_show: "노쇼",
  };
  // 서버 시각은 KST 기준(시간대 표기 없음)
  const kst = (iso) => (iso ? new Date(iso + "+09:00") : null);
  const hhmm = (d) => d ? d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Seoul" }) : "-";

  let state = null;
  let clockOffset = 0; // 서버 시각 - 기기 시각
  let loading = false, pending = false;

  async function api(path, opts = {}) {
    const res = await fetch(path, Object.assign({ cache: "no-store" }, opts, {
      headers: Object.assign({ "Content-Type": "application/json", "X-CSRF-Token": window.CSRF }, opts.headers || {}),
    }));
    if (res.status === 401) { location.reload(); throw new Error("unauthorized"); }
    let body = null;
    try { body = await res.json(); } catch (e) {}
    return { ok: res.ok, status: res.status, body };
  }

  async function refresh() {
    if (loading) { pending = true; return; }
    loading = true;
    try {
      const r = await api("/admin/api/state");
      if (r.ok) {
        state = r.body;
        clockOffset = kst(state.now) - Date.now();
        render();
      }
    } catch (e) {
    } finally {
      loading = false;
      if (pending) { pending = false; refresh(); }
    }
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function minutesSince(iso) {
    return Math.max(0, Math.floor((Date.now() + clockOffset - kst(iso)) / 60000));
  }

  function actionBtn(label, cls, id, action, confirmMsg) {
    const b = el("button", `btn ${cls}`, label);
    b.type = "button";
    b.addEventListener("click", async () => {
      if (confirmMsg && !confirm(confirmMsg)) return;
      b.disabled = true;
      const r = await api(`/admin/api/entries/${id}/${action}`, { method: "POST" });
      if (!r.ok) alert((r.body && r.body.detail) || "처리하지 못했습니다");
      refresh();
    });
    return b;
  }

  function entryRow(e, finished) {
    const row = el("article", `entry st-${e.status}`);
    const head = el("div", "entry-head");
    head.append(el("span", "entry-no", e.no), el("span", "entry-name", e.name || "(삭제됨)"),
                el("span", "entry-phone", e.phone ? `☎ ${e.phone}` : ""),
                el("span", `badge b-${e.status}`, STATUS_TEXT[e.status]));
    const meta = el("div", "entry-meta");
    meta.append(el("span", "", `접수 ${hhmm(kst(e.created_at))}`));
    if (!finished) meta.append(el("span", "wait", `대기 ${minutesSince(e.created_at)}분`));
    if (e.called_at) meta.append(el("span", "", `호출 ${hhmm(kst(e.called_at))}`));
    if (finished && e.completed_at) meta.append(el("span", "", `처리 ${hhmm(kst(e.completed_at))}`));
    const actions = el("div", "entry-actions");
    if (!finished) {
      if (e.status === "waiting") actions.append(actionBtn("호출", "primary", e.id, "call"));
      actions.append(actionBtn("완료", "ok", e.id, "done"));
      actions.append(actionBtn(e.status === "called" ? "노쇼" : "건너뛰기", "warn", e.id, "no_show",
        `${e.no}번 ${e.name}님을 ${e.status === "called" ? "노쇼" : "건너뛰기"} 처리할까요?`));
    } else {
      actions.append(actionBtn("되돌리기", "ghost", e.id, "restore", `${e.no}번을 다시 대기 목록으로 되돌릴까요?`));
    }
    row.append(head, meta, actions);
    return row;
  }

  function render() {
    if (!state) return;
    const s = state.stats;
    const stat = (label, value, cls = "") => {
      const d = el("div", `stat ${cls}`);
      d.append(el("span", "stat-value", value), el("span", "stat-label", label));
      return d;
    };
    $("stats").replaceChildren(
      stat("현재 대기", s.waiting, "hi"),
      stat("총 접수", s.total),
      stat("완료", s.done),
      stat("취소", s.cancelled),
      stat("노쇼", s.no_show),
      stat("평균 대기", s.avg_wait_min === null ? "-" : `${s.avg_wait_min}분`),
    );

    $("active").replaceChildren(...state.active.map((e) => entryRow(e, false)));
    $("active-empty").hidden = state.active.length > 0;
    $("active-count").textContent = state.active.length;
    $("finished").replaceChildren(...state.finished.map((e) => entryRow(e, true)));
    $("finished-count").textContent = state.finished.length;

    const t = $("toggle-open");
    t.textContent = state.is_open ? "접수 마감하기" : "접수 재개하기";
    t.className = `btn ${state.is_open ? "warn" : "primary"}`;
    $("closed-banner").hidden = state.is_open;
  }

  $("toggle-open").addEventListener("click", async () => {
    if (!state) return;
    const next = !state.is_open;
    if (!next && !confirm("접수를 마감할까요? 손님이 새로 접수할 수 없게 됩니다.")) return;
    await api("/admin/api/open", { method: "POST", body: JSON.stringify({ open: next }) });
    refresh();
  });

  $("logout").addEventListener("click", async () => {
    await api("/admin/logout", { method: "POST" });
    location.reload();
  });

  let live = false;
  if ("EventSource" in window) {
    const es = new EventSource("/events");
    es.addEventListener("change", refresh);
    es.onopen = () => { live = true; refresh(); };
    es.onerror = () => { live = false; };
  }
  setInterval(() => { if (!live) refresh(); }, 5000);
  setInterval(render, 30000); // 대기 시간(분) 표시 갱신
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  refresh();
})();
