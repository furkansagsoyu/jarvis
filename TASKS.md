# TASKS — sırayla yapılır

Etiketler: **[YAZILIM]** = testlerle doğrulanır, bittiğinde push edip sıradakine geç · **[HW]** = kullanıcının mikrofon/ses/telefon/ekran denemesi gerekir; commit'le, ne deneyeceğini tek satırda söyle, onay gelince push et.
Durum: `[ ]` bekliyor · `[~]` sürüyor · `[x]` bitti (tarih + commit kısaltması ekle).

## 0. Hazırlık
- [x] [YAZILIM] `git status`, `git log --oneline -5`, `git tag -l`: `v2zi` etiketi, `team.py`/`test_team.py` alt çizgi düzeltmesi ve `RAM.md` güncellemesi commit'li/push'lu mu? Eksikse tamamla (etiket: sıradaki `v2zj`).
- [x] [YAZILIM] `python check_all.py --quick` → 39 OK doğrula. `.claude/settings.json` korumasını doğrula: `data/` altından okuma denemesi reddedilmeli (reddedilmezse kullanıcıya bildir).

## 1. Ajan serisi (team.py rolleri)
- [x] [YAZILIM] **Denetçi ajanı:** kod ajanı çıktısını (workspace projesi) ayrı bağlamda çalıştırıp/okuyup doğrular; bulgu listesi + geçti/kaldı. Yalnızca düzeltme gerektiren bulguları bildirir. Rol testleri `test_team.py`'ye. `kod:` akışına isteğe bağlı son adım olarak bağla.
- [ ] [YAZILIM] **Mimar ajanı:** büyük isteği modüllere/dosyalara böler (kod ajanı sınırlarına uygun: dosya başı ≈120 satır, kısa bağlam); plan sesli okunur, tek "evet".
- [ ] [YAZILIM] **Sistem bakım ajanı:** `memguard`/`ram_report`/Ollama/log/disk sağlığı özeti ve öneriler; kendi başına değişiklik yapmaz, riskli adım onay kapılı.

## 2. Arayüz
- [ ] [YAZILIM→HW] **Qt "ada" yer paylaşımı:** ekranın üst kenarında küçük, tıklanabilir bildirim/onay çubuğu; bekleyen `_confirm` işlemleri için **Evet/Hayır** butonları, durum (dinliyor/düşünüyor/konuşuyor). Mantığı test edilebilir kısım [YAZILIM], görsel/konum doğrulaması [HW]. coucou'dan yalnızca fikir al, kod/varlık kopyalama.

## 3. Hafıza ve entegrasyon
- [ ] [YAZILIM] **SQLite FTS5 hafıza:** `memory.json` → arama yapılabilir depo (geri uyumlu göç); isteğe bağlı yerel gömme (Ollama gömme modeli) ikinci aşama. Kişisel veri buluta gitmez.
- [ ] [YAZILIM] **MCP istemcisi:** yerel MCP sunucularına bağlanma; her MCP aracı `hidden` + onay kapılı, `REMOTE_BLOCKED`'a ekli, gizlilik kuralı korunur.

## 4. Platform ve özellik
- [ ] [YAZILIM] **Windows taşıma (1. aşama):** `platform_compat.py`; ses (`pycaw`), fare/klavye (`pyautogui`), ekran (`mss`), `psutil` bellek; `kur.bat`/`install.ps1`; donanım algılayıp hafif profil; Windows'ta kod ajanı kapalı; README Windows bölümü. Linux'u bozma.
- [ ] [HW] Windows'ta gerçek deneme — kullanıcı ya da Win11 kullanan arkadaşları dener (geri bildirim bekle).
- [ ] [KARAR→YAZILIM] **Sipariş özelliği:** önce kullanıcıya TEK soru: hangi site önce (Getir / Yemeksepeti / Trendyol GO)? Sonra Playwright ile sepet kurma, ödemeden önce dur, parola/kart saklama yok.

## 5. Küçük işler / fikirler (sıra esnek)
- [ ] README'ye kredi bölümü; yeni özellikler "Neler yapabiliyor" tablosuna
- [ ] `vm.swappiness=10` (RAM.md'de komut var; kullanıcı sistemine uygular)
- [ ] Qwen 3.5 9B araç çağırma ölçümü (önce ollama.com/library'de etiketi doğrula; `model_bench.py`)
- [ ] Zamanlanmış/proaktif ajan görevleri; Google Takvim senkronu; ntfy bildirimi
- [ ] Kod ajanında "kendi projem" kipi (workspace dışı projeye kontrollü erişim — güvenlik tasarımı önce kullanıcıya özetlenir)
- [ ] Ders ajanı, Git ajanı

## Bitenler
(Claude Code buraya tarih, commit ve kısa not ekler.)
- 2026-10-25 · Bölüm 0: `main` = `origin/main`, çalışma ağacı temiz. `v2zi` (d0406dc) uzakta mevcut; alt çizgi düzeltmesi (fd004ab) ve `RAM.md` (901d4ab) push'lu → eksik yok, yeni etiket gerekmedi. `check_all.py --quick`: 39 OK, 0 hata. `data/settings.json` Read denemesi izin ayarlarınca reddedildi (not: deny kuralları Read aracını kapsar, Bash `cat`'i değil — kurala uyuluyor).
- 2026-10-25 · Denetçi ajanı (`team.py` rolü `denetci`): `kod:` akışında Kod Ajanı → Denetçi → Yazar; "kod: denetimsiz, …" ile atlanır. Ayrı bağlam (kod ajanının konuşması gitmez, iddiası "doğrulanmamış" etiketli), araçları yalnızca `code_list/code_read/code_run`. Hüküm kodda: bulgu varsa geçti sayılmaz, hiç çalıştırmadan geçti → doğrulanamadı; `team_runs.jsonl`'a `verdict`. Planlayıcı planında denetçi yalnızca kod görevinden sonra kalır. Testler `test_team.py`.
