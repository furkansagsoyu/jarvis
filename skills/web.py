"""İnternette arama: varsayılan tarayıcıda Google aramasını açar."""
import subprocess
from urllib.parse import quote_plus


def web_search(query: str) -> str:
    query = str(query).strip()
    if not query:
        return "Arama sorgusu boş."
    url = "https://www.google.com/search?q=" + quote_plus(query)
    subprocess.Popen(["xdg-open", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return f"'{query}' için arama sonuçlarını tarayıcıda açtım."


SKILLS = [
    {
        "name": "web_search",
        "description": "İnternette arama yapar ve sonuçları tarayıcıda açar. Kullanıcı bir şeyi aramanı isterse kullan.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Arama sorgusu"}},
            "required": ["query"],
        },
        "run": web_search,
    }
]
