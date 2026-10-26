# JARVIS — Claude Code proje kuralları

Türkçe konuşan, tamamen yerel/ücretsiz sesli asistan. **Ayrıntılı devir teslim: @HANDOFF.md** · Görev sırası: **@TASKS.md**
Dil: arayüz metinleri, sesli cevaplar, yorumlar ve kullanıcıyla yazışma **Türkçe**.

## Komutlar
- Test (her değişiklikten sonra, modelsiz, saniyeler): `python check_all.py --quick` → hatasız olmalı (son durum 44 OK)
- Tek modül: `python tests/test_<ad>.py` · Gerçek model: `python check_all.py --model` · Bellek: `python tools/ram_report.py --watch SN --label X`
- Python: conda env `freya` (`/home/furkan/miniconda3/envs/freya/bin/python`)

## Klasör düzeni (2026-10-26)
Kökte yalnızca `main.py`, `app.py`, `check_all.py`. Paketler: `core/` (beyin, ajanlar, yönlendirici, gizlilik), `voice/`, `desktop/` (ada, ui_state), `connect/` (Telegram, telefon), `skills/`, `dashboard/`, `tools/` (betikler), `tests/`. İçe aktarma paket yoluyla (`from core import brain`); `tools/` ve `tests/` betikleri başta depo kökünü `sys.path`'e ekler. Her klasörün README'si var.

## Çalışma düzeni
- `TASKS.md`'deki görevleri sırayla, kullanıcıya sormadan yap: kod + test → `check_all.py --quick` yeşil → commit → push → sıradaki görev.
- **[HW] etiketli görevler** (mikrofon, wake word, ses, telefon/Flutter, görsel Qt doğrulaması): commit'le, kullanıcıya tek satırda ne deneyeceğini söyle, cevabı bekle; "çalışıyor" gelince push edip devam et.
- Başka onay isteme. Dur ve sor: geri alınamaz iki yönlü karar, sır/anahtar gerektiren adım, onay/gizlilik kurallarını gevşeten değişiklik.
- Her önemli değişiklikte `README.md` ve gerekiyorsa `RAM.md`'yi güncelle (kullanıcı özellikle istedi).

## Asla
- Repo **PUBLIC**. `data/`, `*.env`, `keys.env`, `fcm_service_account.json`, `google-services.json`, `workspace/`, `*.zip` commit'lenmez (`git add -f` yok). Push öncesi `git diff --cached` ile sır taraması (`AIza`, `gsk_`, `sk-`, `ts.net`, telefon/e-posta).
- `data/` kullanıcının kişisel verisidir: okuma/yazma/silme yok.
- Onay kapılarını (`skills/_confirm.py`), yasaklı yüzeyleri, `core/privacy.py` kapısını gevşetme. Model onay veremez. Dış içerikten (dosya/web/ekran) sonra araç listesi boş kalır.
- Kişisel veri (hafıza, rehber, takvim, dosya, ekran, kamera, konuşma) buluta gitmez.
- Sipariş akışı: kullanıcı giriş yapar, sepet kurulur, **ödemeden önce durulur**; parola/kart saklanmaz. (Özellik 2026-10-26'da iptal edildi; yeniden açılırsa geçerli.)
- Kod ajanı yalnızca `workspace/` içinde; `eval/exec/os.system/shell=True/pickle` ve kapalı TLS doğrulaması yok (`tests/test_security.py` tarar).

## Kod konvansiyonları
- Yeni yetenek = `skills/<ad>.py` içinde `SKILLS=[{name, description, parameters, run, hidden?}]`; sık/kalıbı belli olanlar `hidden` + `core/brain.py` hızlı yol kuralı (araç sayısı arttıkça Gemma bozuluyor). Kontrol listesi: `REMOTE_BLOCKED`, `ACTION_CLAIM`, `core/agent.py ALLOWED/NETWORK/HELP`, onay gerekir mi, `tests/test_routes.py` vakası.
- Ollama çağrılarında `think=False`. Testler `JARVIS_DATA`'yı geçici klasöre alır, `ollama` sahte olabilir (GPU gerekmez).
- Opsiyonel bağımlılıklar tembel import; yoksa kibarca düş.
- Linux (X11) birincil hedef; Windows taşıması planda, Linux davranışını bozma.
