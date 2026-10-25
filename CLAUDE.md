# JARVIS — Claude Code proje kuralları

Türkçe konuşan, tamamen yerel/ücretsiz sesli asistan. **Ayrıntılı devir teslim: @HANDOFF.md** · Görev sırası: **@TASKS.md**
Dil: arayüz metinleri, sesli cevaplar, yorumlar ve kullanıcıyla yazışma **Türkçe**.

## Komutlar
- Test (her değişiklikten sonra, modelsiz, saniyeler): `python check_all.py --quick` → hatasız olmalı (son durum 42 OK)
- Tek modül: `python test_<ad>.py` · Gerçek model: `python check_all.py --model` · Bellek: `python ram_report.py --watch SN --label X`
- Python: conda env `freya` (`/home/furkan/miniconda3/envs/freya/bin/python`)

## Çalışma düzeni
- `TASKS.md`'deki görevleri sırayla, kullanıcıya sormadan yap: kod + test → `check_all.py --quick` yeşil → commit → push → sıradaki görev.
- **[HW] etiketli görevler** (mikrofon, wake word, ses, telefon/Flutter, görsel Qt doğrulaması): commit'le, kullanıcıya tek satırda ne deneyeceğini söyle, cevabı bekle; "çalışıyor" gelince push edip devam et.
- Başka onay isteme. Dur ve sor: geri alınamaz iki yönlü karar, sır/anahtar gerektiren adım, onay/gizlilik kurallarını gevşeten değişiklik.
- Her önemli değişiklikte `README.md` ve gerekiyorsa `RAM.md`'yi güncelle (kullanıcı özellikle istedi).

## Asla
- Repo **PUBLIC**. `data/`, `*.env`, `keys.env`, `fcm_service_account.json`, `google-services.json`, `workspace/`, `*.zip` commit'lenmez (`git add -f` yok). Push öncesi `git diff --cached` ile sır taraması (`AIza`, `gsk_`, `sk-`, `ts.net`, telefon/e-posta).
- `data/` kullanıcının kişisel verisidir: okuma/yazma/silme yok.
- Onay kapılarını (`skills/_confirm.py`), yasaklı yüzeyleri, `privacy.py` kapısını gevşetme. Model onay veremez. Dış içerikten (dosya/web/ekran) sonra araç listesi boş kalır.
- Kişisel veri (hafıza, rehber, takvim, dosya, ekran, kamera, konuşma) buluta gitmez.
- Sipariş akışı: kullanıcı giriş yapar, sepet kurulur, **ödemeden önce durulur**; parola/kart saklanmaz.
- Kod ajanı yalnızca `workspace/` içinde; `eval/exec/os.system/shell=True/pickle` ve kapalı TLS doğrulaması yok (`test_security.py` tarar).

## Kod konvansiyonları
- Yeni yetenek = `skills/<ad>.py` içinde `SKILLS=[{name, description, parameters, run, hidden?}]`; sık/kalıbı belli olanlar `hidden` + `brain.py` hızlı yol kuralı (araç sayısı arttıkça Gemma bozuluyor). Kontrol listesi: `REMOTE_BLOCKED`, `ACTION_CLAIM`, `agent.py ALLOWED/NETWORK/HELP`, onay gerekir mi, `test_routes.py` vakası.
- Ollama çağrılarında `think=False`. Testler `JARVIS_DATA`'yı geçici klasöre alır, `ollama` sahte olabilir (GPU gerekmez).
- Opsiyonel bağımlılıklar tembel import; yoksa kibarca düş.
- Linux (X11) birincil hedef; Windows taşıması planda, Linux davranışını bozma.
