# TASKS — sırayla yapılır

Etiketler: **[YAZILIM]** = testlerle doğrulanır, bittiğinde push edip sıradakine geç · **[HW]** = kullanıcının mikrofon/ses/telefon/ekran denemesi gerekir; commit'le, ne deneyeceğini tek satırda söyle, onay gelince push et.
Durum: `[ ]` bekliyor · `[~]` sürüyor · `[x]` bitti (tarih + commit kısaltması ekle).

## 0. Hazırlık
- [x] [YAZILIM] `git status`, `git log --oneline -5`, `git tag -l`: `v2zi` etiketi, `team.py`/`test_team.py` alt çizgi düzeltmesi ve `RAM.md` güncellemesi commit'li/push'lu mu? Eksikse tamamla (etiket: sıradaki `v2zj`).
- [x] [YAZILIM] `python check_all.py --quick` → 39 OK doğrula. `.claude/settings.json` korumasını doğrula: `data/` altından okuma denemesi reddedilmeli (reddedilmezse kullanıcıya bildir).

## 1. Ajan serisi (team.py rolleri)
- [x] [YAZILIM] **Denetçi ajanı:** kod ajanı çıktısını (workspace projesi) ayrı bağlamda çalıştırıp/okuyup doğrular; bulgu listesi + geçti/kaldı. Yalnızca düzeltme gerektiren bulguları bildirir. Rol testleri `test_team.py`'ye. `kod:` akışına isteğe bağlı son adım olarak bağla.
- [x] [YAZILIM] **Mimar ajanı:** büyük isteği modüllere/dosyalara böler (kod ajanı sınırlarına uygun: dosya başı ≈120 satır, kısa bağlam); plan sesli okunur, tek "evet".
- [x] [YAZILIM] **Sistem bakım ajanı:** `memguard`/`ram_report`/Ollama/log/disk sağlığı özeti ve öneriler; kendi başına değişiklik yapmaz, riskli adım onay kapılı.

## 2. Arayüz
- [x] [YAZILIM→HW] **Qt "ada" yer paylaşımı:** ekranın üst kenarında küçük, tıklanabilir bildirim/onay çubuğu; bekleyen `_confirm` işlemleri için **Evet/Hayır** butonları, durum (dinliyor/düşünüyor/konuşuyor). Mantığı test edilebilir kısım [YAZILIM], görsel/konum doğrulaması [HW]. coucou'dan yalnızca fikir al, kod/varlık kopyalama.

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
- [x] Kod ajanı yerel modelde geçersiz JSON (2026-10-25, aşağıda not)

## Bitenler
(Claude Code buraya tarih, commit ve kısa not ekler.)
- 2026-10-25 · Bölüm 0: `main` = `origin/main`, çalışma ağacı temiz. `v2zi` (d0406dc) uzakta mevcut; alt çizgi düzeltmesi (fd004ab) ve `RAM.md` (901d4ab) push'lu → eksik yok, yeni etiket gerekmedi. `check_all.py --quick`: 39 OK, 0 hata. `data/settings.json` Read denemesi izin ayarlarınca reddedildi (not: deny kuralları Read aracını kapsar, Bash `cat`'i değil — kurala uyuluyor).
- 2026-10-25 · Denetçi ajanı (`team.py` rolü `denetci`): `kod:` akışında Kod Ajanı → Denetçi → Yazar; "kod: denetimsiz, …" ile atlanır. Ayrı bağlam (kod ajanının konuşması gitmez, iddiası "doğrulanmamış" etiketli), araçları yalnızca `code_list/code_read/code_run`. Hüküm kodda: bulgu varsa geçti sayılmaz, hiç çalıştırmadan geçti → doğrulanamadı; `team_runs.jsonl`'a `verdict`. Planlayıcı planında denetçi yalnızca kod görevinden sonra kalır. Testler `test_team.py`.
- 2026-10-25 · Mimar ajanı: "proje: …" / "mimar: …" → Mimar (onaydan önce tek bulut çağrısı) isteği ≤4 parçaya böler (parça başı ≤2 dosya, ≈120 satır/dosya, arayüzler); plan sesli okunur, tek "evet". Parçalar sırayla aynı projede Kod Ajanı görevleri, tasarım (≤1500 karakter) her kod ajanına ve denetçiye veri olarak gider; sonra Denetçi + Yazar. `validate_design` yolları kodda doğrular. Proje kipinde araç sınırı 60. Mimar planlayıcıya rol olarak sunulmaz.
- 2026-10-25 · Gerçek model denemesi (yerel gemma4:e4b; bulut anahtarı geçici veri klasörüne bağlanamadığı için bulut yolu denenmedi): `check_all.py --model` araç seçimi 102/102. Ekip denemesi iki hata buldu, düzeltildi (51aee19): (1) `code_run` bellek sarmalayıcısı (systemd-run --user) temiz ortamda bus'a ulaşamıyor, her çalıştırma çıkış kodu 1 veriyordu; (2) model `code_write`'a `file` verdi, ad atılınca görev düşüyordu → kılavuzda gerçek parametre adları + takma ad düzeltme. Sonrasında `kod:` akışı uçtan uca: testler 4/4, Denetçi kendisi çalıştırıp "geçti". Mimar yerelde makul plan çıkardı (3 parça); proje kipinde kod parçaları yerelde geçersiz JSON ile düştü (küçük işler listesine yazıldı).
- 2026-10-25 · Sistem bakım ajanı (`skills/maintenance.py`, gizli araç `system_health`, hızlı yol "sistem bakımı yap / bilgisayarım neden yavaş / bakım raporu"; ekip rolü `bakim`, yalnızca yerel). Bellek/PSI/swap, VRAM, yüklü modeller + CPU'ya taşma, Ollama servis ayarları, disk, workspace, `jarvis.log` hata izi, unutulmuş Gradle/Kotlin daemon'ları. Kendi başına değişiklik yok; yalnızca fazladan modeli boşaltma ve daemon durdurma onay kapısıyla, sudo işleri yalnızca öneri. Uzaktan kapalı. `test_maintenance.py` (check_all'da, 40 OK).
- 2026-10-25 · Yerel modelde geçersiz JSON ölçüldü ve düzeltildi. 9 gerçek tur (gemma4:e4b, proje kipi) ham cevap + `done_reason` kaydı: "4096 bağlam taşması" varsayımı YANLIŞ çıktı (190 cevaptan yalnızca 2'si `done=length`, o da tekrar döngüsü). Asıl neden JSON yazım hataları: dizge içinde kaçışsız tırnak, kaçışlı sınırlayıcı (`\"…\"`), fazladan/eksik kapatıcı, nesneden sonra başıboş karakter, tek cevapta birden çok çağrı. `team._repair` son çare onarım; dizge ortasında kesilmiş cevap yalnızca `final` ise kabul (yarım dosya yazılmaz). Kayıtlı 190 cevapta geçersiz oranı %20 → %1,1; onarılan tüm `.py` içerikleri derleniyor. Ayrıca ölçümden: aynı çağrı tekrarlanmaz (denetçi aynı dosyaları okuyup tur sınırına takılıyordu), dosya `code_run` olmadan en fazla 2 kez yazılır, denetçi tur sınırında son kez yalnızca hüküm istenir, mimar planındaki yazılmamış dosya kendiliğinden bulgu. Açık kalan: yerel model engel mesajına rağmen aynı dosyayı yazmayı denemeyi sürdürebiliyor (1/9 turda kod parçası tur sınırında düştü); bulut yolu ölçülmedi.
- 2026-10-25 · Qt "ada" [YAZILIM kısmı bitti, HW bekliyor]: `island.py` (`main.py --island`), pano sunucusunda `/api/island` + `/api/island/answer`. Düğmeler sesli cevapla aynı yoldan; `_confirm.pending_info()` (salt görüntü + artan kimlik) ile eski soruya cevap reddi; plan onayı (ajan/ekip) da gösterilir. Fare/klavye aracı Jarvis pencerelerini (başlık "JARVIS Ada"/"JARVIS Komut Merkezi") yasaklı yüzey sayar; ada odak almaz, imlecin altındaki pencereye de bakılır. Pano 'pending' bayrağı ekip planını da sayıyor (önceden yalnızca ajan). `test_island.py` 26 OK (ekransız Qt duman testi dahil); gerçek ekranda görüntü alınıp kontrol edildi (üst orta, boş/onay halleri).
- 2026-10-25 · Qt "ada" HW denemesi: kullanıcı doğruladı (üstte göründü, Evet/Hayır doğru çalıştı) → push.
