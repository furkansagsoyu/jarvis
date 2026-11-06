# JARVIS — Devir Teslim Dokümanı (Claude Code için)

Bu belge projenin mimarisini, alınan kararları, gelinen noktayı ve geçmişini Claude Code'a aktarır. Okuyan: **sen, Claude Code**. Sahip: **Furkan** (aşağıda "kullanıcı"). Kurallar `CLAUDE.md`'de, görev sırası `TASKS.md`'de.
Belge ile kod çelişirse **kod haklıdır**; çelişkiyi bu dosyada düzelt. Son güncelleme: **2026-11-06** (son commit öncesi `acb02aa`, `check_all.py --quick` 45 OK).

---

## 1. Proje ve kullanıcı

**Ürün:** Tamamen yerel/ücretsiz, **Türkçe** konuşan J.A.R.V.I.S. tarzı sesli bilgisayar asistanı ve ajanı. Ses, metin ve görüntü makineden çıkmaz (istisna: web araması, Telegram, kullanıcının açtırdığı siteler ve gizlilik kapısından geçen ücretsiz bulut LLM çağrıları). Asistanın yeniden adlandırılması planlandı (`TASKS.md` bölüm 7).

**Kullanıcı:** Furkan Sağsoyu, Tokat; mühendislik 4. sınıf öğrencisi (Gaziosmanpaşa Üniversitesi). Türkçe konuşur. Yazılım kariyeri hedefliyor; proje portföy/bitirme niteliğinde. Claude Code'u **Claude masaüstü uygulamasından (Code sekmesi)** kullanıyor (Ortam = Yerel, klasör `~/jarvis`); terminal `claude` ya da VS Code eklentisi kullanmıyor.

**Makine:** MSI dizüstü, Linux Mint Cinnamon / **X11**, RTX 3070 Ti **8 GB VRAM**, **15,3 GB RAM + 4 GB swap**. Python: conda env `freya`. Telefon: Xiaomi Redmi Note 14 Pro+ 5G (Android).

**Repo:** `github.com/furkansagsoyu/jarvis` — **PUBLIC**, tek dal `main`, çalışma kopyası `~/jarvis`. Etiketler `v2za … v2zi` (hepsi push'lu; sıradaki `v2zj`) ve `webcam-gorusu`.

---

## 2. Değişmez kurallar (kullanıcının kararları)

1. **Gizlilik:** Ücretsiz bulut modelleri yalnızca kişisel veri olmadan kullanılır. Hafıza, konuşma kaydı, ekran, kamera, rehber, takvim, dosya içeriği **asla** buluta gitmez. Kapı: `core/privacy.py`.
2. **Sırlar:** Anahtarlar kullanıcı tarafından `data/` altına konur (`data/keys.env`, `data/fcm_service_account.json`…); sohbette/komutta/commit'te görünmez. `google-services.json` eski geçmişte duruyor; Firebase anahtarı Google Cloud'da `com.furkan.jarvisphone` + SHA-1 ile kısıtlandı.
3. **Kod ajanı yalnızca `workspace/` içinde** (bubblewrap, internetsiz).
4. **Onay kapıları** (`skills/_confirm.py`) kodda zorlanır; model onay veremez; uzaktan kip (Telegram/telefon) bilgisayarda bekleyen onayı/planı cevaplayamaz.
5. Dış içerikten (dosya, web, ekran, kamera) sonraki turda araç listesi **boştur**.
6. **Sipariş** (Getir/Yemeksepeti/Trendyol GO) **iptal** (2026-10-26). Yeniden açılırsa: kullanıcı kendi giriş yapar, ajan sepeti kurar, **ödemeden önce durur**, parola/kart saklanmaz.
7. Başka projelerin (ör. `louis-cfm/coucou`, Mark-LV) kodu/görselleri kopyalanmaz; yalnızca fikir alınır.

---

## 3. Mimari

```
"Hey Jarvis" ─► voice/wake.py (openWakeWord) ─► voice/stt.py (faster-whisper large-v3-turbo)
      ─► core/brain.py ─► [hızlı kural yolu]  ya da  [Ollama gemma4:e4b, araç çağırma]
      ─► skills/*  ─► voice/tts.py (EMA Lightning, CPU) ─► hoparlör
```

| Katman | Dosya(lar) | Not |
|---|---|---|
| Giriş noktası | `main.py` | Bayraklar: `--wake --text --ui --dash --island --telegram --morning --fresh --mic --speaker --tts --tts-device --wake-threshold --stt-prompt --list-speakers`. Otomatik başlatma `~/.config/autostart/jarvis.desktop` → `main.py --wake --dash --island --morning --telegram`; menü başlatıcısı `app.py` → `--wake --dash --island --morning`. Eski durum penceresi `--ui` otomatik başlatmada yok. |
| Beyin | `core/brain.py` | `MODEL="gemma4:e4b"`, yedek `qwen3:8b` (`JARVIS_FALLBACK_MODELS`). `think=False` her çağrıda. `MAX_HISTORY=16`, `MAX_TOOL_ROUNDS=3`. `_remote_block`: uzaktan turda yalnız o turda oluşan onay cevaplanır. |
| Hızlı yol | `core/brain.py: _fast_route`, `_browser_route` | Regex (`WORD_*`) ile kural tabanlı yönlendirme; zamanlama kuralları hava/saatten önce. |
| Yetenekler | `skills/*.py` | Bkz. 4. |
| Ajan modu | `core/agent.py` | Tek cümleden plan, adım adım yürütme (max 8 adım), `ALLOWED/NETWORK/HELP`. |
| Ekip modu | `core/team.py` | Planlayıcı (`proje:`/`mimar:` kipinde önce Mimar, ≤4 parça) → Araştırma / Dosya / Kod → Denetçi (`denetimsiz` ile kapatılır) → Yazar. |
| Zamanlayıcı | `core/scheduler.py`, `skills/schedule.py` | Türkçe zaman ifadeleri; 20 sn döngü; kısıtlı kipte gözetimsiz çalışır. |
| Yönlendirici | `core/router.py`, `core/privacy.py` | Ücretsiz bulut (Groq vb., OpenAI uyumlu; `data/models.json`) + gizlilik kapısı. |
| MCP | `core/mcp_client.py`, `skills/mcp.py` | Yalnız `data/mcp.json`'daki yerel stdio sunucular; gizli, onaylı, uzaktan kapalı. |
| Bellek koruması | `core/memguard.py`, `tools/ram_report.py` | RAM/PSI izleme, ağır işi başlatmama. |
| Pano | `dashboard/server.py` (127.0.0.1, `JARVIS_DASH_PORT`), `dashboard/state.py`, `dashboard/window.py` (Qt/QtWebEngine + tepsi → pywebview → Chromium `--app`), `dashboard/static/` | `/api/state`, `/api/cmd`, `/api/agenda`, `/api/conv`, `/api/sessions`; mobil `/m`, `/api/m/{state,chat,voice,cmd,agenda}`. |
| Ada / durum | `desktop/island.py` (`-m desktop.island`), `desktop/ui_state.py`, `desktop/ui.py` | Qt üst kenar adası: Evet/Hayır onayı, Çekirdek maskotu, etkin hal, otomatik gizlenme, Ayarlar > ADA. |
| Uzaktan | `connect/telegram_bot.py`, `connect/remote.py`, `connect/remote_setup.py` | Telegram (kısıtlı kip) ve telefon web arayüzü (Tailscale serve; Funnel açıksa kurulum reddedilir). |
| Telefon | `connect/phonelink.py`, `skills/phone.py`, `phone_app/` | ADB (USB/Wi-Fi) + FCM imzalı komut; Flutter + Kotlin (`com.furkan.jarvisphone`). |
| Masaüstü kurulum | `app.py`, `tools/install_app.py`, `tools/autostart.py` | Menü simgesi, terminalsiz başlatma, tek örnek kilidi (`fcntl`). |

### 3.1 Veri
Tüm kalıcı veri `data/` altında (`JARVIS_DATA` ile değişir; testler geçici klasör kullanır). Dosyalar 0600, klasör 0700. Erişim `skills/_store.py` üzerinden. Bilinen dosyalar: `schedules.json, mcp.json, memory.db (FTS5; eski memory.json → .bak), reminders.json, agenda.json, contacts.json, settings.json (island ayarları dahil), status.json, control.json, dashboard.json, briefing.json, router_stats.json, models.json, phone.json, phone_push.json, remote.json, secret.json, session.json, telegram.json, browser_sites.json, conversations.jsonl, team_runs.jsonl, keys.env, fcm_service_account.json, browser_profile/, ram_watch.csv`. Kilit/pid dosyaları `$XDG_RUNTIME_DIR` altında.

### 3.2 Model ve donanım gerçekleri (ölçüldü, `RAM.md`)
- Sesli sohbette VRAM **6,8/8 GB**. Gemma+Whisper+TTS birlikte rahat; ek büyük model VRAM'i aşar.
- `qwen3:8b` yedek: Jarvis açıkken %21/%79 CPU/GPU. **`gpt-oss:20b` reddedildi** (karar 2,3 sn, ilk parça 3,7 sn).
- Ollama: `OLLAMA_MAX_LOADED_MODELS=1, NUM_PARALLEL=1, FLASH_ATTENTION=1, KV_CACHE_TYPE=q8_0`; earlyoom `-m 5 -s 10`. İsteğe bağlı: `vm.swappiness=10`.
- Gradle daemon'ları `./gradlew --stop` yapılmazsa bellekte kalır. `ram_report.py --watch` **saniye** alır.
- Ücretsiz bulut girdi sınırı ≈ **5000 jeton** (Groq ~8K/dk): büyük girdi gönderilmeden reddedilir; 429'da sıradaki modele geçilir.
- Ada süreci ~%2,4 tek çekirdek (maskot animasyonu, 15 kare/sn).

---

## 4. Kod yapısı

### 4.1 Yetenek ekleme
`skills/` altında `_` ile başlamayan her `.py` otomatik yüklenir; `SKILLS = [{"name", "description", "parameters", "run", "hidden"?}]`, `run(**kwargs) -> str`. `description`'ın **ilk cümlesi** sistem prompt'una ve pano Araçlar sayfasına girer (Türkçe ad: `dashboard/state.TOOL_LABELS`).
- Varsayılan: `hidden` + hızlı yol kuralı. Sonra sırayla: (a) `REMOTE_BLOCKED`, (b) `ACTION_CLAIM`, (c) `core/agent.py ALLOWED/NETWORK/HELP`, (d) onay (`_confirm.request`), (e) `tests/test_routes.py` + yetenek testi.
- Riskli işlem deseni: araç işi yapmaz, `confirm.request(açıklama, run)` ile bekleyen işlem kaydeder; sonraki cümle modele gitmeden evet/hayır sınıflanır; 60 sn sonra düşer. Testte kalıntı: `confirm.cancel()`.

### 4.2 Yetenek dosyaları
`agenda` (`_trdate.py` Türkçe tarih), `apps`, `battery`, `briefing`, `brightness`, `browser` (Playwright, ayrı profil, izin listesi, `browser_play`), `camera`, `clock`, `codeagent`, `desktop_input` (yasaklı yüzeyler), `files` (çöpe at + geri al), `hardware`, `help`, `maintenance` (kural tabanlı, düzeltmeler onaylı), `mcp`, `memory` (FTS5), `phone`, `reminders`, `schedule`, `screen`, `undo`, `volume`, `weather`, `web`. Yardımcılar: `_confirm, _phonenotify, _store, _trdate, _undo`.

### 4.3 Önemli ayrıntılar
- **`browser_play`**: `parse_play(text)` → sorgu ya da `None`; YouTube arama → ilk video → `video.play()`; tarayıcıyı kapatmaz; `--autoplay-policy=no-user-gesture-required`. `core/agent.py` `CLOSE_WANTED = r"kapat(?!ma)"`.
- **Kod ajanı**: `code_run(command, stdin="")` (≤2000 karakter); `core/team.py` tolerant `parse_json` + `_fix_escapes`, art arda 3 bozuk JSON'da bırakır; `speakable` kelime içi alt çizgiyi korur.
- **Zamanlanmış görevler**: `main.run_scheduled` kullanıcının cümlesini `run_remote` ile kısıtlı kipte çalıştırır; bilgisayarda onay bekliyorsa ertelenir; sonuç `notify` (odak modunda yalnız pano, Telegram açıksa telefon). Ajan/ekip/kod/MCP zamanlanamaz. Gerçek saatle beklenerek denenmedi (sahte saatle test edildi).
- **Maskot "Çekirdek"**: `assets/cekirdek.svg`, panoda satır içi (DOMParser), kök `data-state` `idle|listening|thinking|speaking|alert|error`; eşleme `ui_state.mascot_state` (hata > onay/plan > recording/thinking/speaking > idle); `ui_state.flag_error()` 8 sn. Adada Qt CSS animasyonu çalışmadığı için `island.mascot_svg(state, t, since)` kareyi aynı süre/değerlerle hesaplar; `JARVIS_REDUCED_MOTION=1` → durağan.
- **Ada**: etkin halde 250 px'e büyür (`QPropertyAnimation` 320 ms); `island.should_show` + `HIDE_AFTER=6` sn otomatik gizlenme (Cinnamon pencereyi ekran üstüne çıkarmadığı için içteki hap kaydırılır); ayarlar `ui_state.island_settings/set_island` (enabled, on_top, mascot, position, size, theme, autohide), pano `/api/cmd {"island": {key, value}}`, tepsi "Adayı aç".

### 4.4 Kod stili
Python 3, tip ipuçları, ruff. Docstring/yorum Türkçe. `eval/exec/os.system/shell=True/pickle` yok, TLS doğrulaması kapatılmaz (`tests/test_security.py` AST ile tarar; `workspace/` hariç). Alt süreçler liste biçiminde.

---

## 5. Test ve doğrulama

| Komut | Ne yapar |
|---|---|
| `python check_all.py --quick` | Modelsiz mantık testleri. **Son durum: 45 OK, 0 hata (~27 sn).** |
| `python check_all.py` | + ortam kontrolü |
| `python check_all.py --model` | + gerçek model araç seçimi (`tools/tool_check.py`; son: 102/102) |
| `python check_all.py --vision` | + gerçek ekran görüşü |
| `python tests/test_<ad>.py` | Tek modül (agenda, agent, app, browser, code, dashboard, desktop, island, maintenance, mascot, mcp, memory, mobile, phone, phonelink, ram, router, routes, schedule, security, team, web, window) |
| `python tools/code_check.py` · `router_check.py` · `phone_check.py` · `ram_report.py` | Kod kutusu · anahtar + gizlilik · telefon/ADB/FCM · bellek |

Testler `JARVIS_DATA`'yı geçici klasöre yönlendirir, `ollama` yoksa sahtesini koyar. Claude Code makinede çalıştığı için `--model`, `--vision`, `ram_report`, `ollama ps`, `nvidia-smi`, Qt ekran görüntüsü kendisi alabilir. Yapamadıkları (HW): mikrofon/wake word duyumu, hoparlör, telefon bildirimi, Flutter'ı telefonda denemek.

`.claude/settings.json` izin listesini ve `data/**`, `*.env`, `fcm_service_account.json`, `google-services.json` okuma yasağını tanımlar (doğrulandı: `data/` okuması reddediliyor).

---

## 6. Kararlar ve nedenleri

| Karar | Neden |
|---|---|
| v1 silindi, tek dal `main`, klasör `~/jarvis` | v2 v1'in üst kümesiydi. |
| Ücretsiz bulut yalnız kişisel veri yokken | Gizlilik > güç. |
| Yetenekleri modelden saklamak (hidden) | Araç sayısı arttıkça Gemma araç seçimi bozuluyor. |
| Onay ve yasaklı yüzeyler **kodda**; uzaktan kip yerel onaya dokunamaz | Güvenlik modelin iyi niyetine bırakılmaz (güvenlik taraması YÜKSEK bulgusu). |
| Kod ajanı bubblewrap + workspace; sınırlar `MAX_CALLS 30`, `max_rounds 14`, `max_tokens 1800`, `VIEW_BUDGET 9000` karakter, `MAX_STDIN 2000` | İnternetsiz, ev klasörü görünmez; bulutun ~5K jeton sınırı. Büyük projeler için Claude Code. |
| `gpt-oss:20b` reddedildi | Gecikme ve VRAM. |
| Maskot "Çekirdek" (özgün SVG) | Kullanıcı seçti; başka projeden görsel yok. |
| Ada: Qt overlay (Cinnamon applet/desklet değil) | Taşınabilir, `_confirm`'e doğrudan bağlanır. |
| Klasör düzeni: kökte yalnız giriş noktaları + paketler (2026-10-26) | Kökteki 53 dosya okunmuyordu. |
| Eski durum penceresi (`--ui`) otomatik başlatmadan çıktı; yerine `--dash` | Kullanıcı isteği; pano + ada yeterli. |
| Zamanlanmış görevde ajan/ekip/kod/MCP yok | Gözetimsiz onay olmaz. |
| Sipariş özelliği iptal (2026-10-26) | Kullanıcı kararı. Keşif: Yemeksepeti bot doğrulamasıyla engelliyor; Getir ve Trendyol GO açılıyor. |
| Windows: planlı, başlanmadı | Arkadaşlar Win11 kullanıyor; `TASKS.md` bölüm 6. |

---

## 7. Çalışma düzeni
Kurallar `CLAUDE.md`'de. Özet: `TASKS.md` sırasıyla, sormadan; [YAZILIM] → test yeşil → commit → push → sıradaki; [HW] → commit, tek satır deneme talimatı, "çalışıyor" gelince push; [SOR] → `AskUserQuestion`. Push öncesi sır taraması. Ölçmeden "hızlandı/küçüldü" denmez; kök neden düzeltilir. Biten işin ayrıntısı bu dosyanın 10. bölümüne eklenir.

---

## 8. Yol haritası
Ayrıntılı ve güncel sıra `TASKS.md`'de. Sıradaki büyük işler: **Windows taşıma** (`platform_compat.py`; `pycaw`, `pyautogui`, `mss`, `psutil`; `kur.bat`/`install.ps1`; hafif profil; Windows'ta kod ajanı kapalı), **ders reposu iş akışı** (Issue → Branch → PR), **asistanın yeniden adlandırılması**, anlamsal hafıza (yerel gömme), Google Takvim, ntfy, ders/Git ajanı, kod ajanında "kendi projem" kipi.

Piyasa karşılaştırmasından kalan eksikler: e-posta/takvim entegrasyonu, OCR/erişilebilirlik tabanlı tıklama, paylaşılabilir yetenek paketleme.

---

## 9. Açık / doğrulanmamış noktalar
- Kod ajanının ilk başarısız çalışmasındaki ham geçersiz JSON görülmedi (loglama var; `[ekip]` loglarına bak).
- Ekip rolleri bulut yolunda denenmedi (anahtar geçici klasöre bağlanamadı).
- Zamanlanmış görevler gerçek saatle beklenerek denenmedi.
- Qwen 3.5 9B araç çağırma ölçülmedi. Flutter derlemesindeki RAM tepesi yakalanmadı (gereksiz bulundu).

---

## 10. Geçmiş (tamamlanan işler)

- **Ajan serisi:** 55ad3a3 Denetçi · 352b96b Mimar · cfd6130 Sistem bakım (`skills/maintenance.py`, kural tabanlı, düzeltmeler onaylı) · 51aee19/07633a1 gerçek model denemesi: `--model` 102/102; ekip rolleri gemma4:e4b ile 9+ tur; düzeltilenler: code_run sarmalayıcısı bus'a ulaşamıyordu, yanlış parametre adı, JSON yazım hataları (geçersiz %20 → %1,1), tekrar/yeniden yazma döngüleri.
- **Hafıza/entegrasyon:** 3b74312 SQLite FTS5 hafıza (Türkçe arama + bm25) · 6cc4ecc/e7d947d MCP istemcisi (`mcp-server-time` ile çalıştı; JSON sonuç sesli cümleye çevrilir; kurulum README "MCP araçları").
- **Qt ada:** d92f190 (HW 54a84bd; otomatik başlatmada 7372d2a).
- **2026-10-26 Güvenlik taraması (c509f33):**
  - YÜKSEK — uzaktan onay atlatma: bilgisayarda bekleyen onay ve ajan/ekip planı Telegram/telefondan "evet/başla" ile çalıştırılabiliyordu → `Brain._remote_block`.
  - ORTA — `find_files` (yol sızıntısı) ve `forget` (onaysız silme) uzaktan açıktı → `REMOTE_BLOCKED`.
  - DÜŞÜK — ASCII dışı `X-Token` `hmac.compare_digest` TypeError → bayt karşılaştırması, 403.
  - BİLGİ: izlenen dosyalarda ve git geçmişinde gerçek sır yok (tek kayıt kısıtlı Firebase anahtarı). Alt süreçler liste biçiminde; `adb shell` numarası temizleniyor; log'larda anahtar/URL yok; pano statik yol kaçışı engelli, özel başlık (CSRF yok), Host denetimi; MCP ortamı temiz, her çağrı onaylı.
- **2026-10-26 Temizlik (ce95410, kullanıcı onayıyla):** boş `Sesi`, `q`; kökteki kopya `help.py`; `voices/` (63 MB Piper); `out/`, `out_freya/`; `tool_diag2.py`, `stt_test.py`, `tts_compare.py`, `web_check.py`. Korunanlar: `tool_diag.py`, `model_bench.py`, `*_check.py`, `browser_sites.py`. Ölü fonksiyon ve kullanılmayan bağımlılık yok.
- **2026-10-26 UI gözden geçirme (b64af9c, HW onaylı):** Ajanlar kartı kesilmesi (kaydırma + 2 sütun), ~1000 px'te kesilen metinler, tekrar eden açıklamalar, Türkçe sayı biçimi (%12, 0,0/8 GB); "Bilgi Tabanı"/"İş Akışları" gizlendi; "Yapay Zekâ Çekirdeği"; Araçlar sayfası Türkçe ad; `--ui` otomatik başlatmadan çıktı.
- **2026-10-26 Maskot (93c3389, bda73c7, HW onaylı):** SVG gömülmeye uygun hale getirildi (`svg.cekirdek` kapsamı, `ck-` önekleri, `--ck-tema`); yeni `recording` durumu; ada kare kare animasyon (~%2,4 tek çekirdek), maskot 34 px. `cekirdek_demo.html` değiştirilmedi.
- **2026-10-26 Otomatik başlatma panoyu açar (da03d17):** check_all eksik `--dash`'i uyarır.
- **2026-10-26 Ada etkin hali (6c15a1d, HW onaylı):** Hey Jarvis'te büyür, maskot 76 px ortada; OutBack/OutCubic geçiş; yoklama 300 ms; küçülürken düzen önbelleği hatası düzeltildi.
- **2026-10-26 Ayarlar > ADA (d85a97c, HW onaylı):** tema/üstte/maskot/konum/boyut/aç-kapa, yeniden başlatmadan uygulanır; tepsi "Adayı aç".
- **2026-10-26 Ada otomatik gizlenme (0b569d5, HW onaylı):** 6 sn sonra üst kenara kayıp saklanır, Hey Jarvis'te kayarak gelir (gelişte 420 ms OutBack, gidişte 360 ms InCubic).
- **2026-10-26 Sipariş iptali + README teşekkür/bileşen tablosu (db3788b).**
- **2026-10-26 Klasör düzeni (2be00ce, HW onaylı 06dad1e):** kökteki 53 .py paketlere (`git mv`), her klasöre README, ana README 311 → 111 satır; `.claude/settings.json` izin yolları güncellendi.
- **2026-10-26 Zamanlanmış görevler (acb02aa):** `core/scheduler.py` (her gün/sabah/akşam/gece/öğlen, hafta içi/sonu, gün adı, saat[:dk]; 10 dk pencere; günde bir; başarısızsa yeniden dener), `skills/schedule.py` (gizli, kurma onaylı, uzaktan kapalı), pano > Görevler liste + sil, `tests/test_schedule.py`.
- **2026-11-06 Belgeler:** CLAUDE.md yalnızca kurallar + yapı; geçmiş ve kararlar bu dosyaya, TASKS.md yalnızca görev sırası.
