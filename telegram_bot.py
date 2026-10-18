#!/usr/bin/env python3
"""Telegram köprüsü: telefondan Jarvis'e yaz, Jarvis'ten bildirim al. Ek kütüphane gerekmez (urllib).

Kurulum (bir kez):
    1) Telegram'da @BotFather -> /newbot -> bir ad ve kullanıcı adı seç -> verdiği TOKEN'ı kopyala.
    2) python telegram_bot.py --setup      (token'ı sorar, sonra botuna bir mesaj yazmanı ister,
                                            sohbet kimliğini bulup data/telegram.json'a kaydeder)
    3) python main.py --wake --ui --telegram

Güvenlik:
- Yalnızca kayıtlı sohbet kimliğinden (chat_id) gelen mesajlara cevap verilir; başkaları yok sayılır.
- Token ve chat_id data/telegram.json içinde (git dışında). Ortam değişkeni de olur: JARVIS_TELEGRAM_TOKEN.
- Mesajlar Telegram sunucularından geçer (bot mesajları uçtan uca şifreli değildir). Bu yüzden dosya
  içeriği okuma (read_file) ve hafızadan hatırlama (recall) uzaktan kapalıdır; bkz. brain.REMOTE_BLOCKED.
"""
import argparse
import json
import os
import threading
import time
import urllib.parse
import urllib.request

from skills import _store

API = "https://api.telegram.org/bot{token}/{method}"
CONFIG = "telegram.json"
MAX_LEN = 3900  # Telegram sınırı 4096


def load_config() -> dict:
    cfg = dict(_store.load(CONFIG, {}))
    if os.environ.get("JARVIS_TELEGRAM_TOKEN"):
        cfg["token"] = os.environ["JARVIS_TELEGRAM_TOKEN"]
    return cfg


def chunks(text: str, size: int = MAX_LEN) -> list[str]:
    text = (text or "").strip()
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


class TelegramBot:
    def __init__(self, token: str, chat_id: int | None, handler, api=None):
        """handler(text) -> cevap metni. api(method, **params) -> dict (testte sahte verilir)."""
        self.token, self.chat_id, self.handler = token, chat_id, handler
        self._api = api or self._http
        self._offset = 0
        self._stop = threading.Event()
        self._warned: set[int] = set()

    def _http(self, method: str, **params) -> dict:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(API.format(token=self.token, method=method), data=data)
        with urllib.request.urlopen(req, timeout=params.get("timeout", 0) + 15) as r:
            out = json.loads(r.read().decode("utf-8"))
        if not out.get("ok"):
            raise RuntimeError(out.get("description", "Telegram hatası"))
        return out

    def send(self, text: str, chat_id: int | None = None) -> None:
        cid = chat_id or self.chat_id
        if not cid:
            return
        for part in chunks(text):
            if part:
                self._api("sendMessage", chat_id=cid, text=part)

    def notify(self, text: str) -> None:
        """Jarvis'in sesli söylediği bildirimleri (hatırlatma, pil) telefona da gönderir; hata sessizce yutulur."""
        try:
            self.send(text)
        except Exception as exc:  # noqa: BLE001
            print(f"[telegram] gönderilemedi: {type(exc).__name__}", flush=True)

    def handle_update(self, upd: dict) -> None:
        msg = upd.get("message") or {}
        cid = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or "").strip()
        if not cid or not text:
            return
        if cid != self.chat_id:  # yetkisiz sohbet: cevap verme, bir kez logla
            if cid not in self._warned:
                self._warned.add(cid)
                print(f"[telegram] yetkisiz sohbet yok sayıldı (id {cid})", flush=True)
            return
        if text.startswith("/start"):
            self.send("Jarvis hazır. Komutunu yaz.", cid)
            return
        print(f"[telegram] Sen> {text}", flush=True)
        try:
            reply = self.handler(text)
        except Exception as exc:  # noqa: BLE001
            reply = f"Hata: {type(exc).__name__}"
        self.send(reply or "Bunu yapamadım.", cid)

    def poll_once(self, timeout: int = 25) -> None:
        out = self._api("getUpdates", offset=self._offset, timeout=timeout)
        for upd in out.get("result", []):
            self._offset = max(self._offset, upd["update_id"] + 1)
            self.handle_update(upd)

    def start(self) -> None:
        def loop():
            backoff = 2
            while not self._stop.is_set():
                try:
                    self.poll_once()
                    backoff = 2
                except Exception as exc:  # noqa: BLE001  (ağ koptu vb.: bekle, tekrar dene)
                    print(f"[telegram] bağlantı sorunu ({type(exc).__name__}), {backoff} sn sonra tekrar", flush=True)
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 60)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def make_bot(handler) -> "TelegramBot | None":
    cfg = load_config()
    if not cfg.get("token") or not cfg.get("chat_id"):
        return None
    return TelegramBot(cfg["token"], int(cfg["chat_id"]), handler)


def setup() -> None:
    token = input("BotFather'ın verdiği token: ").strip()
    probe = TelegramBot(token, None, None)
    me = probe._api("getMe")["result"]
    print(f"Bot bulundu: @{me['username']}")
    input(f"Şimdi Telegram'da @{me['username']} botuna herhangi bir mesaj yaz, sonra Enter'a bas... ")
    updates = probe._api("getUpdates", offset=0, timeout=0).get("result", [])
    chats = {}
    for u in updates:
        c = (u.get("message") or {}).get("chat")
        if c:
            chats[c["id"]] = c.get("first_name") or c.get("title") or str(c["id"])
    if not chats:
        raise SystemExit("Mesaj görmedim. Bota yazdığından emin olup tekrar dene.")
    if len(chats) > 1:
        print("Birden fazla sohbet var:", chats)
    cid, name = list(chats.items())[-1]
    if input(f"Yetkili sohbet: {name} (id {cid}). Doğru mu? [e/h] ").strip().lower() not in ("e", "evet"):
        raise SystemExit("İptal edildi.")
    _store.save(CONFIG, {"token": token, "chat_id": cid})
    probe.chat_id = cid
    probe.send("Jarvis bağlandı. Artık buradan komut verebilirsin.")
    print("Kaydedildi: data/telegram.json (git dışında).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--test", action="store_true", help="kayıtlı sohbete test mesajı gönder")
    a = ap.parse_args()
    if a.setup:
        setup()
    elif a.test:
        bot = make_bot(None)
        if not bot:
            raise SystemExit("Kurulu değil: önce --setup")
        bot.send("Test: Jarvis burada.")
        print("Gönderildi.")
    else:
        ap.print_help()
