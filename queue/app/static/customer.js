// 손님 화면 (접수 폼 + 내 번호 화면)
const Queue = (() => {
  const KEY = "queue_token";
  const NAME_RE = /^[가-힣]{2,4}$/;
  const PHONE_RE = /^[0-9]{4}$/;
  // 조합 중인 낱자(ㄱ, ㅏ 등)는 입력 도중이므로 바로 오류로 보지 않음
  const NAME_TYPING_RE = /^[가-힣ㄱ-ㅎㅏ-ㅣ]{0,4}$/;
  const NAME_ERROR = "이름은 한글 2~4자로 입력해주세요";
  const PHONE_ERROR = "전화번호 뒷자리 4자리를 입력해주세요";
  const ACTIVE = ["waiting", "called"];
  const STATUS_TEXT = {
    waiting: "대기중",
    called: "호출됨",
    done: "완료",
    cancelled: "취소됨",
    no_show: "호출 후 미방문",
  };

  const $ = (id) => document.getElementById(id);
  const store = {
    get() { try { return localStorage.getItem(KEY); } catch (e) { return null; } },
    set(v) { try { localStorage.setItem(KEY, v); } catch (e) {} },
    del() { try { localStorage.removeItem(KEY); } catch (e) {} },
  };

  async function getJSON(url, opts) {
    const res = await fetch(url, Object.assign({ cache: "no-store" }, opts));
    let body = null;
    try { body = await res.json(); } catch (e) {}
    return { ok: res.ok, status: res.status, body };
  }

  // 변경 신호를 SSE 로 받고, 연결이 안 되면 5초마다 직접 확인
  function subscribe(onChange) {
    // 최근 20초 안에 신호를 실제로 받았을 때만 실시간으로 봄.
    // 연결은 됐는데 신호가 안 오면(일부 프록시가 모아두는 경우) 5초마다 직접 확인
    let lastMsg = 0;
    if ("EventSource" in window) {
      const es = new EventSource("/events");
      es.addEventListener("ping", () => { lastMsg = Date.now(); });
      es.addEventListener("change", () => { lastMsg = Date.now(); onChange(); });
      es.onerror = () => { lastMsg = 0; };
    }
    setInterval(() => { if (Date.now() - lastMsg > 20000) onChange(); }, 5000);
    setInterval(onChange, 30000); // 혹시 놓친 신호 대비
    document.addEventListener("visibilitychange", () => { if (!document.hidden) onChange(); });
  }

  // ---------- 접수 폼 ----------
  function initForm() {
    const saved = store.get();
    if (saved) {
      getJSON(`/api/ticket/${encodeURIComponent(saved)}`).then((r) => {
        if (r.ok && !r.body.expired && ACTIVE.includes(r.body.status)) {
          location.replace(`/t/${encodeURIComponent(saved)}`);
        } else if (r.status === 404 || (r.ok && (r.body.expired || !ACTIVE.includes(r.body.status)))) {
          store.del();
        }
      }).catch(() => {});
    }

    const form = $("form"), name = $("name"), phone = $("phone"), btn = $("submit");
    const touched = { name: false, phone: false };
    let busy = false;

    function check() {
      const n = name.value.normalize("NFC").trim();
      const p = phone.value.trim();
      const nameOk = NAME_RE.test(n);
      const phoneOk = PHONE_RE.test(p);
      const showName = !nameOk && (touched.name || !NAME_TYPING_RE.test(n));
      const showPhone = !phoneOk && touched.phone;
      $("name-hint").textContent = showName ? NAME_ERROR : "";
      $("phone-hint").textContent = showPhone ? PHONE_ERROR : "";
      name.classList.toggle("invalid", showName);
      phone.classList.toggle("invalid", showPhone);
      btn.disabled = busy || !(nameOk && phoneOk);
      return { n, p };
    }

    phone.addEventListener("input", () => {
      const digits = phone.value.replace(/[^0-9]/g, "").slice(0, 4);
      if (digits !== phone.value) phone.value = digits;
      if (digits.length === 4) touched.phone = true;
      check();
    });
    ["input", "compositionend", "change"].forEach((ev) => name.addEventListener(ev, check));
    name.addEventListener("blur", () => { if (name.value) touched.name = true; check(); });
    phone.addEventListener("blur", () => { if (phone.value) touched.phone = true; check(); });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      touched.name = touched.phone = true;
      const { n, p } = check();
      if (btn.disabled) return;
      busy = true; btn.disabled = true; btn.textContent = "발급 중…";
      $("form-error").hidden = true;
      try {
        const r = await getJSON("/api/tickets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: n, phone: p }),
        });
        if (r.ok) {
          store.set(r.body.token);
          if (r.body.existing) {
            showFormError("이미 접수된 번호가 있어 내 번호 화면으로 이동합니다.");
            setTimeout(() => location.replace(r.body.url), 1200);
          } else {
            location.replace(r.body.url);
          }
          return;
        }
        if (r.status === 409) setClosed(true);
        else if (r.status === 422 && r.body) {
          $(`${r.body.field}-hint`).textContent = r.body.detail;
        } else showFormError("잠시 후 다시 시도해주세요.");
      } catch (err) {
        showFormError("네트워크 연결을 확인해주세요.");
      }
      busy = false; btn.textContent = "대기번호 받기"; check();
    });

    function showFormError(msg) {
      $("form-error").textContent = msg;
      $("form-error").hidden = false;
    }
    function setClosed(closed) {
      $("closed-notice").hidden = !closed;
      form.hidden = closed;
    }

    subscribe(async () => {
      try {
        const r = await getJSON("/api/queue");
        if (!r.ok) return;
        $("waiting-count").innerHTML = `현재 대기 <b>${Number(r.body.waiting_count)}</b>팀`;
        setClosed(!r.body.is_open);
      } catch (e) {}
    });
    check();
  }

  // ---------- 호출 알림 ----------
  let audio = null;
  function unlockSound() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      audio.resume();
    } catch (e) { audio = null; }
  }
  function beep() {
    if (!audio) return;
    const t = audio.currentTime;
    [0, 0.35, 0.7].forEach((d) => {
      const o = audio.createOscillator(), g = audio.createGain();
      o.type = "sine";
      o.frequency.value = d === 0.7 ? 1175 : 880;
      g.gain.setValueAtTime(0.0001, t + d);
      g.gain.exponentialRampToValueAtTime(0.5, t + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.3);
      o.connect(g).connect(audio.destination);
      o.start(t + d);
      o.stop(t + d + 0.32);
    });
  }
  function vibrate(pattern) {
    try { if (navigator.vibrate) navigator.vibrate(pattern); } catch (e) {}
  }

  let alertTimers = [];
  let titleTimer = null;
  const baseTitle = document.title;
  function startCallAlert() {
    stopCallAlert();
    const ring = () => { beep(); vibrate([400, 150, 400, 150, 600]); };
    ring();
    alertTimers = [setTimeout(ring, 10000), setTimeout(ring, 20000)];
    let on = false;
    titleTimer = setInterval(() => {
      on = !on;
      document.title = on ? "🔔 호출되었습니다!" : baseTitle;
    }, 1000);
  }
  function stopCallAlert() {
    alertTimers.forEach(clearTimeout);
    alertTimers = [];
    if (titleTimer) clearInterval(titleTimer);
    titleTimer = null;
    document.title = baseTitle;
  }

  // ---------- 내 번호 화면 ----------
  function initTicket(token) {
    store.set(token);
    const url = `/api/ticket/${encodeURIComponent(token)}`;
    let prevStatus = null;
    let loading = false;

    const soundBtn = $("sound-btn");
    soundBtn.addEventListener("click", () => {
      unlockSound();
      beep();
      vibrate(200);
      soundBtn.textContent = "🔔 호출 알림이 켜졌습니다";
      soundBtn.classList.add("on");
    });

    $("cancel-btn").addEventListener("click", async () => {
      if (!confirm("대기를 취소하시겠습니까?\n취소하면 순번이 사라집니다.")) return;
      const r = await getJSON(`${url}/cancel`, { method: "POST" });
      if (r.ok) store.del();
      refresh();
    });

    async function refresh() {
      if (loading) return;
      loading = true;
      try {
        const r = await getJSON(url);
        if (r.status === 404) { store.del(); location.replace("/"); return; }
        if (r.ok) render(r.body);
      } catch (e) {
      } finally {
        loading = false;
      }
    }

    function render(v) {
      const status = v.expired ? "expired" : v.status;
      $("ticket").dataset.status = status;
      $("no").textContent = v.ticket_no;
      $("who").textContent = `${v.name} 님`;
      $("status").textContent = v.expired ? "지난 날짜의 번호" : STATUS_TEXT[v.status];
      $("call-msg").hidden = status !== "called";

      let ahead = "";
      if (status === "waiting") ahead = v.ahead === 0 ? "곧 호출됩니다" : `내 앞에 ${v.ahead}팀 대기 중`;
      else if (status === "done") ahead = "이용해주셔서 감사합니다";
      else if (status === "cancelled") ahead = "대기가 취소되었습니다";
      else if (status === "no_show") ahead = "호출 후 오지 않으셔서 순번이 넘어갔습니다";
      else if (status === "expired") ahead = "오늘 새로 접수해주세요";
      $("ahead").textContent = ahead;

      const active = ACTIVE.includes(status);
      $("cancel-btn").hidden = !active;
      $("new-btn").hidden = active;
      $("sound-btn").hidden = !active;
      if (!active) store.del();

      const list = $("queue");
      list.replaceChildren(...v.queue.map((q) => {
        const li = document.createElement("li");
        if (q.mine) li.classList.add("mine");
        if (q.status === "called") li.classList.add("called");
        const no = document.createElement("span");
        no.className = "q-no";
        no.textContent = q.no;
        const nm = document.createElement("span");
        nm.className = "q-name";
        nm.textContent = q.name + (q.mine ? " (나)" : "");
        li.append(no, nm);
        if (q.status === "called") {
          const tag = document.createElement("span");
          tag.className = "q-tag";
          tag.textContent = "호출됨";
          li.append(tag);
        }
        return li;
      }));
      $("queue-empty").hidden = v.queue.length > 0;

      if (status === "called" && prevStatus !== null && prevStatus !== "called") startCallAlert();
      if (status !== "called") stopCallAlert();
      prevStatus = status;
    }

    subscribe(refresh);
    refresh();
  }

  return { initForm, initTicket };
})();
