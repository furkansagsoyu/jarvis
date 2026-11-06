# JARVIS — Claude Code proje kuralları

Türkçe konuşan, tamamen yerel/ücretsiz sesli asistan. Durum, mimari, kararlar, geçmiş: **@HANDOFF.md** · Görev sırası: **@TASKS.md**
Dil: arayüz metinleri, sesli cevaplar, yorumlar ve kullanıcıyla yazışma **Türkçe**.

## Komutlar
- Python: conda env `freya` (`/home/furkan/miniconda3/envs/freya/bin/python`)
- Her değişiklikten sonra: `python check_all.py --quick` → hatasız olmalı (modelsiz, saniyeler)
- Tek modül: `python tests/test_<ad>.py` · Gerçek model: `python check_all.py --model` · Bellek: `python tools/ram_report.py --watch SN --label X`

## Proje yapısı
Kökte yalnızca `main.py`, `app.py`, `check_all.py`.
- `core/` beyin (`brain.py`), ajan/ekip, yönlendirici + gizlilik kapısı, bellek koruması, zamanlayıcı, MCP istemcisi
- `voice/` STT, TTS, wake word · `desktop/` ada, ui_state · `connect/` Telegram, telefon, uzaktan
- `skills/` yetenekler (`_` ile başlayanlar yardımcı) · `dashboard/` pano sunucusu + pencere · `assets/` maskot vb.
- `tools/` kurulum/tanılama betikleri · `tests/` test_*.py · `phone_app/` Flutter uygulaması
- İçe aktarma paket yoluyla (`from core import brain`); `tools/` ve `tests/` betikleri başta depo kökünü `sys.path`'e ekler. Her klasörün README'si var.

## Çalışma düzeni
- `TASKS.md`'deki görevleri sırayla, sormadan yap: kod + test → `check_all.py --quick` yeşil → commit → push → sıradaki.
- **[HW]** görevler (mikrofon, wake word, ses, telefon/Flutter, görsel Qt doğrulaması): commit'le, kullanıcıya tek satırda ne deneyeceğini söyle, cevabı bekle; "çalışıyor" gelince push et.
- **[SOR]** adımlar: `AskUserQuestion` ile sor. Başka onay isteme. Ayrıca dur ve sor: geri alınamaz iki yönlü karar, sır/anahtar gerektiren adım, onay/gizlilik kurallarını gevşeten değişiklik.
- Her önemli değişiklikte `README.md` (ve ilgili klasör README'si), gerekiyorsa `RAM.md` güncellenir. Biten görev `TASKS.md`'de işaretlenir, ayrıntı `HANDOFF.md` geçmişine yazılır.

## Asla
- Repo **PUBLIC**. `data/`, `*.env`, `keys.env`, `fcm_service_account.json`, `google-services.json`, `workspace/`, `*.zip` commit'lenmez (`git add -f` yok). Push öncesi `git diff --cached` ile sır taraması (`AIza`, `gsk_`, `sk-`, `ts.net`, telefon/e-posta).
- `data/` kullanıcının kişisel verisidir: okuma/yazma/silme yok.
- Onay kapılarını (`skills/_confirm.py`), yasaklı yüzeyleri, `core/privacy.py` kapısını gevşetme. Model onay veremez. Dış içerikten (dosya/web/ekran) sonra araç listesi boş kalır. Uzaktan kip yerel onayı cevaplayamaz.
- Kişisel veri (hafıza, rehber, takvim, dosya, ekran, kamera, konuşma) buluta gitmez.
- Kod ajanı yalnızca `workspace/` içinde; `eval/exec/os.system/shell=True/pickle` ve kapalı TLS doğrulaması yok (`tests/test_security.py` tarar).
- Başka projelerin kodu/görselleri kopyalanmaz (yalnızca fikir).

## Kod konvansiyonları
- Yeni yetenek = `skills/<ad>.py` içinde `SKILLS=[{name, description, parameters, run, hidden?}]`; varsayılan: `hidden` + `core/brain.py` hızlı yol kuralı (araç sayısı arttıkça Gemma bozuluyor). Kontrol listesi: `REMOTE_BLOCKED`, `ACTION_CLAIM`, `core/agent.py ALLOWED/NETWORK/HELP`, onay gerekir mi, `tests/test_routes.py` vakası.
- Ollama çağrılarında `think=False`. Testler `JARVIS_DATA`'yı geçici klasöre alır, `ollama` sahte olabilir (GPU gerekmez).
- Yeni dosyalarda `from __future__ import annotations`, Türkçe docstring. Opsiyonel bağımlılıklar tembel import; yoksa kibarca düş; `requirements.txt` güncellenir.
- Linux (X11) birincil hedef; Windows taşıması Linux davranışını bozmaz.
