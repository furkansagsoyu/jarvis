# tests/ — testler

```bash
python check_all.py --quick       # hepsi (model ve donanım gerekmez, ~30 sn)
python tests/test_routes.py       # tek modül
python check_all.py --model       # + gerçek modelle araç seçimi (GPU + Ollama)
python check_all.py --vision --agent
```

Kurallar:
- Her test `JARVIS_DATA`'yı geçici klasöre yönlendirir; gerçek `data/` hiç okunmaz/yazılmaz.
- `ollama` kurulu değilse sahte modül konur; modelin cevabı test içinde taklit edilir (GPU gerekmez).
- Testler kök klasördeki paketleri (`core`, `voice`, `desktop`, `connect`, `tools`, `skills`, `dashboard`) kullanır; her dosyanın başı depo kökünü `sys.path`'e ekler, yani herhangi bir klasörden çalıştırılabilir.
- Yeni davranış = yeni test vakası; özellikle `test_routes.py`'ye "bu cümle bu aracı çağırmalı / çağırmamalı" satırı.

| Test | Kapsam |
|---|---|
| `test_routes` | hızlı yol: cümle → araç |
| `test_security` | data/ izinleri, uzaktan kapalı araçlar ve uzaktan onay, kod kutusu, `eval/exec/shell=True`/kapalı TLS taraması |
| `test_agent`, `test_team` | ajan ve ekip modu, Denetçi, Mimar, JSON onarımı |
| `test_code` | kod ajanı araçları ve kutu |
| `test_router` | bulut yönlendirici ve gizlilik kapısı |
| `test_browser`, `test_web`, `test_desktop` | tarayıcı (gerçek Chromium, yerel site), web arama, fare/klavye (sahte xdotool) |
| `test_agenda`, `test_memory`, `test_maintenance`, `test_mcp` | takvim/görev, hafıza (FTS5), bakım ajanı, MCP (sahte sunucu) |
| `test_dashboard`, `test_window`, `test_mobile` | pano, pencere/tepsi, telefon sayfası |
| `test_island`, `test_mascot` | ada (Qt duman testi dahil) ve maskot |
| `test_phone`, `test_phonelink`, `test_ram`, `test_app` | telefon, FCM, bellek, masaüstü kurulumu |
