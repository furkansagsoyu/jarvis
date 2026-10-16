"""Yetenek (skill) yükleyici.

skills/ klasöründeki her .py dosyası (adı "_" ile başlamayanlar) otomatik yüklenir.
Bir yetenek dosyası şunu tanımlar:

    SKILLS = [
        {
            "name": "arac_adi",                      # modelin çağıracağı ad
            "description": "Ne yapar. Ne zaman kullanılır.",   # ilk cümle yetenek listesine girer
            "parameters": {...},                     # JSON şeması (parametre yoksa atlanabilir)
            "run": fonksiyon,                        # parametreleri anahtar kelime olarak alır, str döndürür
        },
    ]

Yeni yetenek eklemek için yeni bir dosya yazmak yeterli, başka yere dokunmaya gerek yok.
"""
import importlib
import pkgutil
from pathlib import Path


def load_skills(verbose: bool = False) -> dict:
    """{ad: (ollama_şeması, fonksiyon)} sözlüğü döndürür."""
    tools: dict = {}
    for info in sorted(pkgutil.iter_modules([str(Path(__file__).parent)]), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[skills] {info.name} yüklenemedi: {type(exc).__name__}: {exc}", flush=True)
            continue
        for sk in getattr(mod, "SKILLS", []):
            name = sk["name"]
            if name in tools:
                print(f"[skills] '{name}' iki kez tanımlı ({info.name}), ikincisi atlandı", flush=True)
                continue
            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": sk["description"],
                    "parameters": sk.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            tools[name] = (schema, sk["run"])
            if verbose:
                print(f"[skills] yüklendi: {name} ({info.name}.py)", flush=True)
    return tools


def capability_summary(tools: dict) -> str:
    """Sistem prompt'una konacak kısa yetenek listesi (her açıklamanın ilk cümlesi)."""
    items = []
    for schema, _ in tools.values():
        desc = schema["function"]["description"].strip()
        items.append(desc.split(".")[0].strip())
    return "; ".join(items)
