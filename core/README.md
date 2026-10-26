# core/ — beyin ve ajanlar

Jarvis'in düşünen kısmı: cümleyi anlar, araç seçer, gerekirse çok adımlı plan yürütür. Kişisel her şey yerel modelde kalır.

| Dosya | Görevi |
|---|---|
| `brain.py` | Model (Ollama `gemma4:e4b`, yedek `qwen3:8b`), araç çağırma, kural tabanlı **hızlı yol**, onay kapısı denetimi, oturum ve bağlam özetleme. `REMOTE_BLOCKED`, `UNTRUSTED_TOOLS` burada. |
| `agent.py` | **Ajan modu**: tek cümleden plan, sesli okuma, tek onay, adım adım yürütme (en fazla 8 adım). |
| `team.py` | **Ekip modu**: Planlayıcı → Araştırma / Dosya / Kod / Bakım ajanları → Denetçi → Yazar; Mimar büyük istekleri parçalar. |
| `router.py` | Ücretsiz bulut modelleri (Groq vb., OpenAI uyumlu) yedek zinciriyle; limit/hata yönetimi. |
| `privacy.py` | Gizlilik kapısı: kişisel veri içeren hiçbir şey buluta gitmez. |
| `memguard.py` | Bellek koruması: düşük bellekte uyarı, ağır işi başlatmama. |
| `convlog.py` | Kalıcı konuşma günlüğü (panodaki Konuşmalar; süreli otomatik silme). |
| `scheduler.py` | **Zamanlanmış görevler**: Türkçe zaman ayrıştırma, "zamanı geldi mi" kuralı, arka plan zamanlayıcı (`data/schedules.json`). |
| `mcp_client.py` | Yerel MCP istemcisi (stdio JSON-RPC; ek bağımlılık yok). Araçlar `skills/mcp.py`'de. |

## Hızlı yol ve araç seçimi
Yerel küçük modelde araç çağırma kırılgandır: araç sayısı ve istem uzadıkça yanlış araç seçer. Bu yüzden sık ve kalıbı belli komutlar
(saat, hava, sistem, tarayıcı, telefon, MCP…) modele hiç sorulmadan `brain._fast_route` ile çalışır; bu araçlar modelin şemasında
görünmez (`hidden`). Sistem istemi bilerek kısadır; değiştirmeden önce `python tools/tool_check.py` ile ölçülür.

## Model yönlendirici (ücretsiz bulut)
Yerel model varsayılandır. Zor işlerde (kod, plan, "bulut: …" ile sorulan genel sorular) ücretsiz bulut modelleri kullanılır.
```bash
python tools/router_check.py --init     # data/keys.env şablonu (git'e gitmez); GROQ_API_KEY= satırına anahtarı yaz
python tools/router_check.py            # anahtar ve gizlilik kapısı denemesi
```
- "bulut: python'da sözlük nasıl sıralanır" → yalnızca bu cümle gider (geçmiş, hafıza, ekran eklenmez).
- Gizlilik kapısı parola/anahtar/e-posta/telefon/adres/kart/IBAN/T.C. no içeren mesajı göndermez; hafıza, konuşma kaydı, ekran, kamera hiç gitmez. Pano > Ayarlar > Bulut modelleri ile tamamen kapatılır.
- Groq ücretsiz katmanı ≈ dakikada 8K jeton: büyük girdi hiç gönderilmez, 429'da sıradaki modele geçilir.
- Sağlayıcı eklemek: `data/models.json` → `{"providers": {"mistral": {"label": "Mistral", "base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY", "models": ["mistral-small-latest"]}}}`

## Ajan ve ekip modu
- **Ajan modu:** "ajan modu: Wikipedia'da Ankara'yı araştır ve özetle". Plan yalnızca senin cümlenden çıkar, baştan okunur, tek "evet" ile başlar; her adımda yalnızca o adımın aracı çağrılabilir; dosya okunduktan sonra internete giden adım ayrıca onay ister.
- **Ekip modu:** "ekip: …" (planı model çıkarır), "araştır: …" (Araştırma + Yazar). Model seçimi her çağrıda: bağlam temizse bulut, değilse yerel. Kişisel veri okuyan görev (Dosya Ajanı) ve ona bağlı her görev yalnızca yerelde çalışır. En fazla 5 görev; `data/team_runs.jsonl` yalnızca özet tutar.

## Kod ajanı, Denetçi, Mimar
- "kod: bir hesap makinesi yaz" → Kod Ajanı `workspace/<proje>/` içinde yazar, çalıştırır, düzeltir; **Denetçi** projeyi ayrı bağlamda kendisi çalıştırıp yalnızca düzeltilmesi gereken bulguları bildirir (dosya yazamaz). Hükmü kod belirler: bulgu varsa "geçti" sayılmaz, programı çalıştırmadan "geçti" kabul edilmez. İstemezsen "kod: denetimsiz, …".
- "proje: …" → **Mimar** isteği en fazla 4 parçaya böler (parça başı ≤2 dosya, ≈120 satır/dosya, arayüzlerle); tek "evet" ile parçalar sırayla yazılır, sonda Denetçi tüm projeyi çalıştırır.
- Kod **bubblewrap** kutusunda çalışır: internet yok, ev klasörü ve anahtarlar görünmez, 30 sn, `prlimit` ve cgroup bellek tavanı. Yalnızca `python/python3/pytest/node`. Deneme: `python tools/code_check.py`.
- Yerel modelin bozuk JSON'u kodda onarılır (`team._repair`); aynı çağrı tekrarlanmaz, dosya çalıştırılmadan en fazla 2 kez yazılır.

## MCP istemcisi
Sunucuları **sen** kurar ve `data/mcp.json`'a yazarsın (denenmiş örnek: `mcp-server-time`, ayrı sanal ortamda):
```bash
python -m venv ~/.local/share/jarvis/mcp-venv && ~/.local/share/jarvis/mcp-venv/bin/pip install mcp-server-time
```
```json
{"servers": {"zaman": {"command": "~/.local/share/jarvis/mcp-venv/bin/mcp-server-time", "args": ["--local-timezone", "Europe/Istanbul"],
                       "tools": ["get_current_time", "convert_time"], "timeout": 30}}}
```
"mcp araçları", "mcp: zaman get_current_time timezone=Europe/Istanbul". Her çağrı onay ister, sonuç modele gitmez, uzaktan kapalı; sunucuya Jarvis'in anahtarları geçmez. Yalnızca güvendiğin yerel sunucuları ekle.

## Zamanlanmış görevler
"her gün 9'da hava nasıl", "hafta içi her gün 8:30'da günün özeti", "her cuma 17'de görevlerim", "her akşam 7'de pil kaç" (19:00).
Listeleme "zamanlanmış görevler", silme "zamanlanmış görevi sil 2" ya da pano > Görevler.
- **Kurmak onay ister**; araçlar gizli (model kendi başına kuramaz) ve uzaktan kapalı.
- Zamanı gelen görev, kullanıcının kendi cümlesi olarak **Telegram ile aynı kısıtlı kipte** çalışır (dosya, tarayıcı, fare/klavye, kod, telefon araması, MCP kapalı; bilgisayarda bekleyen onay verilemez). Ajan/ekip/kod/MCP görevleri onay gerektirdiği için zamanlanamaz.
- Sonuç "Zamanlanmış görev. …" diye bildirilir (odak modunda yalnızca panoya; Telegram açıksa telefona da).
- Bilgisayarda onay bekleyen işlem varsa ya da Jarvis meşgulse görev ertelenir; en fazla 10 dk gecikme tanınır, bilgisayar kapalıyken kaçırılanlar sonradan topluca çalışmaz.
