"use strict";
/* JARVIS Komut Merkezi arayüzü. Yeni panel: HTML'e kutu koy, PANELS'a çizici ekle, dashboard/state.py'de aynı adlı sağlayıcıyı yaz.
   Yeni sayfa: VIEWS'a {title, build(body), update(s)} ekle. Tüm dinamik metinler textContent ile yazılır (HTML enjeksiyonu yalnızca sayısal ölçerde). */
const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $ = (s, r = document) => r.querySelector(s);
const SVG = (id) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24");
  const u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + id); s.appendChild(u); return s; };
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) { if (k === "class") e.className = v; else if (k === "icon") e.appendChild(SVG(v)); else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v); }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
const fill = (el, ...kids) => el.replaceChildren(...kids.flat().filter(Boolean));
let S = null, offline = 0;
const sigs = {};
let ACC = "31,216,255", CY = "#1fd8ff", CY2 = "#7be9ff", curTheme = "cyan";
/* ---- temalar: cyan varsayılan (style.css :root); diğerleri değişkenleri ezer ---- */
const THEME_META = { cyan: ["Cyan (varsayılan)", "#1fd8ff", "#030b18"], amber: ["Amber", "#ffb23f", "#0e0a03"], green: ["Yeşil", "#2ee89a", "#020d08"], violet: ["Mor", "#a779ff", "#08040f"], light: ["Açık tema", "#0b78b5", "#e9eff6"] };
const HUES = { amber: 38, green: 152, violet: 265 };
const THEME_KEYS = ["--bg", "--bg-a", "--line", "--line2", "--cy", "--cy2", "--cy-rgb", "--tx", "--tx2", "--mut", "--panel-a", "--panel-b", "--card", "--card2", "--side-a", "--side-b", "--solid", "--badge", "--gaugebg", "--on-cy", "--hi", "--orb-bg", "--orb-bg2", "--ok", "--warn", "--bad", "--vio"];
function hsl2rgb(h, s, l) { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l), f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [Math.round(255 * f(0)), Math.round(255 * f(8)), Math.round(255 * f(4))]; }
function themeVars(name) {
  if (name === "light") return { "--bg": "#e9eff6", "--bg-a": "#ffffff", "--line": "#b8cadb", "--line2": "#7fa6c6", "--cy": "#0b78b5", "--cy2": "#0a5f93", "--cy-rgb": "11,120,181", "--tx": "#14283b", "--tx2": "#2b4660", "--mut": "#5d768c",
    "--panel-a": "rgba(255,255,255,.92)", "--panel-b": "rgba(238,245,251,.95)", "--card": "rgba(255,255,255,.85)", "--card2": "rgba(255,255,255,.95)", "--side-a": "rgba(255,255,255,.95)", "--side-b": "rgba(233,241,248,.97)",
    "--solid": "#f4f8fc", "--badge": "#d3e6f5", "--gaugebg": "#d6e3ee", "--on-cy": "#ffffff", "--hi": "#0b1b2b", "--orb-bg": "rgba(11,120,181,.12)", "--orb-bg2": "rgba(240,246,252,.9)", "--ok": "#0d8f5f", "--warn": "#b86e00", "--bad": "#d02c45", "--vio": "#7040d0" };
  const h = HUES[name]; if (h == null) return null;
  const hs = (s, l, a) => "hsla(" + h + "," + s + "%," + l + "%," + (a ?? 1) + ")";
  return { "--bg": hs(60, 5), "--bg-a": hs(60, 14), "--line": hs(55, 22), "--line2": hs(60, 33), "--cy": hs(100, 58), "--cy2": hs(100, 76), "--cy-rgb": hsl2rgb(h, 100, 58).join(","), "--tx": hs(60, 90), "--tx2": hs(40, 82), "--mut": hs(25, 55),
    "--panel-a": hs(70, 15, .78), "--panel-b": hs(70, 7, .82), "--card": hs(65, 12, .7), "--card2": hs(65, 9, .85), "--side-a": hs(65, 13, .85), "--side-b": hs(65, 6, .9), "--solid": hs(65, 9), "--badge": hs(60, 22), "--gaugebg": hs(55, 18),
    "--on-cy": hs(90, 10), "--hi": "#fff", "--orb-bg": hs(70, 32, .35), "--orb-bg2": hs(65, 6, .85) };
}
function applyTheme(name) {
  if (!THEME_META[name]) name = "cyan"; curTheme = name;
  const st = document.documentElement.style; THEME_KEYS.forEach((k) => st.removeProperty(k));
  const v = themeVars(name); if (v) Object.entries(v).forEach(([k, val]) => st.setProperty(k, val));
  document.documentElement.dataset.theme = name;
  const cs = getComputedStyle(document.documentElement); ACC = cs.getPropertyValue("--cy-rgb").trim() || "31,216,255"; CY = cs.getPropertyValue("--cy").trim() || "#1fd8ff"; CY2 = cs.getPropertyValue("--cy2").trim() || "#7be9ff";
  try { localStorage.setItem("jv-theme", name); } catch (e) { /* depolama yoksa sorun değil */ }
  sigs.chat0 = null;
}
try { applyTheme(localStorage.getItem("jv-theme") || "cyan"); } catch (e) { applyTheme("cyan"); }
const changed = (key, obj) => { const j = JSON.stringify(obj); if (sigs[key] === j) return false; sigs[key] = j; return true; };

async function api(path, body) {
  const r = await fetch(path, { method: body ? "POST" : "GET", headers: { "X-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
const send = (o) => api("/api/cmd", o).then(() => { poll(); setTimeout(poll, 900); setTimeout(poll, 2500); }).catch(() => {});
let toastT = 0;
function toast(msg, ok = true) { const t = $("#toast"); t.textContent = msg; t.className = ok ? "ok" : "bad"; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), 3200); }
const p2 = (n) => String(n).padStart(2, "0");
const GUN = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"], AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const isoDay = (d) => d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate());
function dayLabel(iso) { const d = new Date(iso + "T12:00:00"), t = isoDay(new Date()); const tm = isoDay(new Date(Date.now() + 864e5));
  return d.getDate() + " " + AY[d.getMonth()] + " " + GUN[d.getDay()] + (iso === t ? " · Bugün" : iso === tm ? " · Yarın" : ""); }

/* iki kez tıkla silme (pencere onay kutusu yok) */
function confirmBtn(label, onYes, cls = "") {
  const b = h("button", { class: "mini bad " + cls }, label); let t = 0;
  b.onclick = () => { if (b.dataset.arm) { clearTimeout(t); onYes(); return; } b.dataset.arm = "1"; b.textContent = "Emin misin?"; b.classList.add("arm");
    t = setTimeout(() => { delete b.dataset.arm; b.textContent = label; b.classList.remove("arm"); }, 3000); };
  return b;
}

/* ---------------- sohbet kutusu (her sekmede + ana ekranda çekmece) ---------------- */
const chats = [];
function chatBox(extra = "") {
  const log = h("div", { class: "chatlog" }), inp = h("input", { placeholder: "Jarvis'e yaz…", maxlength: "300", autocomplete: "off" });
  const form = h("form", { class: "chatform" }, inp, h("button", { type: "submit" }, "Gönder"));
  const box = h("div", { class: "chat " + extra }, log, form), me = { el: box, key: "chat" + chats.length }; delete sigs[me.key];
  form.onsubmit = (e) => { e.preventDefault(); const v = inp.value.trim(); if (v) { send({ say: v, chat: true }); inp.value = ""; } };
  me.update = (s) => {
    const k = s.konusma || {}, busy = s.durum && (s.durum.state === "thinking");
    if (!changed(me.key, [k.recent, busy])) return;
    const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
    fill(log, !(k.recent || []).length && !busy ? h("div", { class: "empty" }, "Henüz yazışma yok. Aşağıdan Jarvis'e bir şey yaz; cevabı hem burada görür hem sesli duyarsın.") : null, (k.recent || []).slice(extra.includes("full") ? -30 : -14).map((m) => h("div", { class: "msg " + (m.who === "sen" ? "me" : "ai") }, h("div", {}, m.text), h("small", {}, (m.who === "sen" ? "Sen" : "Jarvis") + " · " + m.time))),
      busy ? h("div", { class: "msg ai dots" }, h("div", {}, "● ● ●")) : null);
    if (stick || !log.dataset.init) { log.scrollTop = log.scrollHeight; log.dataset.init = "1"; }
  };
  chats.push(me); return me;
}

/* ---------------- sekmeler ---------------- */
const NAV = [
  ["merkez", "Komut Merkezi", "grid"], ["yazisma", "Yazışma", "chat"], ["cekirdek", "AI Çekirdeği", "cpu"], ["ajanlar", "Ajanlar", "bot"],
  ["gorevler", "Görevler", "list"], ["takvim", "Takvim", "cal"], ["hafiza", "Hafıza", "db"],
  ["konusmalar", "Konuşmalar", "hist"], ["bilgi", "Bilgi Tabanı", "book"], ["araclar", "Araçlar ve Beceriler", "tool"], ["akislar", "İş Akışları", "flow"], ["ayarlar", "Ayarlar", "gear"],
];
const row = (icon, title, sub, cls = "") => h("li", { class: cls }, SVG(icon), h("div", {}, h("b", {}, title), sub ? h("small", {}, sub) : null));
function listUl(items, empty) {
  if (!items || !items.length) return h("div", { class: "empty" }, empty || "Veri yok.");
  return h("ul", { class: "rows", style: "height:auto" }, items.map(([ic, t, sub]) => row(ic, t, sub)));
}
/* basit sayfa: veriyi listeler (yalnızca veri değişince yeniden çizer) */
const simple = (title, fn, empty) => ({ title, build(body, key) { body._c = h("div", { class: "scroll" }); fill(body, body._c); }, update(s, body, key) {
  const items = fn(s); if (changed(key, items)) fill(body._c, listUl(items, empty)); } });
const VIEWS = {};
VIEWS.yazisma = { title: "YAZIŞMA — JARVİS İLE KONUŞ",
  build(body) { const b = h("button", { class: "pill vo", title: "Açıkken Jarvis yazdığın mesajlara sesli de cevap verir" }); b.onclick = () => send({ id: "chatvoice" }); body._vb = b;
    body.append(h("div", { class: "convbar" }, b, h("span", { class: "muted" }, "Kapalıyken yalnızca yazıyla cevap verir; sesle konuşman etkilenmez.")), chatBox("full").el); },
  update(s, body) { const on = !s.durum || s.durum.chat_voice !== false; body._vb.classList.toggle("on", on);
    fill(body._vb, SVG("vol"), "Sesli cevap: " + (on ? "Açık" : "Kapalı")); } };
VIEWS.cekirdek = simple("YAPAY ZEKÂ ÇEKİRDEĞİ", (s) => s.model && [
  ["cpu", "Dil modeli", s.model.llm.map((m) => m.name + " (" + m.role + (m.active ? ", aktif" : "") + ")").join(", ")], ["vol", "Konuşma tanıma", s.model.stt], ["vol", "Ses motoru", s.model.tts],
  ["bolt", "Uyanma sözcüğü", s.model.wake], ["tool", "Yetenek sayısı", String(s.model.tools)], ["tool", "Araç çağrısı (oturum)", String(s.model.tool_calls)]]);
VIEWS.ajanlar = simple("AJANLAR", (s) => (s.ajanlar || []).map((a) => ["bot", a.name, a.status + " — " + a.detail]));
VIEWS.hafiza = simple("HAFIZA", (s) => ((s.hafiza || {}).last || []).map((t) => ["db", t, ""]), "Kayıtlı bilgi yok.");
VIEWS.bilgi = simple("BİLGİ TABANI — YAKINDA", () => [], "Bu bölüm henüz yok; ileride eklenecek.");
VIEWS.akislar = simple("İŞ AKIŞLARI — YAKINDA", () => [], "Bu bölüm henüz yok; ileride eklenecek.");

/* --- Görevler --- */
function agendaCall(o, done) { return api("/api/agenda", o).then((r) => { toast(r.msg, r.ok); if (r.ok && done) done(); poll(); }).catch(() => toast("Bağlantı hatası", false)); }
VIEWS.gorevler = {
  title: "GÖREVLER",
  build(body) {
    const t = h("input", { placeholder: "Yeni görev…", maxlength: "120" }), d = h("input", { type: "date" });
    const pr = h("select", {}, ...["orta", "yüksek", "düşük"].map((x) => h("option", { value: x }, "Öncelik: " + x)));
    const f = h("form", { class: "addrow" }, t, d, pr, h("button", { type: "submit" }, "Ekle"));
    f.onsubmit = (e) => { e.preventDefault(); if (!t.value.trim()) return; agendaCall({ op: "add_task", title: t.value, due: d.value, priority: pr.value }, () => { t.value = ""; }); };
    body._c = h("div", { class: "scroll" }); fill(body, f, body._c);
  },
  update(s, body, key) {
    const tasks = (s.ajanda || {}).all_tasks || []; if (!changed(key, tasks)) return;
    fill(body._c, tasks.length ? h("ul", { class: "rows", style: "height:auto" }, tasks.map((t) => h("li", { class: t.overdue ? "UYARI" : "" },
      h("i", { class: "pri " + t.priority }), h("div", {}, h("b", {}, t.title), h("small", {}, (t.due ? dayLabel(t.due) : "Tarihsiz") + " · " + t.priority + (t.overdue ? " · GECİKMİŞ" : ""))),
      h("button", { class: "mini", onclick: () => agendaCall({ op: "done_task", id: t.id }) }, "Bitti"),
      confirmBtn("Sil", () => agendaCall({ op: "delete_task", id: t.id }))))) : h("div", { class: "empty" }, "Açık görev yok. Yukarıdan ekleyebilirsin."));
  },
};
/* --- Takvim --- */
VIEWS.takvim = {
  title: "TAKVİM",
  build(body) {
    const t = h("input", { placeholder: "Yeni etkinlik…", maxlength: "120" }), d = h("input", { type: "date", value: isoDay(new Date()) }), tm = h("input", { type: "time" });
    const f = h("form", { class: "addrow" }, t, d, tm, h("button", { type: "submit" }, "Ekle"));
    f.onsubmit = (e) => { e.preventDefault(); if (!t.value.trim() || !d.value) return; agendaCall({ op: "add_event", title: t.value, date: d.value, time: tm.value }, () => { t.value = ""; tm.value = ""; }); };
    body._c = h("div", { class: "scroll" }); fill(body, f, body._c);
  },
  update(s, body, key) {
    const ev = (s.ajanda || {}).events || []; if (!changed(key, ev)) return;
    if (!ev.length) return fill(body._c, h("div", { class: "empty" }, "Yaklaşan etkinlik yok. Saat boş bırakılırsa tüm gün olur."));
    const days = {}; ev.forEach((e) => (days[e.date] = days[e.date] || []).push(e));
    fill(body._c, Object.keys(days).sort().map((day) => h("div", { class: "daygrp" }, h("h5", {}, dayLabel(day)),
      h("ul", { class: "rows", style: "height:auto" }, days[day].map((e) => h("li", { class: e.past ? "past" : "" }, SVG("cal"),
        h("div", {}, h("b", {}, e.title), h("small", {}, e.time || "Tüm gün")), confirmBtn("Sil", () => agendaCall({ op: "cancel_event", id: e.id }))))))));
  },
};
/* --- Konuşmalar: sohbet listesi (gün/saat) -> tıklayınca o sohbetin geçmişi --- */
let convQuery = "";
const hm = (ts) => { const d = new Date(ts * 1000); return p2(d.getHours()) + ":" + p2(d.getMinutes()); };
VIEWS.konusmalar = {
  title: "KONUŞMALAR",
  build(body, key) {
    const sel = h("select", {}, ...[[7, "7 gün"], [14, "14 gün"], [30, "30 gün"], [90, "90 gün"], [0, "Süresiz"]].map(([v, l]) => h("option", { value: v }, l)));
    sel.onchange = () => api("/api/conv", { op: "retention", days: +sel.value }).then(() => { toast("Saklama süresi güncellendi"); body._load(true); });
    const q = h("span", { class: "qtag" }), info = h("span", { class: "muted" });
    const clr = confirmBtn("Tümünü sil", () => api("/api/conv", { op: "clear" }).then((r) => { toast(r.n + " kayıt silindi"); body._load(true); }));
    const bar = h("div", { class: "convbar" }, h("span", {}, "Otomatik silme:"), sel, info, h("span", { class: "sp" }), q, clr);
    const list = h("div", { class: "scroll" }); fill(body, bar, list);
    Object.assign(body, { _list: list, _sel: sel, _q: q, _info: info, _bar: bar, _open: null });
    body._load = (force) => (body._open ? loadOpen(body, force) : loadList(body, force));
    body._load(true);
  },
  update(s, body, key) { if (changed(key + "rev", (s.konusma || {}).rev)) body._load(false); },
};
async function loadList(body, force) {
  try {
    const r = await api("/api/sessions?q=" + encodeURIComponent(convQuery)); if (!body._list.isConnected || body._open) return;
    body._sel.value = String(r.retention); body._info.textContent = r.sessions.length + " sohbet · " + r.total + " mesaj";
    fill(body._q, convQuery ? h("span", {}, "Arama: “" + convQuery + "”  ", h("button", { class: "mini", onclick: () => setQuery("") }, "Temizle")) : null);
    if (!force && !changed("convs", r.sessions)) return; sigs.convs = JSON.stringify(r.sessions);
    if (!r.sessions.length) return fill(body._list, h("div", { class: "empty" }, convQuery ? "Eşleşen sohbet yok." : "Henüz kayıtlı sohbet yok."));
    const days = {}; r.sessions.forEach((x) => { const k = isoDay(new Date(x.start * 1000)); (days[k] = days[k] || []).push(x); });
    fill(body._list, Object.keys(days).sort().reverse().map((day) => h("div", { class: "daygrp" }, h("h5", {}, dayLabel(day)),
      h("ul", { class: "rows", style: "height:auto" }, days[day].map((x) => h("li", { class: "sess", onclick: () => openSession(body, x) }, SVG("chat"),
        h("div", {}, h("b", {}, x.title || "(boş)"),
          h("small", {}, hm(x.start) + (x.count > 1 ? " – " + hm(x.end) : "") + " · " + x.count + " mesaj" + (x.live ? " · devam ediyor" : "")),
          x.snippet ? h("small", { class: "snip" }, ...hilite(x.snippet, convQuery)) : null),
        h("span", { onclick: (e) => e.stopPropagation() }, confirmBtn("Sil", () => api("/api/conv", { op: "delete_range", from: x.start, to: x.end }).then(() => loadList(body, true))))))))));
  } catch (e) { /* bağlantı geçici yoksa sonraki turda */ }
}
function openSession(body, x) { body._open = { from: x.start, to: x.end, live: x.live }; body._bar.style.display = "none"; delete sigs.convo; loadOpen(body, true); }
function backToList(body) { body._open = null; body._bar.style.display = ""; delete sigs.convs; loadList(body, true); }
async function loadOpen(body, force) {
  const o = body._open; if (!o) return;
  try {
    const r = await api("/api/conv?from=" + o.from + "&to=" + (o.live ? 9e12 : o.to)); if (!body._list.isConnected || body._open !== o) return;
    if (!r.items.length) return backToList(body);
    if (!force && !changed("convo", r.items)) return; sigs.convo = JSON.stringify(r.items);
    const first = new Date(r.items[0].ts * 1000), last = r.items[r.items.length - 1].ts;
    const head = h("div", { class: "opened" }, h("button", { class: "mini", onclick: () => backToList(body) }, "← Konuşmalar"),
      h("b", {}, dayLabel(isoDay(first)) + " · " + hm(r.items[0].ts) + (r.items.length > 1 ? " – " + hm(last) : "")), h("span", { class: "muted" }, r.items.length + " mesaj"), h("span", { class: "sp" }),
      confirmBtn("Bu sohbeti sil", () => api("/api/conv", { op: "delete_range", from: o.from, to: o.live ? 9e12 : o.to }).then(() => backToList(body))));
    const log = h("div", { class: "transcript" }, r.items.map((m) => h("div", { class: "msg " + (m.who === "sen" ? "me" : "ai") }, h("div", {}, ...hilite(m.text, convQuery)),
      h("small", {}, hm(m.ts) + " ", h("button", { class: "mini bad x", title: "Bu mesajı sil", onclick: () => api("/api/conv", { op: "delete", id: m.id }).then(() => loadOpen(body, true)) }, "×")))));
    const keep = body._list.scrollTop; fill(body._list, head, log); body._list.scrollTop = o.live && !force ? body._list.scrollHeight : keep || body._list.scrollHeight;
  } catch (e) { /* bağlantı geçici yoksa sonraki turda */ }
}
function hilite(text, q) {
  if (!q) return [text]; const lt = text.toLocaleLowerCase("tr"), lq = q.toLocaleLowerCase("tr"), out = []; let i = 0;
  for (let j; (j = lt.indexOf(lq, i)) >= 0; i = j + lq.length) { out.push(text.slice(i, j), h("mark", {}, text.slice(j, j + lq.length))); }
  out.push(text.slice(i)); return out;
}
/* --- Araçlar ve Beceriler --- */
VIEWS.araclar = {
  title: "ARAÇLAR VE BECERİLER",
  build(body) {
    const f = h("input", { placeholder: "Yeteneklerde ara…", maxlength: "60" }); body._f = f; body._t = h("span", { class: "muted" });
    body._c = h("div", { class: "scroll" }); f.oninput = () => { delete sigs.arac; if (S) VIEWS.araclar.update(S, body, "arac"); };
    fill(body, h("div", { class: "convbar" }, f, body._t), body._c);
  },
  update(s, body, key) {
    const all = s.araclar || [], q = body._f.value.trim().toLocaleLowerCase("tr");
    const items = all.filter((a) => !q || (a.name + " " + a.desc + " " + a.category).toLocaleLowerCase("tr").includes(q));
    if (!changed(key, [items, q])) return;
    body._t.textContent = items.length + " / " + all.length + " yetenek · bu oturumda " + all.reduce((n, a) => n + a.uses, 0) + " kez çalıştı";
    const cats = {}; items.forEach((a) => (cats[a.category] = cats[a.category] || []).push(a));
    fill(body._c, Object.keys(cats).length ? Object.keys(cats).sort().map((c) => h("div", { class: "daygrp" }, h("h5", {}, c, " ", h("span", { class: "muted" }, cats[c].length)),
      h("ul", { class: "rows tools", style: "height:auto" }, cats[c].map((a) => h("li", {}, SVG("tool"), h("div", {}, h("b", {}, h("code", {}, a.name)), h("small", { class: "wrapsm" }, a.desc || "—")),
        h("span", { class: "use" }, a.uses ? a.uses + "×" : "")))))) : h("div", { class: "empty" }, "Eşleşen yetenek yok."));
  },
};
VIEWS.ayarlar = {
  title: "AYARLAR",
  build(body) {
    const grid = h("div", { class: "themes" }, Object.entries(THEME_META).map(([id, [label, accent, bg]]) => {
      const b = h("button", { class: "tcard", "data-t": id, onclick: () => { applyTheme(id); api("/api/cmd", { theme: id }).catch(() => {}); markTheme(body); } },
        h("div", { class: "sw", style: "background:" + bg }, h("b", { style: "background:" + accent }), h("i", { style: "background:" + accent })), h("span", {}, label));
      return b; }));
    const quit = confirmBtn("Jarvis'i kapat", () => { api("/api/cmd", { id: "quit" }).catch(() => {}); toast("Jarvis kapanıyor…"); });
    body._c = h("div", { class: "scroll" },
      h("div", { class: "setgrp" }, h("h5", {}, "TEMA"), h("p", {}, "Seçtiğin tema kaydedilir ve bir sonraki açılışta da kalır."), grid),
      h("div", { class: "setgrp" }, h("h5", {}, "UYGULAMA"), h("p", {}, "Pencereyi kapatmak Jarvis'i kapatmaz; sesle çağırmaya devam edebilirsin. Panoyu tekrar açmak için menüden JARVIS simgesine tıkla. Tamamen kapatmak için:"), quit),
      h("div", { class: "setgrp" }, h("h5", {}, "HATA AYIKLAMA"), h("p", {}, "Kayıt dosyası: ", h("code", {}, "data/jarvis.log"), ". Terminalde görmek için simgeye sağ tıkla > “Hata ayıklama (terminalde)” ya da ", h("code", {}, "python main.py --wake --dash"), ".")));
    fill(body, body._c); markTheme(body);
  },
  update() {},
};
function markTheme(body) { body.querySelectorAll(".tcard").forEach((b) => b.classList.toggle("on", b.dataset.t === curTheme)); }
let view = "merkez", builtView = null;
function setQuery(q) { convQuery = q; $("#say").value = q; if (view !== "konusmalar") { view = "konusmalar"; showView(); } else if ($("#v-other")._body && $("#v-other")._body._load) $("#v-other")._body._load(true); }
function buildNav() {
  fill($("#nav"), NAV.map(([id, label, ic]) => h("button", { "data-v": id, class: /bilgi|akislar/.test(id) ? "soon" : "", onclick: () => { view = id; showView(); } }, SVG(ic), label, h("span", { class: "bd", id: "bd-" + id, hidden: "" }))));
}
function showView() {
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.v === view));
  const main = view === "merkez"; $("#v-merkez").hidden = !main; $("#v-other").hidden = main;
  if (main) { builtView = null; return; }
  const v = VIEWS[view], root = $("#v-other"); $("#otherTitle").textContent = v.title;
  const body = h("div", { class: "vbody" }); Object.keys(sigs).forEach((k) => { if (!k.startsWith("chat")) delete sigs[k]; });
  chats.length = 0; v.build(body, "v-" + view);
  fill($("#otherBody"), body); root._body = body; builtView = view; if (S) { v.update(S, body, "v-" + view); chats.forEach((c) => c.update(S)); }
}

/* ---------------- paneller ---------------- */
/* ---------------- paneller ---------------- */
const lvIcon = { UYARI: "warn", "BİLGİ": "info", "GÖREV": "list", KOMUT: "cmd" };
const PANELS = {
  durum(d) {
    if (!d) return;
    const online = !["stopped"].includes(d.state);
    const b = $("#sysBadge"); b.className = d.state === "stopped" ? "bad" : d.muted ? "warn" : "";
    fill(b, h("i"), d.state === "stopped" ? "KAPALI" : d.muted ? "SESSİZDE" : "ÇEVRİMİÇİ");
    $("#voiceState").textContent = d.label + "…"; $("#talkState").textContent = d.muted ? "Sessizde" : d.state === "listening" ? "Dinliyorum…" : d.label + "…";
    $("#focus").classList.toggle("on", d.focus); $("#pend").hidden = !d.pending;
    $("#bellN").hidden = !d.pending; document.body.dataset.state = d.state; void online;
  },
  core(s) {
    const m = s.model || {}, a = s.ajanlar || [], h2 = s.hafiza || {};
    const busy = a.filter((x) => /Çalışıyor|bekliyor/.test(x.status)).length, llm = (m.llm || []);
    const sys = s.sistem || {};
    fill($("#coreList"),
      row("cpu", "Yapay Zekâ Çekirdeği", (s.durum && s.durum.muted) ? "Sessizde" : "Aktif", "ok"),
      row("db", "Hafıza", (h2.count || 0) + " kayıt", "ok"),
      row("mic", "Ses", s.durum && s.durum.state === "stopped" ? "Kapalı" : "Çevrimiçi", "ok"),
      row("bot", "Ajanlar", busy ? busy + " çalışıyor" : "Hazır", "vio"),
      row("cpu", "Modeller", llm.filter((x) => x.installed !== false).length + " hazır", "ok"),
      row("shield", "Sistem", sys.cpu > 90 ? "Yüksek yük" : "Normal", sys.cpu > 90 ? "warn" : "ok"));
  },
  akis(items) {
    fill($("#feedList"), items && items.length ? items.map((i) => h("li", { class: i.level },
      SVG(lvIcon[i.level] || "info"), h("div", {}, h("b", {}, i.text), h("small", {}, i.time)), h("span", { class: "lv " + i.level }, i.level))) : h("li", {}, h("div", {}, h("b", {}, "Henüz bir olay yok"))));
    const bd = $("#bd-konusmalar"); void bd;
  },
  ajanlar(list_) {
    fill($("#agentGrid"), (list_ || []).map((a) => {
      const cls = a.status === "Yakında" ? "soon" : /Çalışıyor|bekliyor/.test(a.status) ? "warn" : /Kapalı/.test(a.status) ? "bad" : "ok";
      return h("div", { class: "ag " + (a.status === "Yakında" ? "soon" : "") }, SVG(a.name.includes("Tarayıcı") ? "globe" : a.name.includes("Takvim") ? "cal" : a.name.includes("Bilgisayar") ? "hw" : "bot"),
        h("div", {}, h("b", {}, a.name), h("small", { title: a.detail }, a.detail), h("em", { class: cls }, "● " + a.status)));
    }));
  },
  ajanda(a) {
    if (!a) return;
    const now = new Date(), nm = now.getHours() * 60 + now.getMinutes();
    const ev = a.events_today || [];
    const items = ev.map((e) => {
      const [hh, mm] = (e.time || "00:00").split(":").map(Number), diff = hh * 60 + mm - nm;
      const st = !e.time ? "Tüm gün" : e.past ? "Bitti" : diff < 60 ? diff + " dk sonra" : Math.floor(diff / 60) + " sa " + (diff % 60) + " dk";
      return h("li", { class: e.past ? "done" : "" }, h("span", { class: "t" }, e.time || "—"), h("span", { class: "n", style: "--w:" + (e.past ? 100 : 0) + "%" }, e.title), h("span", { class: "s" }, st));
    });
    const due = (a.tasks || []).filter((t) => t.overdue).slice(0, 2).map((t) => h("li", {}, h("span", { class: "t" }, "!"), h("span", { class: "n bad" }, t.title), h("span", { class: "s bad" }, "Gecikmiş")));
    fill($("#timeline"), items.concat(due).length ? items.concat(due) : h("li", {}, h("span", {}), h("span", { class: "empty" }, "Bugün için kayıtlı plan yok."), h("span")));
    const bd = $("#bd-gorevler"); bd.hidden = !a.open_tasks; bd.textContent = a.open_tasks;
  },
  sistem(s) {
    if (!s) return;
    const g = (lbl, pct, txt) => { const C = 2 * Math.PI * 30, p = Math.max(0, Math.min(100, pct));
      const el = h("div", { class: "g" + (p > 90 ? " crit" : p > 75 ? " hot" : "") });
      el.innerHTML = '<svg viewBox="0 0 72 72"><circle class="bg" cx="36" cy="36" r="30"/><circle class="fg" cx="36" cy="36" r="30" stroke-dasharray="' + C + '" stroke-dashoffset="' + (C * (1 - p / 100)) + '"/></svg>';
      el.appendChild(h("div", {}, h("small", {}, lbl), h("b", {}, txt))); return el; };
    fill($("#gauges"), g("CPU", s.cpu, s.cpu + "%"), g("RAM", 100 * s.ram.used / s.ram.total, Math.round(100 * s.ram.used / s.ram.total) + "%"), g("Disk", 100 * s.disk.used / s.disk.total, Math.round(100 * s.disk.used / s.disk.total) + "%"));
    const x = []; if (s.cpu_temp) x.push(h("span", {}, "CPU ", h("b", {}, Math.round(s.cpu_temp) + "°C")));
    if (s.gpu) x.push(h("span", {}, "GPU ", h("b", {}, s.gpu.util + "% · " + (s.gpu.used / 1024).toFixed(1) + "/" + Math.round(s.gpu.total / 1024) + " GB · " + s.gpu.temp + "°C")));
    fill($("#sysExtra"), x);
  },
  hafiza(m) {
    if (!m) return; const mo = S.model || {};
    fill($("#memStats"), h("div", {}, "Kayıtlı bilgi", h("b", {}, m.count)), h("div", {}, "Oturum turu", h("b", {}, m.turns)), h("div", {}, "Araç çağrısı", h("b", {}, mo.tool_calls || 0)));
    $("#memLast").textContent = m.last && m.last[0] ? "Son: " + m.last[0] : "Henüz kayıtlı bilgi yok.";
    drawMem(m.count);
    const bd = $("#bd-konusmalar"); const n = (S.durum && S.durum.turns || []).length; bd.hidden = !n; bd.textContent = n;
  },
  model(m) {
    if (!m) return;
    const tiles = m.llm.map((l) => h("div", { class: "lt " + (l.active ? "act on" : l.installed === false ? "off" : "on") }, h("b", {}, h("i"), l.name), h("small", {}, l.installed === false ? "Kurulu değil" : l.active ? "Aktif · " + l.role : l.role)))
      .concat([["Konuşma tanıma", m.stt], ["Ses motoru", m.tts], ["Uyanma", m.wake]].map(([t, v]) => h("div", { class: "lt on" }, h("b", {}, h("i"), t), h("small", {}, v))));
    fill($("#llmGrid"), tiles.slice(0, 6)); $("#llmCount").textContent = m.llm.filter((l) => l.installed !== false).length + " model hazır";
    const bd = $("#bd-araclar"); bd.hidden = false; bd.textContent = m.tools;
  },
  alt(a) {
    if (!a) return; $("#fCity").textContent = a.city; $("#fTemp").textContent = a.temp || "—";
    $("#fNet").textContent = a.online ? "Çevrimiçi" : "Çevrimdışı"; $("#fNet").className = a.online ? "ok" : "bad";
  },
};
const QUICK = [["brief", "Günün Özeti", "play"], ["tasks", "Görevlerim", "list"], ["today", "Bugünün Planı", "cal"], ["system", "Sistem Durumu", "hw"], ["weather", "Hava Durumu", "cloud"], ["battery", "Pil Durumu", "batt"], ["stop", "Sustur", "stop"], ["mute", "Mikrofon Aç/Kapat", "mic"]];
function buildQuick() { fill($("#quick"), QUICK.map(([id, l, ic]) => h("button", { onclick: () => send({ id }) }, SVG(ic), l))); }

function render(s) {
  S = s;
  if (s.durum && s.durum.theme && s.durum.theme !== curTheme) { applyTheme(s.durum.theme); if (builtView === "ayarlar") markTheme($("#v-other")._body); }
  PANELS.durum(s.durum); PANELS.core(s); PANELS.akis(s.akis); PANELS.ajanlar(s.ajanlar); PANELS.ajanda(s.ajanda);
  PANELS.sistem(s.sistem); PANELS.hafiza(s.hafiza); PANELS.model(s.model); PANELS.alt(s.alt);
  if (builtView) VIEWS[builtView].update(s, $("#v-other")._body, "v-" + builtView);
  chats.forEach((c) => c.el.isConnected && c.update(s));
}
async function poll() {
  try { render(await api("/api/state")); offline = 0; }
  catch (e) { if (++offline > 2) { const b = $("#sysBadge"); b.className = "bad"; fill(b, h("i"), "BAĞLANTI YOK"); } }
}

/* ---------------- saat, düğmeler ---------------- */
function tick() { const d = new Date(); $("#date").textContent = GUN[d.getDay()] + ", " + d.getDate() + " " + AY[d.getMonth()] + " " + d.getFullYear(); $("#time").textContent = p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds()); }
function wire() {
  $("#talk").onclick = () => send({ id: "talk" });
  $("#focus").onclick = () => send({ id: "focus" });
  document.querySelectorAll("[data-cmd]").forEach((b) => (b.onclick = () => send({ id: b.dataset.cmd })));
  let t = 0; const inp = $("#say");
  $("#sayForm").onsubmit = (e) => { e.preventDefault(); clearTimeout(t); setQuery(inp.value.trim()); };
  inp.oninput = () => { clearTimeout(t); t = setTimeout(() => { if (inp.value.trim() || convQuery) setQuery(inp.value.trim()); }, 300); };
}

/* ---------------- çizimler (süs; genlik gerçek duruma bağlı) ---------------- */
const amp = () => { const st = (S && S.durum && S.durum.state) || "starting"; return { speaking: 1, listening: .45, thinking: .7, muted: .08, stopped: .03 }[st] ?? .2; };
function waves() {
  const t = performance.now() / 1000;
  for (const id of ["wave", "wave2", "wave3"]) {
    const c = $("#" + id), x = c.getContext("2d"), w = c.width, hh = c.height, n = Math.floor(w / 4);
    x.clearRect(0, 0, w, hh); x.fillStyle = CY;
    for (let i = 0; i < n; i++) { const v = (Math.sin(t * 5 + i * .7) * .5 + .5) * (Math.sin(i * .35 + t) * .4 + .6), a = Math.max(.06, v * amp()), bar = a * hh;
      x.globalAlpha = .45 + a * .5; x.fillRect(i * 4, (hh - bar) / 2, 2, bar); }
  }
  for (const id of ["line1", "line2"]) {
    const c = $("#" + id), x = c.getContext("2d"), w = c.width = c.clientWidth || 200; x.clearRect(0, 0, w, 20);
    x.fillStyle = CY; for (let i = 0; i < w; i += 8) { x.globalAlpha = .2 + .3 * Math.abs(Math.sin(i / 25 + t * 2)); x.fillRect(i, 9, 2, 2); }
  }
}
const pts = []; (function () { let s = 7; const r = () => (s = (s * 16807) % 2147483647) / 2147483647; for (let i = 0; i < 40; i++) pts.push([r(), r()]); })();
function drawMem(count) {
  const c = $("#mem"), x = c.getContext("2d"), w = c.width = c.clientWidth || 260, hh = c.height = 96; x.clearRect(0, 0, w, hh);
  const n = Math.min(pts.length, Math.max(count ? 3 : 0, Math.round(Math.log2(count + 1) * 4)));
  x.strokeStyle = "rgba(" + ACC + ",.35)"; x.lineWidth = 1; x.beginPath();
  for (let i = 1; i < n; i++) { const a = pts[i], b = pts[i - 1]; x.moveTo(a[0] * w, a[1] * hh); x.lineTo(b[0] * w, b[1] * hh); } x.stroke();
  x.fillStyle = CY2; for (let i = 0; i < n; i++) { x.beginPath(); x.arc(pts[i][0] * w, pts[i][1] * hh, i % 5 ? 2 : 3.2, 0, 7); x.fill(); }
}
/* orb: dönen tel kafes küre + halkalar + parçacıklar */
const orb = { c: null, x: null, P: [] };
function orbInit() {
  orb.c = $("#orb"); orb.x = orb.c.getContext("2d");
  let s = 3; const r = () => (s = (s * 48271) % 2147483647) / 2147483647;
  for (let i = 0; i < 260; i++) { const u = r() * 2 - 1, th = r() * 6.2832, q = Math.sqrt(1 - u * u); orb.P.push([q * Math.cos(th), u, q * Math.sin(th)]); }
}
function orbDraw() {
  const c = orb.c, x = orb.x, W = c.width = c.clientWidth, H = c.height = c.clientHeight; if (!W) return;
  const t = performance.now() / 1000, cx = W / 2, cy = H * .5, R = Math.min(W, H) * .34, a = amp();
  x.clearRect(0, 0, W, H);
  const g = x.createRadialGradient(cx, cy, R * .1, cx, cy, R * 1.25); g.addColorStop(0, "rgba(" + ACC + "," + (.10 + .1 * a) + ")"); g.addColorStop(.7, "rgba(20,110,200,.12)"); g.addColorStop(1, "rgba(0,0,0,0)");
  x.fillStyle = g; x.beginPath(); x.arc(cx, cy, R * 1.25, 0, 7); x.fill();
  x.strokeStyle = "rgba(" + ACC + ",.5)"; x.lineWidth = 1; x.beginPath(); x.arc(cx, cy, R, 0, 7); x.stroke();
  const ry = t * .25, cs = Math.cos(ry), sn = Math.sin(ry), pr = [];
  for (const p of orb.P) { const X = p[0] * cs + p[2] * sn, Z = -p[0] * sn + p[2] * cs; pr.push([cx + X * R, cy + p[1] * R, Z]); }
  x.lineWidth = .6;
  for (let i = 0; i < pr.length; i++) for (let j = i + 1; j < pr.length; j += 7) {
    const dx = pr[i][0] - pr[j][0], dy = pr[i][1] - pr[j][1], d = dx * dx + dy * dy;
    if (d < R * R * .035) { x.strokeStyle = "rgba(" + ACC + "," + (.18 + .14 * (pr[i][2] + 1) / 2) + ")"; x.beginPath(); x.moveTo(pr[i][0], pr[i][1]); x.lineTo(pr[j][0], pr[j][1]); x.stroke(); }
  }
  for (const p of pr) { x.fillStyle = "rgba(" + ACC + "," + (.35 + .5 * (p[2] + 1) / 2) + ")"; x.beginPath(); x.arc(p[0], p[1], 1 + (p[2] + 1) * .8, 0, 7); x.fill(); }
  for (let k = 0; k < 3; k++) { x.save(); x.translate(cx, cy); x.rotate(-.5 + k * .55 + t * .05); x.scale(1, .24 + k * .04); x.strokeStyle = "rgba(" + ACC + "," + (.22 + .15 * a) + ")"; x.lineWidth = 1.2;
    x.beginPath(); x.arc(0, 0, R * (1.25 + k * .22 + .03 * Math.sin(t * 2 + k) * a), 0, 7); x.stroke(); x.restore(); }
  x.strokeStyle = "rgba(" + ACC + ",.28)"; for (let k = 0; k < 5; k++) { x.beginPath(); x.ellipse(cx, cy + R * 1.12, R * (.55 + k * .2), R * (.07 + k * .02), 0, 0, 7); x.stroke(); }
}
function frame() { waves(); orbDraw(); requestAnimationFrame(frame); }

wire(); buildNav(); buildQuick(); showView(); orbInit(); tick(); setInterval(tick, 1000); poll(); setInterval(poll, 1500); frame();
