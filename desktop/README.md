# desktop/ — masaüstü arayüzü

| Dosya | Görevi |
|---|---|
| `ui_state.py` | Jarvis ile arayüzler arasında paylaşılan durum (`data/status.json`, `control.json`, `settings.json`): durumlar, sessiz/odak, tema, ada ayarları, **maskot eşlemesi** (`mascot_state`). |
| `island.py` | **Üst kenar adası** (Qt): durum, Evet/Hayır onay çubuğu, hareketli Çekirdek maskotu. `python main.py --island` ya da otomatik başlatma açar. |
| `ui.py` | Eski küçük durum penceresi + tepsi simgesi (`--ui`); otomatik başlatmada artık yok, istersen elle verilir. |

## Durumlar ve maskot
| Jarvis durumu | Anlamı | Maskot |
|---|---|---|
| `listening` | "Hey Jarvis"i bekliyor | idle |
| `recording` | uyandı, seni dinliyor | listening |
| `thinking` / `speaking` | düşünüyor / konuşuyor | thinking / speaking |
| bekleyen onay ya da plan | soru bekliyor | alert (amber) |
| hata (`flag_error`, 8 sn) | bir komut hata verdi | error (kırmızı) |

Maskotun kendisi `assets/cekirdek.svg`; panoda animasyonlu SVG, adada aynı geometriden kare kare çizilen sürüm (~15 kare/sn).

## Ada
- **Küçük hap** (bekleme) → **etkin hal** ("Hey Jarvis"ten sonra büyür, maskot ortaya gelir) → **onay** (soru, kalan süre, Evet/Hayır).
- **Otomatik gizlenme** (varsayılan açık): beklemede üst kenarın arkasına kayıp saklanır, "Hey Jarvis"le kayarak gelir, cevaptan 6 sn sonra yine saklanır; onay/uyarı/hata varken hep görünür.
- **Pano > Ayarlar > ADA:** aç/kapa, her zaman üstte, otomatik gizlen, maskot, konum (orta/sol/sağ), boyut, tema. Değerler `settings.json`'da; ada yeniden başlatmadan uygular. Kapatılan ada pano tepsi menüsündeki "Adayı aç" ile döner.
- Güvenlik: düğmeler sesli "evet/hayır" ile aynı yoldan geçer (onay kapısı değişmez); her bekleyen işlemin kimliği var (eski soruya basılan Evet yenisini onaylamaz); ada odak almaz ve fare/klavye aracı Jarvis'in kendi pencerelerine tıklamaz — model kendi onayını veremez. Pano sunucusuna yalnızca 127.0.0.1 ve oturum anahtarıyla bağlanır.
- Hareket azaltma: `JARVIS_REDUCED_MOTION=1`. Fikir: [coucou](https://github.com/louis-cfm/coucou) (kod/görsel alınmadı).
