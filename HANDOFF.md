# JARVIS — Devir Teslim Dokümanı (Claude Code için)

Bu belge, projenin önceki geliştirme sohbetinde (claude.ai, Claude Sonnet 5.5 ile) alınan kararları, mimariyi, kod yapısını ve gelinen noktayı Claude Code'a aktarır. Okuyan: **sen, Claude Code**. Sahip: **Furkan** (aşağıda "kullanıcı").
Bu belgedeki her teknik iddia kod tabanından doğrulanmıştır; yine de değiştirmeden önce ilgili dosyayı oku. Belge ile kod çelişirse **kod haklıdır**; çelişkiyi bu dosyada düzelt.

---

## 1. Proje ve kullanıcı

**Ürün:** Tamamen yerel/ücretsiz, **Türkçe** konuşan J.A.R.V.I.S. tarzı sesli bilgisayar asistanı ve ajanı. Ses, metin ve görüntü makineden çıkmaz (istisna: web araması, Telegram, kullanıcının açtırdığı siteler, ve gizlilik kapısından geçen ücretsiz bulut LLM çağrıları).

**Kullanıcı:** Furkan Sağsoyu, Tokat; mühendislik 4. sınıf öğrencisi (Gaziosmanpaşa Üniversitesi). Türkçe konuşur; **tüm arayüz metinleri, sesli cevaplar, yorumlar ve commit dışı yazışma Türkçe** olmalı. Yazılım kariyeri hedefliyor; bu proje portföy/bitirme niteliğinde.

**Makine (hedef platform):** MSI dizüstü, Linux Mint Cinnamon / **X11**, RTX 3070 Ti **8 GB VRAM**, **15,3 GB RAM + 4 GB swap dosyası**. Python ortamı: conda env `freya` (`/home/furkan/miniconda3/envs/freya/bin/python`). Telefon: Xiaomi Redmi Note 14 Pro+ 5G (Android).

**Repo:** `github.com/furkansagsoyu/jarvis` — **PUBLIC**, tek dal `main`. Kullanıcının çalışma kopyası `~/jarvis`. Etiket şeması `v2za … v2zi` (sıradaki `v2zj`); `v2zi`'nin push edilip edilmediği doğrulanmadı → ilk iş `git tag -l` ve `git log --oneline -5` ile bak.

---

## 2. Değişmez kurallar (kullanıcının kararları)

1. **Gizlilik:** Ücretsiz bulut modelleri yalnızca kişisel veri olmadan kullanılabilir. Hafıza, konuşma kaydı, ekran, kamera, rehber, takvim, dosya içeriği **asla** buluta gitmez. Kapı: `privacy.py`.
2. **Sırlar:** API anahtarları/sırlar kullanıcı tarafından `data/` altındaki dosyalara konur (`data/keys.env`, `data/fcm_service_account.json`…). **Asla sohbette/komutta/commit'te** görünmez. Repo public: `data/`, `*.env`, `keys.env`, `fcm_service_account.json`, `phone_app/android/app/google-services.json`, `workspace/`, `*.zip` `.gitignore`'dadır; **bunları asla `git add -f` yapma.** (`google-services.json` eski geçmişte duruyor; Firebase API anahtarı Google Cloud'da `com.furkan.jarvisphone` paketi + SHA-1 ile kısıtlandı.)
3. **Sipariş (Getir / Yemeksepeti / Trendyol GO):** kullanıcı kendi giriş yapar; ajan sepeti kurar ve **ödemeden önce DURUR**. Parola/kart saklanmaz. Hangi site(ler)in öncelikli olduğu henüz **cevaplanmadı**.
4. **Kod ajanı yalnızca `workspace/` içinde** çalışır (bubblewrap kutusu, internet yok).
5. **Onay kapıları** (`skills/_confirm.py`) hassas işlemlerde kalır; modelin "onayladım" demesi/onay vermesi mümkün olmamalı. Bu kapıları gevşeten hiçbir değişiklik yapma.
6. Model, dış içerikten (dosya, web, ekran, kamera) gelen talimatlara uymaz: o turdan sonra araç listesi **boştur**.

---

## 3. Mimari

```
"Hey Jarvis" ─► wake.py (openWakeWord) ─► stt.py (faster-whisper large-v3-turbo)
      ─► brain.py ─► [hızlı kural yolu]  ya da  [Ollama gemma4:e4b, araç çağırma]
      ─► skills/*  ─► tts.py (EMA Lightning, CPU) ─► hoparlör
```

| Katman | Dosya(lar) | Not |
|---|---|---|
| Giriş noktası | `main.py` | Bayraklar: `--wake --text --ui --dash --island --telegram --morning --fresh --mic --speaker --tts --tts-device --wake-threshold --stt-prompt --list-speakers`. Otomatik başlatma: `~/.config/autostart/jarvis.desktop` → `main.py --wake --island --morning --telegram` (eski durum penceresi `--ui` 2026-10-26 kullanıcı isteğiyle çıkarıldı; menü başlatıcısı `app.py`: `--wake --dash --island --morning`). |
| Beyin | `brain.py` | `MODEL="gemma4:e4b"`, yedek `qwen3:8b` (`JARVIS_FALLBACK_MODELS`). **`think=False` her çağrıda gönderilir.** `MAX_HISTORY=16`, `MAX_TOOL_ROUNDS=3`. |
| Hızlı yol | `brain.py: _fast_route`, `_browser_route` | Regex (`WORD_*`) ile kural tabanlı yönlendirme. Sık/kalıbı belli işler modele hiç sorulmaz. |
| Yetenekler | `skills/*.py` | Yeni dosya = yeni yetenek (aşağıda 4). |
| Ajan modu | `agent.py` | Tek cümleden plan, adım adım yürütme. `ALLOWED/NETWORK/HELP` kümeleri. Max 8 adım. |
| Ekip modu | `team.py` | Planlayıcı → Araştırma / Dosya / Kod → Yazar. |
| Yönlendirici | `router.py`, `privacy.py` | Ücretsiz bulut (Groq vb., OpenAI uyumlu; `data/models.json` ile sağlayıcı eklenir) + gizlilik kapısı. |
| Bellek koruması | `memguard.py`, `ram_report.py` | RAM/PSI izleme, ağır işi başlatmama. |
| Pano / pencere | `dashboard/server.py` (127.0.0.1, `JARVIS_DASH_PORT`), `dashboard/window.py` (öncelik: Qt/QtWebEngine penceresi + tepsi simgesi [`pywebview[qt]` ile gelen qtpy] → pywebview → Chromium `--app`), `dashboard/static/` | `/api/state`, `/api/cmd`, `/api/agenda`, `/api/conv`, `/api/sessions`; mobil: `/m`, `/api/m/{state,chat,voice,cmd,agenda}`. |
| Durum UI | `ui.py`, `ui_state.py` | Tepsi simgesi + durum penceresi. |
| Uzaktan | `telegram_bot.py`, `remote.py`, `remote_setup.py` | Telegram (kısıtlı kip) ve telefon web arayüzü (Tailscale serve; Funnel açıksa kurulum reddedilir). |
| Telefon | `phonelink.py`, `skills/phone.py`, `phone_app/` | ADB (USB/Wi-Fi) + FCM ile imzalı komut. Flutter + Kotlin uygulama (`com.furkan.jarvisphone`). |
| Masaüstü kurulum | `app.py`, `install_app.py`, `autostart.py` | Menüde JARVIS simgesi, terminalsiz başlatma, tek örnek kilidi (`fcntl`). |

### 3.1 Veri
Tüm kalıcı veri `data/` altında (`JARVIS_DATA` ile değişir; testler geçici klasör kullanır). Dosyalar 0600, klasör 0700. Erişim `skills/_store.py` üzerinden (`load/save/path/runtime_path`). Bilinen dosyalar: `mcp.json (kullanıcının MCP sunucuları), memory.db (SQLite FTS5; eski memory.json göçte memory.json.bak olur), reminders.json, agenda.json, contacts.json, settings.json, status.json, control.json, dashboard.json, briefing.json, router_stats.json, models.json, phone.json, phone_push.json, remote.json, secret.json, session.json, telegram.json, browser_sites.json, conversations.jsonl, team_runs.jsonl, keys.env, fcm_service_account.json, browser_profile/, ram_watch.csv`. Kilit/pid dosyaları `$XDG_RUNTIME_DIR` altındadır.

### 3.2 Model ve donanım gerçekleri (ölçüldü, `RAM.md`)
- Sesli sohbette VRAM **6,8/8 GB** (sıkışık). Gemma+Whisper+TTS birlikte rahat; ek büyük model eklemek VRAM'i aşar.
- `qwen3:8b` yedek, Jarvis açıkken 21%/79% CPU/GPU bölünür. **`gpt-oss:20b` denendi ve reddedildi** (karar 2,3 sn, ilk parça 3,7 sn).
- Gradle daemon'ları `./gradlew --stop` yapılmazsa bellekte kalır. `ram_report.py --watch SN` **saniye** alır (etiket için `--label`).
- Ollama sistem ayarları (RAM.md): `OLLAMA_MAX_LOADED_MODELS=1, NUM_PARALLEL=1, FLASH_ATTENTION=1, KV_CACHE_TYPE=q8_0`; earlyoom `-m 5 -s 10`. İsteğe bağlı kalan: `vm.swappiness=10`.
- Ücretsiz bulut girdi sınırı ≈ **5000 jeton** (Groq ~8K/dk): büyük girdi hiç gönderilmeden reddedilir; 429'da sıradaki modele geçilir.

---

## 4. Kod yapısı ve konvansiyonlar

### 4.1 Yetenek (skill) ekleme
`skills/` altındaki `_` ile başlamayan her `.py` otomatik yüklenir. Dosya `SKILLS = [{"name", "description", "parameters", "run", "hidden"?}]` tanımlar; `run(**kwargs) -> str`. `description`'ın **ilk cümlesi** sistem prompt'undaki yetenek listesine girir (kısa tut).
- **Neden `hidden`?** Araç sayısı arttıkça Gemma'nın doğru aracı seçmesi bozuluyor. Modelin şemasında görünmeyen, yalnızca kural tabanlı hızlı yoldan çağrılan araçlar `"hidden": True` işaretlenir (browser_*, agenda_*, phone_*, codeagent araçları…). **Yeni yetenek eklerken varsayılan tercih: hidden + hızlı yol kuralı.**
- Yeni yetenek eklediğinde sırayla düşün: (a) `brain.py` `REMOTE_BLOCKED` (Telegram/telefon web'den kapatılmalı mı?), (b) `ACTION_CLAIM` regex'i (model araç çağırmadan "yaptım" derse yakalar), (c) `agent.py` `ALLOWED/NETWORK/HELP`, (d) onay gerekir mi (`_confirm.request`), (e) `test_routes.py` vaka(lar)ı + yetenek testi.
- Riskli işlem deseni: araç işi yapmaz, `confirm.request(açıklama, run)` ile bekleyen işlem kaydeder; sonraki cümle modele gitmeden evet/hayır olarak sınıflanır; 60 sn sonra düşer. Testte kalıntı onay: `confirm.cancel()`.

### 4.2 Yetenek dosyaları (özet)
`agenda` (takvim+görev, Türkçe tarih ayrıştırma `_trdate.py`), `apps`, `battery`, `briefing` (günaydın özeti), `brightness`, `browser` (Playwright, ayrı profil, izin listesi), `camera`, `clock`, `codeagent` (workspace araçları), `desktop_input` (fare/klavye, yasaklı yüzeyler), `files` (oku/bul/taşı/çöpe at + geri al), `hardware`, `help`, `memory` ("hatırla"), `phone`, `reminders`, `screen`, `undo`, `volume`, `weather`, `web` (arama). Yardımcılar: `_confirm, _phonenotify, _store, _trdate, _undo`.

### 4.3 Son eklenen kritik parçalar (bu sohbetin sonu)
- **`browser_play`** (`skills/browser.py`): `parse_play(text)` → sorgu ya da `None` (PLAY_NOUN/VERB/NOT/QUOTED/FILL regex'leri; "bir" bilerek dolgu sayılmaz; <2 karakter ya da "bir/bu/şu" → None). `_play`: YouTube arama sayfası → ilk `a#video-title[href^='/watch']` → izle sayfası → `video.play()`. Tarayıcıyı **kapatmaz**. Başlatma argümanı `--autoplay-policy=no-user-gesture-required`.
- `brain._browser_route` en başta `parse_play` dener. `agent.py`: `CLOSE_WANTED = r"kapat(?!ma)"`; hedefte "kapat" yoksa plandaki `browser_close` adımı atılır ("kapatma" demek kapatmak değildir).
- **Kod ajanı sağlamlaştırma:** `code_run(command, stdin="")` (≤2000 karakter; eskiden stdin DEVNULL → `EOFError` döngüsü); `team.py` tolerant `parse_json` + `_fix_escapes` (geçersiz `\` kaçışları), art arda 3 bozuk JSON'da bırakır ve tur sayılmaz, ham geçersiz JSON loglanır; TTS için `speakable` kelime içi alt çizgiyi korur (`test_main.py` "testmain.py" olmasın).
- Hava: `WORD_WEATHER` hızlı yolu. Takvim/görev, telefon uyarıları, Telegram, mobil web arayüzü çalışır durumda (kullanıcı "telefona bildirim sorunu yok" dedi).

### 4.4 Kod stili
Python 3, tip ipuçları (yeni dosyalarda `from __future__ import annotations`), ruff ile lint (`.ruff_cache` var; yapılandırmayı doğrula). Docstring ve yorumlar **Türkçe**. Yeni kodda `eval/exec/os.system/shell=True/pickle` yok; TLS doğrulaması kapatılmaz (`test_security.py` bunu AST ile tarar; `workspace/` taramadan hariçtir). Bağımlılık eklersen `requirements.txt`'e ekle; isteğe bağlıysa **import'u tembel yap** ve yokluğunda kibarca düş.

---

## 5. Test ve doğrulama

| Komut | Ne yapar |
|---|---|
| `python check_all.py --quick` | Modelsiz mantık testleri (saniyeler). **Son durum: 43 OK, 0 hata.** Her değişiklikten sonra çalıştır. |
| `python check_all.py` | + ortam kontrolü |
| `python check_all.py --model` | + gerçek model araç seçimi (`tool_check.py`; GPU+Ollama, dakikalar) |
| `python check_all.py --vision` | + gerçek ekran görüşü |
| `python test_<ad>.py` | Tek modül (routes, browser, agent, team, code, agenda, maintenance, island, memory, mcp, app, dashboard, desktop, mobile, phone, phonelink, ram, router, security, web, window) |
| `python code_check.py` | Kod ajanı bubblewrap kutusu |
| `python router_check.py` | Anahtar + gizlilik kapısı |
| `python phone_check.py [--wifi / --via app / --app-pair / --app-test]` | Telefon/ADB/FCM tanılama |
| `python ram_report.py [--watch SN --label X]` | Bellek ölçümü |

Konvansiyon: testler `JARVIS_DATA`'yı geçici klasöre yönlendirir ve `ollama` yoksa `sys.modules["ollama"]` sahtesi koyar → **GPU/Ollama gerekmez**. Yeni davranış = yeni test vakası (özellikle `test_routes.py`'ye "bu cümle bu aracı çağırmalı / çağırmamalı" satırları).

**Claude Code makinede doğrudan çalıştığı için** `--model`, `--vision`, `ram_report.py`, `ollama ps`, `nvidia-smi` gibi ölçümleri kendin yapabilirsin. Yapamayacakların: mikrofon/wake word duyumu, hoparlör sesi, telefon bildirimini görmek, Flutter uygulamasını telefonda denemek → bunlar "HW testi" (bkz. 7).

---

## 6. Alınan önemli kararlar ve nedenleri

| Karar | Neden |
|---|---|
| v1 silindi, tek dal `main`, klasör `~/jarvis` | v2 v1'in üst kümesiydi; iki hat gereksiz yük. |
| Ücretsiz bulut yalnız kişisel veri yokken | Gizlilik > güç. Bulut yoksa yerel model. |
| Yetenekleri modelden saklamak (hidden) | Araç sayısı arttıkça Gemma araç seçimi bozuluyor. |
| Onay ve yasaklı yüzeyler **kodda** | Güvenlik modelin iyi niyetine bırakılmaz. |
| Kod ajanı bubblewrap + workspace | İnternetsiz, ev klasörü görünmez, 30 sn, `prlimit`. |
| Kod ajanı sınırları: `MAX_CALLS 30`, kod `max_rounds 14`, `max_tokens 1800`, `view_budget 7000`, `MAX_STDIN 2000` | Ücretsiz bulutun ~5K jeton girdi sınırı + yerel modelin kod için zayıflığı (kod rolü `patient`: limitte yerele düşmek yerine bekler). Pratikte küçük/orta (≈120 satır/dosya, birkaç dosya) programlar; büyük projeler için kod ajanı değil Claude Code kullanılır. |
| `gpt-oss:20b` reddedildi | Gecikme (2,3 sn karar) ve VRAM. |
| Windows desteği: planlandı, **başlanmadı** | Arkadaşlar Win11 kullanıyor; plan 8'de. |
| Onay kapıları, yasaklı yüzeyler, gizlilik kapısı gevşetilmez | Kodda zorlanan kapılar projenin ana özelliği; bunları azaltan değişiklik yapmadan önce kullanıcıya sor. |

---

## 7. ÇALIŞMA DÜZENİ (Claude Code için talimat)

Kullanıcı şunu istedi: **görevleri sırayla kendin yap; kod yaz, test et, commit'le; ayrıca onay isteme. Yalnızca donanım gerektiren denemeler için kullanıcıdan test iste.**

Her görev için:
1. `TASKS.md`'den sıradaki görevi al. Karmaşıksa önce kısa plan (plan modu) çıkar; küçükse doğrudan yap.
2. Kodu yaz + testini yaz. `python check_all.py --quick` **hatasız** olmalı (`git status`'ta beklenmeyen dosya yok).
3. Commit at (Claude Code'un varsayılan atıfı yeterli; mesaj Türkçe veya kısa İngilizce, açıklayıcı).
4. **Görev tipi [YAZILIM]** (donanımsız doğrulanabilir): push et (`git push`), `TASKS.md`'de işaretle, **kullanıcıya sormadan sıradaki göreve geç.**
5. **Görev tipi [HW]** (mikrofon, wake word, ses, telefon/Flutter, Qt ekranda görsel doğrulama gibi): commit'le, kullanıcıya **tek satırda ne deneyeceğini** söyle (komut + beklenen sonuç) ve **cevabını bekle**. "Çalışıyor" derse push et ve devam et; hata derse düzelt.
6. Push öncesi **sır taraması:** `git diff --cached --name-only` içinde `data/`, `*.env`, `keys.env`, `fcm_service_account.json`, `google-services.json`, `workspace/` olmamalı; diff'te `AIza`, `gsk_`, `sk-`, `ts.net`, telefon numarası/e-posta kalıpları aranmalı. Repo public.
7. Durup kullanıcıya sorman gereken tek durumlar: geri alınamaz ve iki makul yönü olan karar (ör. sipariş sitesi seçimi), sır/anahtar gerektiren adım (kullanıcı kendisi koyar), onay kapılarını/gizlilik kuralını değiştirmeyi gerektiren bir şey. Bunlar dışında kendin karar ver ve commit mesajında/`TASKS.md`'de not düş.

Genel tutum: küçük, geri alınabilir commit'ler; her commit'te testler yeşil. Ölçmeden "hızlandı/küçüldü" deme. Hata çıkarsa belirtiyi gizleme, kök nedeni düzelt. `data/` içine **dokunma** (kullanıcının kişisel verisi).

---

## 8. Yol haritası (kullanıcı bu sırayı korumamı istedi)

**Ajan serisi (Jarvis'in kendi içindeki ajanlar, `team.py` rolleri olarak):**
1. **Denetçi (test/gözden geçirme) ajanı** — kod ajanı çıktısını ayrı bağlamda çalıştırıp doğrular; yazanın kendi işini notlamaması için.
2. **Mimar ajanı** — büyük istekleri modüllere böler; kod ajanının küçük-dosya sınırına uygun plan çıkarır.
3. **Sistem bakım ajanı** — RAM/disk/Ollama/log sağlığını izler, öneri üretir (kendi başına riskli şey yapmaz; onay kapılı).

**Sonra:**
4. **Qt "ada" yer paylaşımı** (üst kenarda küçük bir bildirim/onay çubuğu; **Evet/Hayır** butonlarıyla `_confirm`'e bağlanır). Cinnamon appleti/desklet alternatifleri değerlendirildi; Qt overlay önerildi.
5. **FTS5 / anlamsal hafıza** — FTS5 bitti (`skills/memory.py`, `data/memory.db`); ikinci aşama yerel gömme (anlamsal arama) bekliyor.
6. **MCP istemcisi** — bitti (`mcp_client.py`, `skills/mcp.py`, `data/mcp.json`; gizli + onay kapılı + uzaktan kapalı).
7. **Windows taşıma** (paralel yürüyebilir): `platform_compat.py` soyutlaması; `psutil`, `pycaw` (ses), `pyautogui`, `mss`; `kur.bat`/`install.ps1`; donanım algılayıp hafif profil seçme; Windows'ta kod ajanı kapalı (bubblewrap yok); README'ye Windows bölümü. Linux davranışını bozma.
8. **Sipariş özelliği** (Getir/Yemeksepeti/Trendyol GO) — site önceliği için kullanıcıya **bir kez** sor; kural: sepeti kur, ödemede dur.

**Piyasa karşılaştırmasından çıkan eksikler** (diğer Jarvis/agent projeleri ve `louis-cfm/coucou` incelendi): MCP istemcisi, FTS5/anlamsal hafıza, zamanlanmış/proaktif ajan görevleri, e-posta/takvim entegrasyonu (Google Calendar), OCR/erişilebilirlik tabanlı tıklama, paylaşılabilir yetenek paketleme. coucou: AI kodlama ajanları için üst kenar (notch) onay arkadaşı, MIT lisanslı; görselleri sahibine ait → **kodu/varlıkları kopyalama, yalnızca fikir al.**

**Diğer fikirler / küçük işler:** Ders ajanı, Git ajanı; README'de kredi bölümü; Google Takvim senkronu; ntfy; kod ajanında "kendi projem" kipi; `vm.swappiness=10`; Qwen 3.5 9B araç çağırma karşılaştırması (önce ollama.com/library'de etiketi doğrula); yerel gömme modeli.

**Dokümantasyon borcu (kullanıcı "unutturma" dedi):** Her önemli değişiklikte `README.md` (özellikle "Neler yapabiliyor" tablosu ve "Proje yapısı") ve `RAM.md` güncellenmeli; yeni klasör/dosya eklendiyse yapı bloğuna yaz.

---

## 9. Açık/doğrulanmamış noktalar
- `v2zi` etiketi ve `team.py`/`test_team.py` alt çizgi düzeltmesi + `RAM.md` güncellemesinin commit'lenip push'lanması kullanıcıdan teyit bekliyor → `git status`, `git log`, `git tag -l` ile kontrol et, eksikse tamamla.
- Kod ajanının ilk başarısız çalışmasındaki ham geçersiz JSON hiç görülmedi (loglama eklendi; sorun tekrarlarsa `[ekip]` loglarına bak).
- Flutter derlemesi sırasındaki RAM tepesi yakalanmadı (gereksiz bulundu).
- Qwen 3.5 9B tool-calling ölçülmedi.
- Windows ve sipariş özellikleri tasarım aşamasında; kod yok.

---

## 10. Hızlı başlangıç (Claude Code ilk oturum)
Kullanıcı Claude Code'u **Claude masaüstü uygulamasından (Code sekmesi)** kullanıyor: Ortam = Yerel, klasör = `~/jarvis`, izin modu = Auto (ya da Accept edits). Terminal (`claude`) ya da VS Code eklentisi kullanmıyor; talimatlar ona göre.
```bash
cd ~/jarvis
git status && git log --oneline -5 && git tag -l | tail -3
python check_all.py --quick | tail -3      # 43 OK bekleniyor (conda env freya)
cat TASKS.md                               # sıradaki görev
```
`.claude/settings.json` (repoda) izin listesini ve `data/**`, `*.env`, `fcm_service_account.json`, `google-services.json` okuma yasağını tanımlar. İlk iş doğrula: `data/` altından bir dosya okumayı dene → reddedilmeli. Reddedilmezse kullanıcıya söyle (uygulama dosyayı okumuyor demektir). Sonra `TASKS.md` bölüm 0'dan başla.
