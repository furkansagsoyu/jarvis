"use strict";
/* Jarvis telefon sayfası. Satır içi betik/stil yok (CSP). Metinler textContent ile yazılır (XSS yok). */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const KEY = "jarvis_m_token", SKEY = "jarvis_m_speak", TKEY = "jarvis_m_tab";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* özel pencere vb. */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* yok say */ } },
  };
  const ICON = {
    check: "M5 12l5 5 9-10",
    x: "M6 6l12 12M18 6L6 18",
  };
  const icon = (d) => {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg"); s.setAttribute("viewBox", "0 0 24 24");
    const p = document.createElementNS(ns, "path"); p.setAttribute("d", d); s.appendChild(p); return s;
  };

  // ---------------------------------------------------------------- eşleşme (anahtar # parçasında gelir)
  let token = "";
  (function pair() {
    const m = /(?:^|[#&])t=([A-Za-z0-9_-]{16,})/.exec(location.hash);
    if (m) { token = m[1]; store.set(KEY, token); history.replaceState(null, "", location.pathname); }
    else token = store.get(KEY) || "";
  })();

  // ---------------------------------------------------------------- ağ
  async function api(path, body, opts) {
    opts = opts || {};
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), opts.timeout || 20000);
    try {
      const init = { method: body === undefined ? "GET" : "POST", headers: { "X-Token": token }, signal: ctl.signal, cache: "no-store" };
      if (body instanceof Blob) { init.headers["Content-Type"] = body.type || "application/octet-stream"; init.body = body; }
      else if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
      const r = await fetch(path, init);
      let data = {};
      try { data = await r.json(); } catch (e) { /* gövde yok */ }
      if (r.status === 403) showPair();
      return { ok: r.ok, status: r.status, data };
    } catch (e) {
      return { ok: false, status: 0, data: { error: e && e.name === "AbortError" ? "zaman aşımı" : "bağlantı yok" } };
    } finally { clearTimeout(timer); }
  }

  // ---------------------------------------------------------------- arayüz yardımcıları
  let toastTimer = 0;
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function banner(msg) { const b = $("#banner"); b.textContent = msg || ""; b.hidden = !msg; }
  const hhmm = (ts) => { const d = new Date(ts * 1000); return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
  const clean = (t) => String(t || "").replace(/^\[(Telefon|Telegram)\]\s*/, "");

  let view = "chat";
  function show(name) {
    view = name;
    $$(".view").forEach((v) => { v.hidden = v.id !== "v-" + name; });
    $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === name));
    store.set(TKEY, name);
    if (name === "chat") scrollLog(true);
  }
  function showPair() {
    token = ""; store.del(KEY);
    $$(".view").forEach((v) => { v.hidden = v.id !== "v-pair"; });
    $("#tabs").hidden = true;
  }

  // ---------------------------------------------------------------- sohbet
  const log = $("#log");
  let busy = false, lastId = -1, S = null, speakOn = store.get(SKEY) === "1";
  function scrollLog(force) {
    const near = log.scrollHeight - log.scrollTop - log.clientHeight < 140;
    if (force || near) log.scrollTop = log.scrollHeight;
  }
  function bubble(cls, text, ts) {
    const b = el("div", "b " + cls, text);
    if (ts) b.appendChild(el("small", null, hhmm(ts)));
    log.appendChild(b); scrollLog(true); return b;
  }
  function renderHistory(h) {
    log.textContent = "";
    if (!h || !h.length) { log.appendChild(el("div", "empty", "Henüz konuşma yok. Aşağıdan yaz ya da mikrofona dokun.")); return; }
    h.forEach((i) => { if (i.text) bubble(i.who === "sen" ? "me" : "bot", clean(i.text), i.ts); });
  }
  function setBusy(v) {
    busy = v;
    $$("#chips button, #confirm button, #sendbtn, #mic").forEach((b) => { if (b.id !== "mic" || !rec) b.disabled = v; });
    $("#msg").disabled = v;
  }
  function speak(text) {
    if (!speakOn || !window.speechSynthesis || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text); u.lang = "tr-TR"; window.speechSynthesis.speak(u);
    } catch (e) { /* ses yok */ }
  }
  async function exchange(path, payload, label) {
    if (busy) return;
    setBusy(true);
    const empty = $(".empty", log); if (empty) empty.remove();
    bubble("me", label);
    const typing = bubble("bot typing", "Jarvis düşünüyor");
    const r = await api(path, payload, { timeout: 135000 });
    typing.remove();
    if (r.ok && r.data.ok) {
      const reply = r.data.reply || "(cevap boş)";
      bubble("bot", reply); speak(reply); showConfirm(!!r.data.pending);
    } else if (r.status !== 403) {
      bubble("bot err", r.data.error || "Bir hata oldu");
    }
    setBusy(false);
    refresh();
  }
  const send = (text) => exchange("/api/m/chat", { text }, text);
  const command = (id, label) => exchange("/api/m/cmd", { id }, label);
  function showConfirm(v) { $("#confirm").hidden = !v; }

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const inp = $("#msg"), t = inp.value.trim();
    if (!t || busy) return;
    inp.value = ""; send(t);
  });
  $$("#chips button").forEach((b) => b.addEventListener("click", () => command(b.dataset.cmd, b.textContent)));
  $$("#confirm button").forEach((b) => b.addEventListener("click", () => command(b.dataset.cmd, b.textContent)));

  // ---------------------------------------------------------------- ses kaydı (yazıya çevirme bilgisayarda, yerelde)
  let rec = null, stream = null, chunks = [], recStart = 0, recTick = 0, recCancel = false;
  const mic = $("#mic");
  async function toggleRec() {
    if (rec) { stopRec(false); return; }
    if (busy) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast("Bu tarayıcı ses kaydını desteklemiyor"); return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    } catch (e) { toast("Mikrofon izni verilmedi (Chrome site ayarlarından aç)"); return; }
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    const mime = types.find((t) => window.MediaRecorder.isTypeSupported(t)) || "";
    try { rec = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 32000 } : undefined); }
    catch (e) { stream.getTracks().forEach((t) => t.stop()); rec = null; toast("Kayıt başlatılamadı"); return; }
    chunks = []; recCancel = false;
    rec.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data); };
    rec.onstop = onRecStop;
    rec.start();
    recStart = Date.now();
    mic.classList.add("rec");
    const t = $("#rectime"); t.hidden = false;
    recTick = setInterval(() => {
      const s = Math.floor((Date.now() - recStart) / 1000);
      t.textContent = "● " + s + " sn — bitirmek için dokun";
      if (s >= 60) stopRec(false);
    }, 250);
  }
  function stopRec(cancel) {
    if (!rec) return;
    recCancel = !!cancel;
    clearInterval(recTick);
    try { rec.stop(); } catch (e) { /* zaten durmuş */ }
    if (stream) stream.getTracks().forEach((t) => t.stop());
  }
  async function onRecStop() {
    const type = (rec && rec.mimeType) || "audio/webm";
    const blob = new Blob(chunks, { type });
    rec = null; chunks = [];
    mic.classList.remove("rec"); $("#rectime").hidden = true;
    if (recCancel) return;
    if (blob.size < 1500) { toast("Kayıt çok kısaydı"); return; }
    mic.classList.add("work"); mic.disabled = true; toast("Yazıya çevriliyor…");
    const r = await api("/api/m/voice", blob, { timeout: 70000 });
    mic.classList.remove("work"); mic.disabled = false;
    if (r.ok && r.data.text) { send(r.data.text); }
    else if (r.ok) toast("Ses anlaşılamadı, tekrar dene");
    else if (r.status !== 403) toast(r.data.error || "Ses gönderilemedi");
  }
  mic.addEventListener("click", toggleRec);

  // ---------------------------------------------------------------- ajanda
  async function agendaOp(op, extra, okMsg) {
    const r = await api("/api/m/agenda", Object.assign({ op }, extra), { timeout: 20000 });
    if (r.data && r.data.ajanda) { S = S || {}; S.ajanda = r.data.ajanda; renderAgenda(S.ajanda); }
    if (r.ok) toast(r.data.ok ? okMsg || r.data.msg || "Tamam" : r.data.msg || "Olmadı");
    else if (r.status !== 403) toast(r.data.error || "İşlem yapılamadı");
    return r.ok && r.data.ok;
  }
  function row(cls, title, sub, actions) {
    const li = el("li", cls);
    const t = el("div", "t", title); if (sub) t.appendChild(el("small", null, sub));
    li.appendChild(t); (actions || []).forEach((a) => li.appendChild(a)); return li;
  }
  function actBtn(path, label, cls, fn) {
    const b = el("button", "act " + (cls || "")); b.type = "button"; b.setAttribute("aria-label", label); b.title = label;
    b.appendChild(icon(path)); b.addEventListener("click", fn); return b;
  }
  const dmy = (iso) => { const p = String(iso || "").split("-"); return p.length === 3 ? p[2] + "." + p[1] : iso; };
  function renderAgenda(a) {
    a = a || {};
    const today = $("#ev-today"); today.textContent = "";
    (a.events_today || []).forEach((e) => today.appendChild(row(e.past ? "past" : "", (e.time ? e.time + "  " : "") + e.title)));
    if (!today.children.length) today.appendChild(el("li", "none", "Bugün etkinlik yok"));

    const tl = $("#tasks"); tl.textContent = "";
    (a.tasks || []).forEach((t) => {
      const li = row(t.overdue ? "over" : "", t.title, (t.due ? (t.overdue ? "Gecikti · " : "Son: ") + dmy(t.due) : "Tarihsiz"), [
        actBtn(ICON.check, "Bitti", "", () => agendaOp("done_task", { id: t.id }, "Görev bitti")),
        actBtn(ICON.x, "Sil", "del", () => { if (confirm("Görev silinsin mi?")) agendaOp("delete_task", { id: t.id }, "Görev silindi"); }),
      ]);
      const dot = el("span", "dot " + (t.priority || "")); li.insertBefore(dot, li.firstChild);
      tl.appendChild(li);
    });
    if (!tl.children.length) tl.appendChild(el("li", "none", "Açık görev yok"));
    const cnt = $("#task-count"); cnt.textContent = a.open_tasks ? String(a.open_tasks) : ""; cnt.hidden = !a.open_tasks;
    const badge = $("#nbadge"); badge.textContent = String(a.overdue || ""); badge.hidden = !a.overdue;

    const ev = $("#events"); ev.textContent = "";
    (a.events || []).filter((e) => !e.past).forEach((e) => ev.appendChild(row("", e.title, dmy(e.date) + (e.time ? " " + e.time : ""), [
      actBtn(ICON.x, "Sil", "del", () => { if (confirm("Etkinlik silinsin mi?")) agendaOp("cancel_event", { id: e.id }, "Etkinlik silindi"); }),
    ])));
    if (!ev.children.length) ev.appendChild(el("li", "none", "Yaklaşan etkinlik yok"));
  }
  $("#f-task").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, btn = $("button", f); btn.disabled = true;
    const ok = await agendaOp("add_task", { title: f.title.value, due: f.due.value, priority: f.priority.value });
    btn.disabled = false; if (ok) f.reset();
  });
  $("#f-event").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, btn = $("button", f); btn.disabled = true;
    const ok = await agendaOp("add_event", { title: f.title.value, date: f.date.value, time: f.time.value });
    btn.disabled = false; if (ok) f.reset();
  });

  // ---------------------------------------------------------------- durum
  function gauge(label, text, pct) {
    const g = el("div", "g"), lab = el("div", "lab"), bar = el("div", "bar"), fill = el("i");
    lab.appendChild(el("span", null, label)); lab.appendChild(el("span", null, text));
    fill.style.width = Math.max(0, Math.min(100, pct || 0)) + "%"; if (pct >= 90) fill.className = "hot";
    bar.appendChild(fill); g.appendChild(lab); g.appendChild(bar); return g;
  }
  function renderStatus(s) {
    const d = s.durum || {}, sys = s.sistem || {}, g = $("#gauges"); g.textContent = "";
    $("#st-state").textContent = d.label || "—";
    $("#st-model").textContent = s.model || "—";
    const alt = s.alt || {};
    $("#st-temp").textContent = alt.temp ? alt.temp : "—";
    const on = $("#st-online"); on.textContent = alt.online ? "internet var" : "internet yok"; on.className = "tag " + (alt.online ? "ok" : "bad");
    if (sys.cpu != null) g.appendChild(gauge("İşlemci", sys.cpu + "%" + (sys.cpu_temp ? " · " + Math.round(sys.cpu_temp) + "°C" : ""), sys.cpu));
    if (sys.ram) g.appendChild(gauge("Bellek", sys.ram.used + " / " + sys.ram.total + " GB", sys.ram.used / sys.ram.total * 100));
    if (sys.gpu) g.appendChild(gauge("Ekran kartı", sys.gpu.util + "% · " + (sys.gpu.used / 1024).toFixed(1) + "/" + Math.round(sys.gpu.total / 1024) + " GB · " + sys.gpu.temp + "°C", sys.gpu.used / sys.gpu.total * 100));
    if (sys.disk) g.appendChild(gauge("Disk", sys.disk.used + " / " + sys.disk.total + " GB", sys.disk.used / sys.disk.total * 100));
    $("#b-mute").setAttribute("aria-pressed", d.muted ? "true" : "false");
    $("#b-focus").setAttribute("aria-pressed", d.focus ? "true" : "false");
  }
  async function act(id, okMsg) {
    const r = await api("/api/m/cmd", { id }, { timeout: 15000 });
    if (r.ok) { toast(okMsg); refresh(); } else if (r.status !== 403) toast(r.data.error || "Olmadı");
  }
  $("#b-stop").addEventListener("click", () => act("stop", "Konuşma kesildi"));
  $("#b-mute").addEventListener("click", () => act("mute", "Mikrofon değiştirildi"));
  $("#b-focus").addEventListener("click", () => act("focus", "Odak modu değiştirildi"));
  $("#unpair").addEventListener("click", () => { if (confirm("Bu telefonun anahtarı silinsin mi?")) { showPair(); } });

  // ---------------------------------------------------------------- durum çekme
  let fails = 0, inflight = false;
  async function refresh() {
    if (!token || inflight) return;
    inflight = true;
    const btn = $("#reload"); btn.classList.add("spin");
    const r = await api("/api/m/state", undefined, { timeout: 12000 });
    btn.classList.remove("spin"); inflight = false;
    if (!r.ok) {
      if (r.status === 403) return;
      fails++;
      if (r.status === 429) banner("Çok fazla istek; biraz bekle.");
      else if (fails >= 2) { banner("Jarvis'e ulaşılamıyor — Tailscale açık mı, bilgisayar uyanık mı?"); $("#pill").textContent = "çevrimdışı"; $("#pill").dataset.s = "off"; }
      return;
    }
    fails = 0; banner("");
    const s = r.data; S = s;
    const d = s.durum || {};
    $("#pill").textContent = d.label || "—"; $("#pill").dataset.s = d.state || "";
    const hist = s.history || [], top = hist.length ? hist[hist.length - 1].id : 0;
    if (!busy && (lastId === -1 || top !== lastId)) { renderHistory(hist); lastId = top; }
    if (!busy) showConfirm(!!d.pending);
    $("#msg").placeholder = s.voice ? "Jarvis'e yaz…" : "Jarvis'e yaz… (ses tanıma kapalı)";
    renderAgenda(s.ajanda); renderStatus(s);
  }

  // ---------------------------------------------------------------- başlangıç
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => { show(b.dataset.view); refresh(); }));
  $("#reload").addEventListener("click", refresh);
  const sp = $("#speak");
  const paintSpeak = () => sp.setAttribute("aria-pressed", speakOn ? "true" : "false");
  paintSpeak();
  sp.addEventListener("click", () => {
    speakOn = !speakOn; store.set(SKEY, speakOn ? "1" : "0"); paintSpeak();
    if (!speakOn && window.speechSynthesis) window.speechSynthesis.cancel();
    toast(speakOn ? "Cevaplar sesli okunacak" : "Sesli okuma kapalı");
  });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
  setInterval(() => { if (document.visibilityState === "visible" && !busy && !rec) refresh(); }, 6000);

  if (!token) showPair();
  else {
    const t = store.get(TKEY);
    show(t === "agenda" || t === "status" ? t : "chat");
    refresh();
  }
})();
