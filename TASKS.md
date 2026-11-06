# TASKS — sırayla yapılır

Etiketler: **[YAZILIM]** = testlerle doğrulanır, bittiğinde push edip sıradakine geç · **[HW]** = kullanıcının mikrofon/ses/telefon/ekran denemesi gerekir; commit'le, ne deneyeceğini tek satırda söyle, onay gelince push et · **[SOR]** = kullanıcıya `AskUserQuestion` ile sorulacak adım.
Durum: `[ ]` bekliyor · `[~]` sürüyor · `[x]` bitti (tarih + commit kısaltması). Bitenlerin ayrıntısı `HANDOFF.md` bölüm 10'a yazılır; burada tek satır kalır.

## Bitenler (özet)
- [x] Hazırlık: depo durumu, `v2zi` push'lu, `data/` okuma koruması
- [x] Ajan serisi: Denetçi (55ad3a3), Mimar (352b96b), Sistem bakım (cfd6130), gerçek model denemesi (51aee19, 07633a1)
- [x] Hafıza ve entegrasyon: FTS5 hafıza (3b74312), MCP istemcisi (6cc4ecc, e7d947d)
- [x] Güvenlik taraması (c509f33) · Temizlik (ce95410) · UI gözden geçirme (b64af9c)
- [x] Maskot "Çekirdek" ve ada: Qt ada (d92f190), maskot (93c3389, bda73c7), etkin hal (6c15a1d), Ayarlar > ADA (d85a97c), otomatik gizlenme (0b569d5)
- [x] README kredi bölümü (db3788b) · Klasör düzeni (2be00ce) · Zamanlanmış görevler (acb02aa)
- [x] Belgeler: CLAUDE.md kısaltıldı, geçmiş/kararlar HANDOFF.md'ye (2026-11-06)
- [x] ~~Sipariş özelliği~~ **İPTAL** (2026-10-26, kullanıcı kararı)

## 1. Platform
- [ ] [YAZILIM] **Windows taşıma (1. aşama):** `platform_compat.py`; ses (`pycaw`), fare/klavye (`pyautogui`), ekran (`mss`), `psutil` bellek; `kur.bat`/`install.ps1`; donanım algılayıp hafif profil; Windows'ta kod ajanı kapalı; README Windows bölümü. Linux'u bozma.
- [ ] [HW] Windows'ta gerçek deneme (kullanıcı ya da Win11 kullanan arkadaşlar).

## 2. YENİ — Ders reposu (Issue → Branch → PR)
- [ ] [SOR] Kapsamı netleştir: hangi ders(ler), repo adı, public/private, yeni repo mu yoksa mevcut bir repo mu, Jarvis'ten mi (Git/ders ajanı) yoksa yalnızca Claude Code iş akışı olarak mı yönetilecek. Repo oluşturma/görünürlük geri alınamaz → kullanıcı onaylar.
- [ ] [YAZILIM] İş akışı: her iş bir **Issue** ile açılır → `issue-<no>-<kısa-ad>` dalı → commit'ler (`#<no>` atıflı) → **PR** (`Closes #<no>`) → kontrol/ödev testleri → birleştirme. Issue/PR şablonları (`.github/ISSUE_TEMPLATE`, `pull_request_template.md`), README'de akış anlatımı; `gh` CLI ile.
- [ ] [YAZILIM] (İsteğe bağlı, onaydan sonra) Jarvis'e "ders ajanı/Git ajanı" bağlantısı: sesli "şu ödev için issue aç", "PR durumu ne" — gizli yetenek + hızlı yol; issue/PR açma onay kapılı, uzaktan kapalı (`REMOTE_BLOCKED`); kişisel veri buluta gitmez.

## 3. YENİ — Asistanın yeniden adlandırılması
- [ ] [SOR] Yeni ad (ve hitap/wake word). Kapsamı sor: yalnızca görünen ad mı, yoksa wake word, GitHub repo adı, paket/uygulama kimliği (`com.furkan.jarvisphone`), `~/jarvis` klasörü, `JARVIS_*` ortam değişkenleri de mi değişecek. Repo/paket kimliği değişikliği geri alınması zor → onaylı.
- [ ] [YAZILIM] Görünen ad tek yerde (ör. `core/identity.py` `NAME`): sistem prompt'u, sesli cevaplar, pano/mobil/ada metinleri, tepsi, `.desktop` dosyaları (`tools/install_app.py`, `tools/autostart.py`), Telegram mesajları, README'ler. Eski adla çağırma bir süre çalışmaya devam etsin. `tests/test_routes.py` ve arayüz testleri güncellenir.
- [ ] [HW] Wake word: openWakeWord'de hazır "hey jarvis" modeli var; yeni ad için özel model eğitimi gerekir (eğitim + eşik ayarı + yanlış uyanma denemesi). Kullanıcı mikrofonla dener.
- [ ] [HW] Telefon uygulaması adı/simgesi (Flutter) ve masaüstü menü girdisi görsel doğrulama.

## 4. Küçük işler / fikirler (sıra esnek)
- [ ] `vm.swappiness=10` (RAM.md'de komut var; kullanıcı sistemine uygular)
- [ ] Qwen 3.5 9B araç çağırma ölçümü (önce ollama.com/library'de etiketi doğrula; `tools/model_bench.py`)
- [ ] Anlamsal hafıza (yerel gömme modeli; FTS5'in ikinci aşaması)
- [ ] Google Takvim senkronu; ntfy bildirimi
- [ ] Kod ajanında "kendi projem" kipi (güvenlik tasarımı önce kullanıcıya özetlenir)
- [ ] Ders ajanı, Git ajanı (bölüm 2 ile birleşebilir)
- [ ] Zamanlanmış görevi gerçek saatle bekleyerek dene (şimdiye dek sahte saatle test edildi)
