# TASKS — sırayla yapılır

Etiketler: **[YAZILIM]** = testlerle doğrulanır, bittiğinde push edip sıradakine geç · **[HW]** = kullanıcının mikrofon/ses/telefon/ekran denemesi gerekir; commit'le, ne deneyeceğini tek satırda söyle, onay gelince push et · **[SOR]** = kullanıcıya `AskUserQuestion` ile soru sorulacak adım.
Durum: `[ ]` bekliyor · `[~]` sürüyor · `[x]` bitti (tarih + commit kısaltması ekle).
**İlk iş:** `git log --oneline -20` ile gerçek durumu bu dosyaya yansıt. Biten görevleri `[x]` yap, işaretlenmemiş ama yapılmış olanları da (Sistem bakım, Qt ada, FTS5 hafıza vb.) not düşerek işaretle.

## 0. Hazırlık
- [x] Depo durumu, `v2zi`, 39 OK, `data/` okuma koruması doğrulandı.

## 1. Ajan serisi (team.py rolleri)
- [x] **Denetçi ajanı** (55ad3a3)
- [x] **Mimar ajanı** (352b96b)
- [ ] **Sistem bakım ajanı:** `memguard`/`ram_report`/Ollama/log/disk sağlığı özeti ve öneriler; kendi başına değişiklik yapmaz, riskli adım onay kapılı. (Yapıldıysa işaretle.)
- [ ] [YAZILIM] **Gerçek model denemesi:** `python check_all.py --model` ile Denetçi + Mimar (+ Sistem bakım) rollerini gerçek modelle dene; JSON protokolüne uymuyorsa düzelt. (Kendin çalıştır, kullanıcıdan test isteme.)

## 2. Hafıza ve entegrasyon
- [ ] **SQLite FTS5 hafıza** (yapıldıysa işaretle)
- [x] **MCP istemcisi** (e7d947d): `mcp-server-time` ile çalıştı. Sunucu ayrı venv'de; kullanıcının `data/mcp.json`'una ekleme talimatını README'ye yaz.

## 3. YENİ — Güvenlik ve temizlik (Windows'tan ÖNCE; ölü kodu taşımayalım)
- [ ] [YAZILIM] **Güvenlik taraması:** `test_security.py`'ye ek olarak elle gözden geçir: komut enjeksiyonu, yol kaçışı, sır sızıntısı (log'lar, hata mesajları, `git ls-files` ile takip edilen dosyalar), public repo riskleri, MCP istemcisi ve uzaktan (Telegram/telefon web) yüzeyi, onay kapısının atlanabileceği yollar. Bulguları şiddetine göre listele, açıkları düzelt, her biri için test ekle.
- [ ] [YAZILIM→SOR] **Gereksiz kod/dosya temizliği:** kullanılmayan modül, fonksiyon, bağımlılık, tekrar eden dosya, eski tanılama betikleri (`tool_diag*.py`, `stt_test.py`, `tts_compare.py` vb.) için **önce liste çıkar** (neden gereksiz: kim import ediyor / hangi testte geçiyor). Listeyi kullanıcıya göster. **Yalnızca kullanıcı onayladıklarını sil**; açıkça ölü ve hiçbir yerde referansı olmayanları listede ayrıca işaretle. Silmeden sonra `check_all.py --quick` yeşil kalmalı, README "Proje yapısı" güncellenmeli.

## 4. YENİ — Arayüz düzeltmeleri
- [ ] [YAZILIM→SOR] **UI gözden geçirme:** pano, mobil sayfa (`/m`), durum penceresi ve (varsa) ada arayüzünü gez. Bozuk/eksik/fazla/tutarsız yerleri listele (hizalama, boş sekme, kullanılmayan düğme, Türkçe metin hataları, tema renkleri, küçük ekran). Emin olmadığın her yer için kullanıcıya **soru olarak sor** (tahminle silme/ekleme yapma). Onaylananları düzelt. Görsel doğrulama [HW].

## 5. YENİ — Maskot ve ada ayarları
Maskot **"Çekirdek"** (kullanıcı seçti). Hazır varlıklar: `assets/cekirdek.svg` (animasyonlu, CSS ile durum değişir) ve `assets/cekirdek_demo.html` (6 durum önizlemesi). Başka projenin görsel/kodunu kopyalama; yalnızca bu özgün SVG.
- [ ] [YAZILIM] **Maskot entegrasyonu:** SVG'yi **satır içi (inline)** göm (`<img>` içinde durum değişmez); kök `svg` öğesinin `data-state` değeri `idle | listening | thinking | speaking | alert | error` olur. Durum eşlemesi: bekleme → idle; wake word/mikrofon açık → listening; model/araç çalışıyor → thinking; TTS konuşuyor → speaking; onay bekleyen işlem/uyarı → alert; hata → error. Kaynak: `ui_state.py`/`status.json`. Pano ve (varsa) Qt ada/durum penceresinde göster; `prefers-reduced-motion` desteği SVG'de var, bozma. Mantığı test et (durum → data-state eşlemesi).
- [ ] [HW] Maskotun pano ve adada akıcı/okunur olduğunu kullanıcı dener (boyut, animasyon hızı, CPU yükü).
- [ ] [YAZILIM→HW] **Ayarlar sekmesinde "Ada" bölümü:** tema (mevcut temalar: cyan, amber, yeşil, mor, açık ile uyumlu; maskot rengi de temayı izlesin), **her zaman üstte** aç/kapa, **maskotu göster/gizle**, ada konumu (üst orta/sol/sağ), **boyut**, **adayı kapat** (sadece adayı kapatır, Jarvis'i değil; geri açmak için tepsi menüsünde seçenek). Değerler `settings.json`'da kalır, yeniden başlatınca korunur, testleri yaz. Ada görsel davranışı [HW].
- [ ] **Qt "ada" yer paylaşımı** (yapılmadıysa): üst kenarda küçük bildirim/onay çubuğu; bekleyen `_confirm` için **Evet/Hayır** butonları, maskot + durum. coucou'dan yalnızca fikir al.

## 6. Platform ve özellik
- [ ] [YAZILIM] **Windows taşıma (1. aşama):** `platform_compat.py`; ses (`pycaw`), fare/klavye (`pyautogui`), ekran (`mss`), `psutil` bellek; `kur.bat`/`install.ps1`; donanım algılayıp hafif profil; Windows'ta kod ajanı kapalı; README Windows bölümü. Linux'u bozma. **Bölüm 3-5 bittikten sonra başla.**
- [ ] [HW] Windows'ta gerçek deneme (kullanıcı ya da Win11 kullanan arkadaşlar).
- [ ] [SOR→YAZILIM] **Sipariş özelliği:** önce kullanıcıya TEK soru: hangi site önce (Getir / Yemeksepeti / Trendyol GO)? Sonra Playwright ile sepet kurma, ödemeden önce dur, parola/kart saklama yok.

## 7. Küçük işler / fikirler (sıra esnek)
- [ ] README'ye kredi bölümü; yeni özellikler "Neler yapabiliyor" tablosuna
- [ ] `vm.swappiness=10` (RAM.md'de komut var; kullanıcı sistemine uygular)
- [ ] Qwen 3.5 9B araç çağırma ölçümü (önce ollama.com/library'de etiketi doğrula; `model_bench.py`)
- [ ] Zamanlanmış/proaktif ajan görevleri; Google Takvim senkronu; ntfy bildirimi
- [ ] Kod ajanında "kendi projem" kipi (güvenlik tasarımı önce kullanıcıya özetlenir)
- [ ] Ders ajanı, Git ajanı

## Bitenler
- 55ad3a3 Denetçi ajanı · 352b96b Mimar ajanı · e7d947d MCP istemcisi (gerçek `mcp-server-time` ile çalıştı, JSON sonuçlar sesli cümleye çevriliyor)
