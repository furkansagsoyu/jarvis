#!/usr/bin/env python3
"""Kural tabanlı hızlı yolu (brain._fast_route) modelsiz doğrular. Saniyeler sürer, GPU/Ollama gerekmez.

    python test_routes.py
Her cümle için beklenen araç; None = hızlı yol karışmamalı (model karar verir).
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
try:
    import ollama  # noqa: F401
except ImportError:  # modelsiz ortam: yönlendirme testi ollama'ya ihtiyaç duymaz
    sys.modules["ollama"] = types.ModuleType("ollama")

from brain import Brain  # noqa: E402
from skills import files  # noqa: E402

CASES = [
    ("Saat kaç?", "get_time"),
    ("Bugün günlerden ne?", "get_date"),
    ("Hava nasıl?", "get_weather"),
    ("Yarın yağmur var mı", "get_weather"),
    ("İstanbul'da hava nasıl", None),
    ("Pil kaç?", "get_battery"),
    ("Şarjım ne kadar kaldı", "get_battery"),
    ("Pilim yüzde kaç", "get_battery"),
    ("Pil durumu nasıl", "get_battery"),
    ("Şarja tak", None),
    ("Pil tasarrufu modunu aç", None),
    ("Günaydın", "morning_brief"),
    ("Günün özetini ver", "morning_brief"),
    ("Bugün neler var", "morning_brief"),
    ("Yarın saat beşte uyar", None),
    ("rapor.pdf dosyasını oku", "read_file"),
    ("Yaptığımı geri al", "undo_last_action"),
    ("Ekranda ne var", "look_at_screen"),
    ("Ekrana bak", "look_at_screen"),
    ("Ekranımı anlat", "look_at_screen"),
    ("Ekranı karart", None),
    ("Ekran görüntüsü al", None),
    ("Parlaklığı artır", None),
    ("CPU kaç", "get_system_status"),
    ("İşlemci sıcaklığı kaç", "get_system_status"),
    ("RAM ne kadar dolu", "get_system_status"),
    ("Ekran kartı nasıl", "get_system_status"),
    ("Sistem durumu nasıl", "get_system_status"),
    ("Bilgisayar sıcaklığı kaç", "get_system_status"),
    ("Sesi kıs", None),
    ("Terminali aç", None),
    ("Ankara'nın nüfusunu araştır", None),
]
# "Bunu oku" ancak yakın zamanda dosya aranmışsa dosya okumaya gider
CONTEXT_CASES = [("onu oku", "read_file"), ("ikincisini özetle", "read_file"), ("ilk yardım nedir", None)]


def main():
    brain = Brain(tools=None)
    bad = 0
    files._last = []
    for text, want in CASES:
        got = brain._fast_route(text)
        name = got[0][0] if got else None
        ok = name == want
        bad += not ok
        print(f"{'OK  ' if ok else 'HATA'} {text!r:36} -> {name}  (beklenen {want})")
    from pathlib import Path  # noqa: PLC0415
    files._remember([Path("/tmp/a.txt"), Path("/tmp/b.txt")])
    for text, want in CONTEXT_CASES:
        got = brain._fast_route(text)
        name = got[0][0] if got else None
        ok = name == want
        bad += not ok
        print(f"{'OK  ' if ok else 'HATA'} [bağlamlı] {text!r:24} -> {name}  (beklenen {want})")
    files._last = []
    got = brain._fast_route("onu oku")
    ok = not got
    bad += not ok
    print(f"{'OK  ' if ok else 'HATA'} [bağlamsız] 'onu oku' -> {got or None}  (beklenen None)")
    print(f"\n{'TÜMÜ TAMAM' if not bad else f'{bad} HATA'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
