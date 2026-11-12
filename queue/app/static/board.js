// 현황판(TV) 화면
(() => {
  const $ = (id) => document.getElementById(id);
  const MAX_CALLED = 4; // 지금 순서 칸에 보여줄 호출 번호 수 (첫 번째가 가장 최근)

  // ---------- 시계 ----------
  function tick() {
    const now = new Date();
    const opt = { timeZone: "Asia/Seoul" };
    $("date").textContent = now.toLocaleDateString("ko-KR", Object.assign({ month: "long", day: "numeric", weekday: "short" }, opt));
    $("time").textContent = now.toLocaleTimeString("ko-KR", Object.assign({ hour: "2-digit", minute: "2-digit", hour12: false }, opt));
  }
  tick();
  setInterval(tick, 1000);

  // ---------- 소리 ----------
  // TV 브라우저도 화면을 한 번 눌러야(리모컨 확인 버튼 등) 소리를 낼 수 있음
  let audio = null;
  function enableSound() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      audio.resume();
    } catch (e) { audio = null; }
    $("sound-btn").hidden = true;
  }
  document.addEventListener("click", enableSound);
  document.addEventListener("keydown", enableSound);

  function chime() {
    if (!audio) return;
    const t = audio.currentTime;
    [[0, 784], [0.28, 988], [0.56, 1175]].forEach(([d, f]) => {
      const o = audio.createOscillator(), g = audio.createGain();
      o.type = "sine";
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t + d);
      g.gain.exponentialRampToValueAtTime(0.5, t + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.6);
      o.connect(g).connect(audio.destination);
      o.start(t + d);
      o.stop(t + d + 0.65);
    });
  }
  function announce(no) {
    if (!audio) return;
    chime();
    try {
      if (!("speechSynthesis" in window)) return;
      setTimeout(() => {
        const u = new SpeechSynthesisUtterance(`${no}번 고객님, 순서입니다.`);
        u.lang = "ko-KR";
        u.rate = 0.95;
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
      }, 900);
    } catch (e) {}
  }

  // ---------- 화면 그리기 ----------
  let prevCalled = null; // 직전에 받은 호출 번호 목록
  let loading = false, pending = false;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function render(s) {
    const calledNos = s.called.map((c) => c.no);
    const fresh = prevCalled === null ? [] : calledNos.filter((n) => !prevCalled.includes(n));

    $("called").replaceChildren(...s.called.slice(0, MAX_CALLED).map((c, i) => {
      const row = el("div", "call" + (i === 0 ? " latest" : "") + (fresh.includes(c.no) ? " fresh" : ""));
      const no = el("span", "no", c.no);
      no.append(el("small", "", "번"));
      row.append(no, el("span", "nm", `${c.name} 님`));
      return row;
    }));
    $("called-empty").hidden = s.called.length > 0;
    if (fresh.length) announce(fresh[0]);
    prevCalled = calledNos;

    // QR/마감 칸을 먼저 바꿔야 대기 목록이 쓸 수 있는 높이가 정해짐
    $("join").hidden = !s.is_open;
    $("closed").hidden = s.is_open;

    $("waiting-count").textContent = s.waiting_count;
    const list = $("waiting");
    list.replaceChildren(...s.waiting.map((w, i) => {
      const li = el("li", i === 0 ? "next" : "");
      li.append(el("span", "no", `${w.no}번`), el("span", "nm", w.name));
      return li;
    }));
    // 화면에 다 안 들어가면 뒤에서부터 숨기고 "외 n팀" 표시
    let hidden = 0;
    while (list.children.length > 1 && list.scrollHeight > list.clientHeight + 1) {
      list.lastElementChild.remove();
      hidden++;
    }
    $("waiting-more").hidden = hidden === 0;
    $("waiting-more").textContent = `외 ${hidden}팀 대기 중`;
    $("waiting-empty").hidden = s.waiting.length > 0;
  }

  async function refresh() {
    if (loading) { pending = true; return; }
    loading = true;
    try {
      const res = await fetch("/api/board", { cache: "no-store" });
      if (res.ok) render(await res.json());
    } catch (e) {
    } finally {
      loading = false;
      if (pending) { pending = false; refresh(); }
    }
  }

  // 변경 신호를 SSE 로 받고, 연결이 안 되면 5초마다 직접 확인
  let live = false;
  if ("EventSource" in window) {
    const es = new EventSource("/events");
    es.addEventListener("change", refresh);
    es.onopen = () => { live = true; refresh(); };
    es.onerror = () => { live = false; };
  }
  setInterval(() => { if (!live) refresh(); }, 5000);
  setInterval(refresh, 30000);
  let resizeTimer;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(refresh, 200); });
  refresh();

  // ---------- TV 편의 기능 ----------
  // 마우스를 3초간 움직이지 않으면 커서 숨김
  let cursorTimer;
  document.addEventListener("mousemove", () => {
    document.body.classList.remove("hide-cursor");
    clearTimeout(cursorTimer);
    cursorTimer = setTimeout(() => document.body.classList.add("hide-cursor"), 3000);
  });
  // 더블클릭 또는 F 키로 전체 화면
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
  }
  document.addEventListener("dblclick", toggleFullscreen);
  document.addEventListener("keydown", (e) => { if (e.key === "f" || e.key === "F") toggleFullscreen(); });
  // 화면 꺼짐 방지 (지원하는 브라우저에서만)
  async function keepAwake() {
    try { if (navigator.wakeLock) await navigator.wakeLock.request("screen"); } catch (e) {}
  }
  keepAwake();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { keepAwake(); refresh(); } });
  // 하루 종일 켜두므로 날짜가 바뀌면 새로고침
  const startDay = new Date().toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" });
  setInterval(() => {
    if (new Date().toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" }) !== startDay) location.reload();
  }, 60000);
})();
